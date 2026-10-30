import os

import pytest
from httpx import ASGITransport, AsyncClient

from career_catalyst.api.health import get_database_check
from career_catalyst.main import create_app


def client_with_database(up: bool) -> AsyncClient:
    app = create_app()

    async def fake_check() -> bool:
        return up

    app.dependency_overrides[get_database_check] = lambda: fake_check
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def test_health_is_ok_without_database() -> None:
    async with client_with_database(up=False) as client:
        response = await client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


async def test_ready_when_database_is_up() -> None:
    async with client_with_database(up=True) as client:
        response = await client.get("/ready")
    assert response.status_code == 200
    assert response.json() == {"status": "ready", "database": "up"}


async def test_ready_returns_503_when_database_is_down() -> None:
    async with client_with_database(up=False) as client:
        response = await client.get("/ready")
    assert response.status_code == 503
    assert response.json() == {"status": "unavailable", "database": "down"}


@pytest.mark.integration
@pytest.mark.skipif("DATABASE_URL" not in os.environ, reason="needs a running PostgreSQL")
async def test_ready_against_real_database() -> None:
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/ready")
    assert response.status_code == 200
