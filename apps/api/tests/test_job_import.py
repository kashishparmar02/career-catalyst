import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI

from career_catalyst.sources import (
    AshbySource,
    GreenhouseSource,
    LeverSource,
    PostingNotFoundError,
    UnsupportedSourceError,
    UpstreamError,
    fetch_posting,
    find_source,
    get_http_client,
)
from tests.conftest import requires_db

FIXTURES = Path(__file__).parent / "fixtures"

GREENHOUSE_URL = "https://job-boards.greenhouse.io/acme/jobs/4012345002"
LEVER_URL = "https://jobs.lever.co/acme/6ed76ce8-4156-4b60-b120-403538bd66cd"
ASHBY_URL = "https://jobs.ashbyhq.com/acme/7458d4e9-da2e-47bd-98cb-adfda43d42b2"

# The only URLs the service may request, mapped to the recorded-shape response for each.
API_RESPONSES = {
    "https://boards-api.greenhouse.io/v1/boards/acme/jobs/4012345002": "greenhouse_job.json",
    "https://api.lever.co/v0/postings/acme/6ed76ce8-4156-4b60-b120-403538bd66cd": (
        "lever_posting.json"
    ),
    "https://api.ashbyhq.com/posting-api/job-board/acme": "ashby_board.json",
}

Handler = Callable[[httpx.Request], httpx.Response]


def boards(request: httpx.Request) -> httpx.Response:
    """Fake job-board APIs: known URLs return their fixture, anything else is a 404."""
    name = API_RESPONSES.get(str(request.url))
    if name is None:
        return httpx.Response(404, json={"error": "not found"})
    return httpx.Response(200, json=json.loads((FIXTURES / name).read_text()))


def status(code: int) -> Handler:
    return lambda _: httpx.Response(code, text="error")


def timeout(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectTimeout("timed out", request=request)


def http_client(handler: Handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.parametrize(
    ("url", "source"),
    [
        (GREENHOUSE_URL, GreenhouseSource),
        ("https://boards.greenhouse.io/acme/jobs/4012345002?gh_src=abc", GreenhouseSource),
        (LEVER_URL + "/apply", LeverSource),
        ("http://jobs.lever.co/acme/6ed76ce8-4156-4b60-b120-403538bd66cd/", LeverSource),
        (ASHBY_URL + "/application?utm_source=x", AshbySource),
    ],
)
def test_supported_links_pick_their_source(url: str, source: type) -> None:
    assert isinstance(find_source(url), source)


@pytest.mark.parametrize(
    "url",
    [
        "https://greenhouse.io.evil.com/acme/jobs/1",
        "https://job-boards.greenhouse.io.evil.com/acme/jobs/1",
        "https://evil.com/job-boards.greenhouse.io/acme/jobs/1",
        "https://evil-jobs.lever.co/acme/6ed76ce8-4156-4b60-b120-403538bd66cd",
        "https://jobs.lever.co@evil.com/acme/6ed76ce8-4156-4b60-b120-403538bd66cd",
        "https://jobs.lever.co:8443/acme/6ed76ce8-4156-4b60-b120-403538bd66cd",
        "ftp://jobs.ashbyhq.com/acme/7458d4e9-da2e-47bd-98cb-adfda43d42b2",
        "https://job-boards.greenhouse.io/../admin/jobs/1",
        "https://job-boards.greenhouse.io/acme/jobs/not-a-number",
        "https://jobs.lever.co/acme",
        "https://jobs.ashbyhq.com/acme/not-a-uuid",
        "https://www.linkedin.com/jobs/view/123",
    ],
)
def test_other_links_are_unsupported(url: str) -> None:
    with pytest.raises(UnsupportedSourceError):
        find_source(url)


async def test_greenhouse_posting_is_mapped_and_html_stripped() -> None:
    async with http_client(boards) as client:
        job = await fetch_posting("https://boards.greenhouse.io/ACME/jobs/4012345002/", client)
    assert (job.company, job.title, job.location) == (
        "Acme",
        "Senior Backend Engineer",
        "Remote, India",
    )
    assert str(job.url) == GREENHOUSE_URL
    assert job.description == (
        "Acme builds tools for teams & their data.\n\n"
        "What you will do\n\n- Design APIs\n\n- Own services in production"
    )


async def test_lever_posting_is_mapped_with_lists() -> None:
    async with http_client(boards) as client:
        job = await fetch_posting(LEVER_URL + "/apply", client)
    assert (job.company, job.title, job.location) == (
        "acme",
        "Platform Engineer",
        "Bengaluru, India",
    )
    assert str(job.url) == LEVER_URL
    assert job.description is not None
    assert "Join the platform team." in job.description
    assert "Requirements\n\n- 5+ years of Python" in job.description
    assert "<" not in job.description


async def test_ashby_posting_is_picked_from_the_board() -> None:
    async with http_client(boards) as client:
        job = await fetch_posting(ASHBY_URL.replace("acme", "Acme"), client)
    assert (job.company, job.title, job.location) == (
        "acme",
        "Staff Software Engineer",
        "Remote - India",
    )
    assert str(job.url) == ASHBY_URL
    assert job.description == "Hi, we are Acme.\n\nBuild the core."


async def test_ashby_posting_missing_from_board_is_not_found() -> None:
    async with http_client(boards) as client:
        with pytest.raises(PostingNotFoundError):
            await fetch_posting(
                "https://jobs.ashbyhq.com/acme/00000000-0000-0000-0000-000000000000", client
            )


@pytest.mark.parametrize(
    ("handler", "error"),
    [
        (status(404), PostingNotFoundError),
        (status(500), UpstreamError),
        (timeout, UpstreamError),
        (lambda _: httpx.Response(200, text="<html>not json</html>"), UpstreamError),
        (lambda _: httpx.Response(200, json={"unexpected": True}), UpstreamError),
    ],
)
async def test_upstream_failures_become_domain_errors(
    handler: Handler, error: type[Exception]
) -> None:
    async with http_client(handler) as client:
        with pytest.raises(error):
            await fetch_posting(GREENHOUSE_URL, client)


def use_boards(app: FastAPI, handler: Handler) -> None:
    async def fake_client() -> Any:
        async with http_client(handler) as client:
            yield client

    app.dependency_overrides[get_http_client] = fake_client


@requires_db
@pytest.mark.integration
@pytest.mark.parametrize(
    ("url", "title"),
    [
        (GREENHOUSE_URL, "Senior Backend Engineer"),
        (LEVER_URL, "Platform Engineer"),
        (ASHBY_URL, "Staff Software Engineer"),
    ],
)
async def test_import_stores_the_job(
    app: FastAPI, client: httpx.AsyncClient, url: str, title: str
) -> None:
    use_boards(app, boards)
    response = await client.post("/api/v1/jobs/import", json={"url": url})
    assert response.status_code == 201, response.text
    job = response.json()
    assert (job["title"], job["url"]) == (title, url)
    assert (await client.get(f"/api/v1/jobs/{job['id']}")).json()["description"]


@requires_db
@pytest.mark.integration
async def test_importing_the_same_posting_twice_is_a_conflict(
    app: FastAPI, client: httpx.AsyncClient
) -> None:
    use_boards(app, boards)
    first = await client.post("/api/v1/jobs/import", json={"url": GREENHOUSE_URL})
    assert first.status_code == 201
    again = "https://boards.greenhouse.io/Acme/jobs/4012345002?gh_src=linkedin"
    response = await client.post("/api/v1/jobs/import", json={"url": again})
    assert response.status_code == 409


@requires_db
@pytest.mark.integration
@pytest.mark.parametrize(
    ("url", "handler", "code"),
    [
        ("https://greenhouse.io.evil.com/acme/jobs/1", boards, 422),
        ("not-a-url", boards, 422),
        (GREENHOUSE_URL, status(404), 404),
        (GREENHOUSE_URL, status(500), 502),
        (GREENHOUSE_URL, timeout, 502),
    ],
)
async def test_import_failures_map_to_status_codes(
    app: FastAPI, client: httpx.AsyncClient, url: str, handler: Handler, code: int
) -> None:
    use_boards(app, handler)
    response = await client.post("/api/v1/jobs/import", json={"url": url})
    assert response.status_code == code, response.text
    assert (await client.get("/api/v1/jobs")).json()["items"] == []
