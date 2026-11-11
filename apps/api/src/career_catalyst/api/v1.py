"""Version 1 of the public REST API: jobs and applications."""

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from career_catalyst.db import get_session
from career_catalyst.schemas import (
    ApplicationCreate,
    ApplicationRead,
    ApplicationUpdate,
    JobCreate,
    JobRead,
    Page,
)
from career_catalyst.services import ApplicationService, JobService

router = APIRouter(prefix="/api/v1")

Session = Annotated[AsyncSession, Depends(get_session)]
Limit = Annotated[int, Query(ge=1, le=100)]
Offset = Annotated[int, Query(ge=0)]


@router.post("/jobs", status_code=status.HTTP_201_CREATED, tags=["jobs"])
async def create_job(data: JobCreate, session: Session) -> JobRead:
    return JobRead.model_validate(await JobService(session).create(data))


@router.get("/jobs", tags=["jobs"])
async def list_jobs(session: Session, limit: Limit = 20, offset: Offset = 0) -> Page[JobRead]:
    jobs = await JobService(session).list(limit, offset)
    return Page(items=[JobRead.model_validate(j) for j in jobs], limit=limit, offset=offset)


@router.get("/jobs/{job_id}", tags=["jobs"])
async def get_job(job_id: uuid.UUID, session: Session) -> JobRead:
    return JobRead.model_validate(await JobService(session).get(job_id))


@router.post("/applications", status_code=status.HTTP_201_CREATED, tags=["applications"])
async def create_application(data: ApplicationCreate, session: Session) -> ApplicationRead:
    return ApplicationRead.model_validate(await ApplicationService(session).create(data))


@router.get("/applications", tags=["applications"])
async def list_applications(
    session: Session, limit: Limit = 20, offset: Offset = 0
) -> Page[ApplicationRead]:
    apps = await ApplicationService(session).list(limit, offset)
    return Page(items=[ApplicationRead.model_validate(a) for a in apps], limit=limit, offset=offset)


@router.get("/applications/{application_id}", tags=["applications"])
async def get_application(application_id: uuid.UUID, session: Session) -> ApplicationRead:
    return ApplicationRead.model_validate(await ApplicationService(session).get(application_id))


@router.patch("/applications/{application_id}", tags=["applications"])
async def update_application(
    application_id: uuid.UUID, data: ApplicationUpdate, session: Session
) -> ApplicationRead:
    application = await ApplicationService(session).update(application_id, data)
    return ApplicationRead.model_validate(application)
