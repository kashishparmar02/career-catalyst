"""Business rules for jobs and applications, independent of HTTP.

Errors are raised as domain exceptions; the API layer maps them to status codes.
"""

import uuid
from collections.abc import Mapping

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from career_catalyst.models import Application, ApplicationEvent, ApplicationStage, Job
from career_catalyst.repositories import (
    ApplicationEventRepository,
    ApplicationRepository,
    JobRepository,
)
from career_catalyst.schemas import (
    ApplicationCreate,
    ApplicationUpdate,
    JobCreate,
    StageTransition,
)

# The whole stage machine: each stage maps to the stages it may move to next.
# "interview" may repeat for another round; rejected and withdrawn are final.
ALLOWED_TRANSITIONS: Mapping[ApplicationStage, frozenset[ApplicationStage]] = {
    ApplicationStage.SAVED: frozenset({ApplicationStage.APPLIED, ApplicationStage.WITHDRAWN}),
    ApplicationStage.APPLIED: frozenset(
        {
            ApplicationStage.ASSESSMENT,
            ApplicationStage.INTERVIEW,
            ApplicationStage.OFFER,
            ApplicationStage.REJECTED,
            ApplicationStage.WITHDRAWN,
        }
    ),
    ApplicationStage.ASSESSMENT: frozenset(
        {ApplicationStage.INTERVIEW, ApplicationStage.REJECTED, ApplicationStage.WITHDRAWN}
    ),
    ApplicationStage.INTERVIEW: frozenset(
        {
            ApplicationStage.INTERVIEW,
            ApplicationStage.OFFER,
            ApplicationStage.REJECTED,
            ApplicationStage.WITHDRAWN,
        }
    ),
    ApplicationStage.OFFER: frozenset({ApplicationStage.WITHDRAWN}),
    ApplicationStage.REJECTED: frozenset(),
    ApplicationStage.WITHDRAWN: frozenset(),
}


class NotFoundError(Exception):
    pass


class ConflictError(Exception):
    pass


class InvalidTransitionError(Exception):
    def __init__(self, current: ApplicationStage, requested: ApplicationStage) -> None:
        # Listed in enum order (saved first), not set order, so the message is stable.
        allowed = [s.value for s in ApplicationStage if s in ALLOWED_TRANSITIONS[current]]
        super().__init__(
            f"Cannot move an application from {current.value} to {requested.value}. "
            f"Allowed next stages: {', '.join(allowed) or 'none (final stage)'}"
        )


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
        self.events = ApplicationEventRepository(session)

    async def create(self, data: ApplicationCreate) -> Application:
        """Start tracking a job (stage "saved") and record that as the first history event.

        Only one application per job is allowed.
        """
        if await self.jobs.get(data.job_id) is None:
            raise NotFoundError(f"Job {data.job_id} not found")
        if await self.applications.get_by_job(data.job_id):
            raise ConflictError(f"An application for job {data.job_id} already exists")
        application = Application(**data.model_dump())
        try:
            await self.applications.add(application)
            await self.events.add(
                ApplicationEvent(application_id=application.id, to_stage=application.stage)
            )
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

    async def transition(self, application_id: uuid.UUID, data: StageTransition) -> Application:
        """Move an application to a new stage and record the move in its history.

        The row is locked (SELECT ... FOR UPDATE) before validating, so concurrent transitions
        run one at a time and each validates against the stage the previous one left behind.
        """
        application = await self.applications.get_for_update(application_id)
        if application is None:
            raise NotFoundError(f"Application {application_id} not found")
        if data.to not in ALLOWED_TRANSITIONS[application.stage]:
            raise InvalidTransitionError(application.stage, data.to)
        await self.events.add(
            ApplicationEvent(
                application_id=application.id,
                from_stage=application.stage,
                to_stage=data.to,
                note=data.note,
            )
        )
        application.stage = data.to
        await self.session.commit()
        await self.session.refresh(application)
        return application

    async def list_events(self, application_id: uuid.UUID) -> list[ApplicationEvent]:
        """Return the stage history of one application, oldest first."""
        await self.get(application_id)
        return await self.events.list_for_application(application_id)

    async def list(self, limit: int, offset: int) -> list[Application]:
        return await self.applications.list(limit, offset)
