import asyncio
import uuid
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from career_catalyst.main import create_app
from career_catalyst.models import Application
from career_catalyst.repositories import ApplicationRepository
from tests.conftest import requires_db

pytestmark = [pytest.mark.integration, requires_db]


async def create_application(client: AsyncClient) -> dict[str, Any]:
    job = await client.post(
        "/api/v1/jobs",
        json={"company": "Acme", "title": "Engineer", "url": "https://jobs.example.com/acme/1"},
    )
    response = await client.post("/api/v1/applications", json={"job_id": job.json()["id"]})
    assert response.status_code == 201, response.text
    return response.json()


async def move(client: AsyncClient, application_id: str, to: str, note: str | None = None) -> Any:
    return await client.post(
        f"/api/v1/applications/{application_id}/transitions", json={"to": to, "note": note}
    )


async def test_full_path_to_offer_is_recorded_in_order(client: AsyncClient) -> None:
    application = await create_application(client)
    path = [
        ("applied", "Sent CV"),
        ("interview", "Round 1"),
        ("interview", "Round 2"),
        ("offer", None),
    ]
    for to, note in path:
        response = await move(client, application["id"], to, note)
        assert response.status_code == 200, response.text
        assert response.json()["stage"] == to

    events = (await client.get(f"/api/v1/applications/{application['id']}/events")).json()
    assert [(e["from_stage"], e["to_stage"], e["note"]) for e in events] == [
        (None, "saved", None),
        ("saved", "applied", "Sent CV"),
        ("applied", "interview", "Round 1"),
        ("interview", "interview", "Round 2"),
        ("interview", "offer", None),
    ]


async def test_skipping_stages_is_rejected_with_allowed_list(client: AsyncClient) -> None:
    application = await create_application(client)
    response = await move(client, application["id"], "offer")
    assert response.status_code == 422
    assert "Allowed next stages: applied, withdrawn" in response.json()["detail"]
    current = await client.get(f"/api/v1/applications/{application['id']}")
    assert current.json()["stage"] == "saved"


async def test_final_stage_blocks_further_transitions(client: AsyncClient) -> None:
    application = await create_application(client)
    assert (await move(client, application["id"], "withdrawn")).status_code == 200
    response = await move(client, application["id"], "applied")
    assert response.status_code == 422
    assert "none (final stage)" in response.json()["detail"]


async def test_unknown_stage_is_rejected(client: AsyncClient) -> None:
    application = await create_application(client)
    assert (await move(client, application["id"], "hired")).status_code == 422


async def test_unknown_application_is_404(client: AsyncClient) -> None:
    missing = uuid.uuid4()
    assert (await move(client, str(missing), "applied")).status_code == 404
    assert (await client.get(f"/api/v1/applications/{missing}/events")).status_code == 404


async def test_concurrent_transitions_apply_only_once(
    client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    application = await create_application(client)
    await move(client, application["id"], "applied")

    # Pause after reading the row so both requests are guaranteed to overlap. Without the row
    # lock both would read "applied" here and both would commit.
    read = ApplicationRepository.get_for_update

    async def slow_read(
        self: ApplicationRepository, application_id: uuid.UUID
    ) -> Application | None:
        row = await read(self, application_id)
        await asyncio.sleep(0.2)
        return row

    monkeypatch.setattr(ApplicationRepository, "get_for_update", slow_read)

    # Two independent clients, so each request gets its own database session and connection.
    # Both target a final stage: whichever commits first, the other must see it and be refused.
    async with (
        AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as a,
        AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as b,
    ):
        results = await asyncio.gather(
            move(a, application["id"], "rejected"), move(b, application["id"], "withdrawn")
        )

    assert sorted(r.status_code for r in results) == [200, 422]
    events = (await client.get(f"/api/v1/applications/{application['id']}/events")).json()
    assert len(events) == 3
    winner = next(r for r in results if r.status_code == 200).json()["stage"]
    assert events[-1]["to_stage"] == winner
