"""Application entry point: builds the FastAPI app, mounts every router and maps domain errors.

Run locally with `uv run uvicorn career_catalyst.main:app --reload`.
"""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from career_catalyst.api import health, v1
from career_catalyst.config import get_settings
from career_catalyst.services import ConflictError, NotFoundError


def create_app() -> FastAPI:
    app = FastAPI(title=get_settings().app_name, version="0.2.0")
    app.include_router(health.router)
    app.include_router(v1.router)

    @app.exception_handler(NotFoundError)
    async def not_found(_: Request, exc: NotFoundError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": str(exc)})

    @app.exception_handler(ConflictError)
    async def conflict(_: Request, exc: ConflictError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_409_CONFLICT, content={"detail": str(exc)})

    return app


app = create_app()
