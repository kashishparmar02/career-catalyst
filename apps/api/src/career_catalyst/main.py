"""Application entry point: builds the FastAPI app and mounts every router.

Run locally with `uv run uvicorn career_catalyst.main:app --reload`.
"""

from fastapi import FastAPI

from career_catalyst.api import health
from career_catalyst.config import get_settings


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version="0.1.0")
    app.include_router(health.router)
    return app


app = create_app()
