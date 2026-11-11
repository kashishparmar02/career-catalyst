"""Shared fixtures. Database tests run against a real PostgreSQL migrated to head with Alembic,
and are skipped when DATABASE_URL is not set."""

import os
import subprocess
import sys
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from career_catalyst.db import get_engine
from career_catalyst.main import create_app

API_DIR = Path(__file__).resolve().parents[1]

requires_db = pytest.mark.skipif(
    "DATABASE_URL" not in os.environ, reason="needs a running PostgreSQL"
)


@pytest.fixture(scope="session")
def migrated() -> None:
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=API_DIR, check=True)


@pytest.fixture
async def client(migrated: None) -> AsyncIterator[AsyncClient]:
    async with get_engine().begin() as conn:
        await conn.execute(text("TRUNCATE application_events, applications, jobs"))
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as c:
        yield c
