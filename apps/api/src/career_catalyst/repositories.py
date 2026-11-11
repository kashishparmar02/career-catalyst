"""Data access for jobs and applications. Only this module talks SQL; services call it."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_catalyst.models import Application, Job


class JobRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, job: Job) -> Job:
        self.session.add(job)
        await self.session.flush()
        return job

    async def get(self, job_id: uuid.UUID) -> Job | None:
        return await self.session.get(Job, job_id)

    async def get_by_url(self, url: str) -> Job | None:
        return await self.session.scalar(select(Job).where(Job.url == url))

    async def list(self, limit: int, offset: int) -> list[Job]:
        rows = await self.session.scalars(
            select(Job).order_by(Job.created_at.desc(), Job.id).limit(limit).offset(offset)
        )
        return list(rows)


class ApplicationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, application: Application) -> Application:
        self.session.add(application)
        await self.session.flush()
        await self.session.refresh(application)
        return application

    async def get(self, application_id: uuid.UUID) -> Application | None:
        return await self.session.get(Application, application_id)

    async def get_by_job(self, job_id: uuid.UUID) -> Application | None:
        return await self.session.scalar(select(Application).where(Application.job_id == job_id))

    async def list(self, limit: int, offset: int) -> list[Application]:
        rows = await self.session.scalars(
            select(Application)
            .order_by(Application.updated_at.desc(), Application.id)
            .limit(limit)
            .offset(offset)
        )
        return list(rows)
