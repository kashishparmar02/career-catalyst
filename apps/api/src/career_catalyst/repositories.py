"""Data access for jobs, applications and stage history. Only this module talks SQL."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from career_catalyst.models import Application, ApplicationEvent, Job


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

    async def get_for_update(self, application_id: uuid.UUID) -> Application | None:
        """Fetch and lock the row until the transaction ends, so concurrent writers queue up.

        populate_existing makes sure the stage is re-read after waiting for the lock, not taken
        from an object the session already held.
        """
        return await self.session.scalar(
            select(Application)
            .where(Application.id == application_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

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


class ApplicationEventRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def add(self, event: ApplicationEvent) -> ApplicationEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def list_for_application(self, application_id: uuid.UUID) -> list[ApplicationEvent]:
        rows = await self.session.scalars(
            select(ApplicationEvent)
            .where(ApplicationEvent.application_id == application_id)
            .order_by(ApplicationEvent.occurred_at, ApplicationEvent.id)
        )
        return list(rows)
