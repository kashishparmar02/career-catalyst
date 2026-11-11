"""Business rules for jobs and applications, independent of HTTP.

Errors are raised as domain exceptions; the API layer maps them to status codes.
"""

import uuid

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from career_catalyst.models import Application, Job
from career_catalyst.repositories import ApplicationRepository, JobRepository
from career_catalyst.schemas import ApplicationCreate, ApplicationUpdate, JobCreate


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class JobService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = JobRepository(session)

    async def create(self, data: JobCreate) -> Job:
        """Store a new posting. The same URL twice is a conflict, enforced by the unique index."""
        url = str(data.url)
        if await self.jobs.get_by_url(url):
            raise ConflictError(f"A job with URL {url} already exists")
        job = Job(**data.model_dump(exclude={"url"}), url=url)
        try:
            await self.jobs.add(job)
            await self.session.commit()
        except IntegrityError as exc:
            # Lost a race with a concurrent insert of the same URL.
            await self.session.rollback()
            raise ConflictError(f"A job with URL {url} already exists") from exc
        await self.session.refresh(job)
        return job

    async def get(self, job_id: uuid.UUID) -> Job:
        job = await self.jobs.get(job_id)
        if job is None:
            raise NotFoundError(f"Job {job_id} not found")
        return job

    async def list(self, limit: int, offset: int) -> list[Job]:
        return await self.jobs.list(limit, offset)


class ApplicationService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.jobs = JobRepository(session)
        self.applications = ApplicationRepository(session)

    async def create(self, data: ApplicationCreate) -> Application:
        """Start tracking a job (stage "saved"). Only one application per job is allowed."""
        if await self.jobs.get(data.job_id) is None:
            raise NotFoundError(f"Job {data.job_id} not found")
        if await self.applications.get_by_job(data.job_id):
            raise ConflictError(f"An application for job {data.job_id} already exists")
        application = Application(**data.model_dump())
        try:
            await self.applications.add(application)
            await self.session.commit()
        except IntegrityError as exc:
            await self.session.rollback()
            raise ConflictError(f"An application for job {data.job_id} already exists") from exc
        await self.session.refresh(application)
        return application

    async def get(self, application_id: uuid.UUID) -> Application:
        application = await self.applications.get(application_id)
        if application is None:
            raise NotFoundError(f"Application {application_id} not found")
        return application

    async def update(self, application_id: uuid.UUID, data: ApplicationUpdate) -> Application:
        """Update free-text fields. Only fields present in the request are changed."""
        application = await self.get(application_id)
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(application, field, value)
        await self.session.commit()
        await self.session.refresh(application)
        return application

    async def list(self, limit: int, offset: int) -> list[Application]:
        return await self.applications.list(limit, offset)
