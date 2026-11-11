"""Database tables for job postings and the applications made to them.

A Job is a posting as published by a company (stored once, however many times it is seen).
An Application is the user's progress on one Job; its stage changes over time.
An ApplicationEvent is one recorded stage change, so the full history of an application is kept.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, Enum, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ApplicationStage(enum.StrEnum):
    SAVED = "saved"
    APPLIED = "applied"
    ASSESSMENT = "assessment"
    INTERVIEW = "interview"
    OFFER = "offer"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


# One PostgreSQL enum type, shared by every column that stores a stage.
stage_type = Enum(
    ApplicationStage,
    name="application_stage",
    values_callable=lambda e: [m.value for m in e],
)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    company: Mapped[str] = mapped_column(String(200))
    title: Mapped[str] = mapped_column(String(300))
    location: Mapped[str | None] = mapped_column(String(300))
    url: Mapped[str] = mapped_column(String(2048), unique=True)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    applications: Mapped[list["Application"]] = relationship(back_populates="job")


class Application(Base):
    __tablename__ = "applications"
    # One application per job: applying twice to the same posting is a mistake, not a feature.
    __table_args__ = (UniqueConstraint("job_id", name="uq_applications_job_id"),)

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    job_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("jobs.id", ondelete="CASCADE"))
    stage: Mapped[ApplicationStage] = mapped_column(stage_type, default=ApplicationStage.SAVED)
    referred_by: Mapped[str | None] = mapped_column(String(200))
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    job: Mapped[Job] = relationship(back_populates="applications")


class ApplicationEvent(Base):
    __tablename__ = "application_events"
    __table_args__ = (
        Index("ix_application_events_application_id_occurred_at", "application_id", "occurred_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(primary_key=True, default=uuid.uuid4)
    application_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("applications.id", ondelete="CASCADE")
    )
    # Null only for the first event, when the application is created.
    from_stage: Mapped[ApplicationStage | None] = mapped_column(stage_type)
    to_stage: Mapped[ApplicationStage] = mapped_column(stage_type)
    note: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
