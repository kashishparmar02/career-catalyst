"""Job intake: turn a pasted job-board link into a JobCreate by reading the board's public JSON API.

Each supported board (Greenhouse, Lever, Ashby) is one adapter behind the JobSource protocol; what
varies between them is which links they recognise, which API they call and how its JSON maps to a
job. The registry picks the adapter by URL. Only fixed provider API hosts are ever requested, never
the pasted host, so a link cannot make the service fetch an arbitrary address.
"""

import re
from collections.abc import AsyncIterator
from html import unescape
from html.parser import HTMLParser
from typing import Any, Protocol
from urllib.parse import urlsplit

import httpx

from career_catalyst.schemas import JobCreate

HTTP_TIMEOUT = httpx.Timeout(10.0)
UNSUPPORTED = "Unsupported job link. Paste a Greenhouse, Lever or Ashby posting URL."

# Board and company slugs allow only letters, digits, "-" and "_", so they cannot add path
# segments to the API URL built from them.
SLUG = r"[A-Za-z0-9][A-Za-z0-9_-]*"
UUID = r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}"


class UnsupportedSourceError(Exception):
    pass


class PostingNotFoundError(Exception):
    pass


class UpstreamError(Exception):
    pass


async def get_http_client() -> AsyncIterator[httpx.AsyncClient]:
    """FastAPI dependency: one outbound HTTP client per request; tests swap in a mock transport."""
    async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
        yield client


class JobSource(Protocol):
    def matches(self, url: str) -> bool: ...

    async def fetch(self, url: str, client: httpx.AsyncClient) -> JobCreate: ...


def match_posting(url: str, hosts: frozenset[str], path: re.Pattern[str]) -> dict[str, str] | None:
    """Return the slug and id from a posting link, or None if the link is not for these hosts.

    The host must equal one of `hosts` exactly, so lookalikes such as greenhouse.io.evil.com or a
    link with user info (jobs.lever.co@evil.com) never match. Slugs are lowercased so the same
    posting pasted with different casing or tracking parameters is recognised as one.
    """
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"} or parts.hostname not in hosts:
        return None
    if parts.port is not None or parts.username is not None:
        return None
    found = path.fullmatch(parts.path)
    return {k: v.lower() for k, v in found.groupdict().items()} if found else None


def posting_ref(url: str, hosts: frozenset[str], path: re.Pattern[str]) -> dict[str, str]:
    """Like match_posting, but raise UnsupportedSourceError instead of returning None."""
    ref = match_posting(url, hosts, path)
    if ref is None:
        raise UnsupportedSourceError(UNSUPPORTED)
    return ref


async def get_json(client: httpx.AsyncClient, api_url: str) -> Any:
    """GET a provider API URL and decode it, turning every failure into a domain error."""
    try:
        response = await client.get(api_url)
    except httpx.TimeoutException as exc:
        raise UpstreamError("The job board did not answer in time") from exc
    except httpx.HTTPError as exc:
        raise UpstreamError("Could not reach the job board") from exc
    if response.status_code == httpx.codes.NOT_FOUND:
        raise PostingNotFoundError("The job board has no such posting (it may have closed)")
    if response.status_code != httpx.codes.OK:
        raise UpstreamError(f"The job board answered with HTTP {response.status_code}")
    return response.json()


class GreenhouseSource:
    hosts = frozenset({"job-boards.greenhouse.io", "boards.greenhouse.io"})
    path = re.compile(rf"/(?P<board>{SLUG})/jobs/(?P<id>\d+)/?")

    def matches(self, url: str) -> bool:
        return match_posting(url, self.hosts, self.path) is not None

    async def fetch(self, url: str, client: httpx.AsyncClient) -> JobCreate:
        ref = posting_ref(url, self.hosts, self.path)
        board, job_id = ref["board"], ref["id"]
        job = await get_json(
            client, f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
        )
        # Greenhouse returns the description as HTML that is itself HTML-escaped.
        return JobCreate(
            company=job["company_name"],
            title=job["title"],
            location=(job.get("location") or {}).get("name"),
            url=f"https://job-boards.greenhouse.io/{board}/jobs/{job_id}",
            description=html_to_text(unescape(job.get("content") or "")),
        )


class LeverSource:
    hosts = frozenset({"jobs.lever.co"})
    path = re.compile(rf"/(?P<company>{SLUG})/(?P<id>{UUID})(/apply)?/?")

    def matches(self, url: str) -> bool:
        return match_posting(url, self.hosts, self.path) is not None

    async def fetch(self, url: str, client: httpx.AsyncClient) -> JobCreate:
        ref = posting_ref(url, self.hosts, self.path)
        company, job_id = ref["company"], ref["id"]
        job = await get_json(client, f"https://api.lever.co/v0/postings/{company}/{job_id}")
        # Lever splits the text into an intro, titled lists (requirements, ...) and a closing part.
        lists = "".join(
            f"<h3>{x['text']}</h3><ul>{x['content']}</ul>" for x in job.get("lists", [])
        )
        html = (job.get("description") or "") + lists + (job.get("additional") or "")
        # The posting API has no company name, so the URL slug stands in for it.
        return JobCreate(
            company=company,
            title=job["text"],
            location=(job.get("categories") or {}).get("location"),
            url=f"https://jobs.lever.co/{company}/{job_id}",
            description=html_to_text(html),
        )


class AshbySource:
    hosts = frozenset({"jobs.ashbyhq.com"})
    path = re.compile(rf"/(?P<board>{SLUG})/(?P<id>{UUID})(/application)?/?")

    def matches(self, url: str) -> bool:
        return match_posting(url, self.hosts, self.path) is not None

    async def fetch(self, url: str, client: httpx.AsyncClient) -> JobCreate:
        ref = posting_ref(url, self.hosts, self.path)
        board, job_id = ref["board"], ref["id"]
        # Ashby has no single-posting endpoint: read the whole board and pick the posting out.
        data = await get_json(client, f"https://api.ashbyhq.com/posting-api/job-board/{board}")
        job = next((j for j in data["jobs"] if j["id"].lower() == job_id), None)
        if job is None:
            raise PostingNotFoundError("The job board has no such posting (it may have closed)")
        # The board API has no company name, so the board slug stands in for it.
        return JobCreate(
            company=board,
            title=job["title"],
            location=job.get("location"),
            url=f"https://jobs.ashbyhq.com/{board}/{job_id}",
            description=html_to_text(job.get("descriptionHtml") or ""),
        )


SOURCES: tuple[JobSource, ...] = (GreenhouseSource(), LeverSource(), AshbySource())


def find_source(url: str) -> JobSource:
    """Return the adapter that understands this link, or raise UnsupportedSourceError."""
    for source in SOURCES:
        if source.matches(url):
            return source
    raise UnsupportedSourceError(UNSUPPORTED)


async def fetch_posting(url: str, client: httpx.AsyncClient) -> JobCreate:
    """Fetch the posting behind a job link. The returned url is the canonical posting URL.

    A response missing expected fields (or failing validation) means the provider changed its
    format, so it is reported as an upstream error rather than a crash.
    """
    source = find_source(url)
    try:
        return await source.fetch(url, client)
    except (KeyError, TypeError, ValueError) as exc:
        raise UpstreamError("The job board returned a response in an unexpected format") from exc


class _TextExtractor(HTMLParser):
    BLOCKS = frozenset(
        {"p", "div", "br", "li", "ul", "ol", "tr", "h1", "h2", "h3", "h4", "h5", "h6"}
    )
    SKIP = frozenset({"script", "style"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skipping = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self.SKIP:
            self.skipping += 1
        elif tag in self.BLOCKS:
            self.parts.append("\n")
        if tag == "li":
            self.parts.append("- ")

    def handle_endtag(self, tag: str) -> None:
        if tag in self.SKIP:
            self.skipping = max(0, self.skipping - 1)
        elif tag in self.BLOCKS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skipping:
            self.parts.append(data)


def html_to_text(html: str) -> str | None:
    """Convert posting HTML to plain text, keeping paragraph and list breaks; None if empty.

    Uses the standard-library parser, which only reads the markup: nothing is executed or fetched.
    """
    extractor = _TextExtractor()
    extractor.feed(html)
    extractor.close()
    lines = (re.sub(r"\s+", " ", line).strip() for line in "".join(extractor.parts).splitlines())
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text or None
