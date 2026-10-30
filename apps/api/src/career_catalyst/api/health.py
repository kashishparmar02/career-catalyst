"""Liveness and readiness probes.

/health answers as long as the process is up (used by Docker and load balancers to restart a hung
container). /ready also checks dependencies, so traffic is only routed once PostgreSQL is reachable.
"""

from collections.abc import Awaitable, Callable
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel

from career_catalyst.db import ping_database

router = APIRouter(tags=["health"])

DatabaseCheck = Callable[[], Awaitable[bool]]


def get_database_check() -> DatabaseCheck:
    return ping_database


class HealthResponse(BaseModel):
    status: Literal["ok"]


class ReadyResponse(BaseModel):
    status: Literal["ready", "unavailable"]
    database: Literal["up", "down"]


@router.get("/health")
async def health() -> HealthResponse:
    return HealthResponse(status="ok")


@router.get("/ready", responses={503: {"model": ReadyResponse}})
async def ready(
    response: Response,
    check_database: Annotated[DatabaseCheck, Depends(get_database_check)],
) -> ReadyResponse:
    if await check_database():
        return ReadyResponse(status="ready", database="up")
    response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadyResponse(status="unavailable", database="down")
