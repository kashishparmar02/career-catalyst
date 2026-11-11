"""Request and response shapes for the public API (validated at the HTTP boundary)."""

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, HttpUrl

from career_catalyst.models import ApplicationStage


class JobCreate(BaseModel):
    company: str = Field(min_length=1, max_length=200)
    title: str = Field(min_length=1, max_length=300)
    location: str | None = Field(default=None, max_length=300)
    url: HttpUrl
    description: str | None = None


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    company: str
    title: str
    location: str | None
    url: str
    description: str | None
    created_at: datetime


class ApplicationCreate(BaseModel):
    job_id: uuid.UUID
    referred_by: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class ApplicationUpdate(BaseModel):
    referred_by: str | None = Field(default=None, max_length=200)
    notes: str | None = None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    job_id: uuid.UUID
    stage: ApplicationStage
    referred_by: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class StageTransition(BaseModel):
    to: ApplicationStage
    note: str | None = None


class ApplicationEventRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    application_id: uuid.UUID
    from_stage: ApplicationStage | None
    to_stage: ApplicationStage
    note: str | None
    occurred_at: datetime


class Page[T](BaseModel):
    items: list[T]
    limit: int
    offset: int
