import uuid

import pytest
from httpx import AsyncClient

from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]

JOB = {
    "company": "Acme",
    "title": "Backend Engineer",
    "location": "London",
    "url": "https://jobs.example.com/acme/backend-1",
}


async def create_job(client: AsyncClient, **overrides: str) -> dict[str, str]:
    response = await client.post("/api/v1/jobs", json=JOB | overrides)
    assert response.status_code == 201, response.text
    return response.json()


async def test_create_and_get_job(client: AsyncClient) -> None:
    job = await create_job(client)
    response = await client.get(f"/api/v1/jobs/{job['id']}")
    assert response.status_code == 200
    assert response.json()["company"] == "Acme"


async def test_duplicate_job_url_is_a_conflict(client: AsyncClient) -> None:
    await create_job(client)
    response = await client.post("/api/v1/jobs", json=JOB)
    assert response.status_code == 409


async def test_invalid_job_payload_is_rejected(client: AsyncClient) -> None:
    response = await client.post("/api/v1/jobs", json=JOB | {"url": "not-a-url", "company": ""})
    assert response.status_code == 422


async def test_list_jobs_is_paginated(client: AsyncClient) -> None:
    for i in range(3):
        await create_job(client, url=f"https://jobs.example.com/acme/{i}")
    response = await client.get("/api/v1/jobs", params={"limit": 2, "offset": 0})
    body = response.json()
    assert response.status_code == 200
    assert len(body["items"]) == 2
    assert (await client.get("/api/v1/jobs", params={"limit": 101})).status_code == 422


async def test_unknown_job_is_404(client: AsyncClient) -> None:
    assert (await client.get(f"/api/v1/jobs/{uuid.uuid4()}")).status_code == 404


async def test_application_lifecycle(client: AsyncClient) -> None:
    job = await create_job(client)
    created = await client.post("/api/v1/applications", json={"job_id": job["id"]})
    assert created.status_code == 201
    application = created.json()
    assert application["stage"] == "saved"

    updated = await client.patch(
        f"/api/v1/applications/{application['id']}",
        json={"referred_by": "Asha", "notes": "Asked on LinkedIn"},
    )
    assert updated.status_code == 200
    assert updated.json()["referred_by"] == "Asha"

    listed = await client.get("/api/v1/applications")
    assert [a["id"] for a in listed.json()["items"]] == [application["id"]]


async def test_second_application_for_same_job_is_a_conflict(client: AsyncClient) -> None:
    job = await create_job(client)
    await client.post("/api/v1/applications", json={"job_id": job["id"]})
    response = await client.post("/api/v1/applications", json={"job_id": job["id"]})
    assert response.status_code == 409


async def test_application_for_unknown_job_is_404(client: AsyncClient) -> None:
    response = await client.post("/api/v1/applications", json={"job_id": str(uuid.uuid4())})
    assert response.status_code == 404


async def test_patch_only_changes_sent_fields(client: AsyncClient) -> None:
    job = await create_job(client)
    application = (
        await client.post("/api/v1/applications", json={"job_id": job["id"], "notes": "keep me"})
    ).json()
    response = await client.patch(
        f"/api/v1/applications/{application['id']}", json={"referred_by": "Ravi"}
    )
    assert response.json()["notes"] == "keep me"
