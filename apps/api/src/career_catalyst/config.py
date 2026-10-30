"""Typed application settings, read once from environment variables (or a local .env file)."""

from functools import lru_cache

from pydantic import PostgresDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Career Catalyst API"
    environment: str = "local"
    database_url: PostgresDsn = PostgresDsn(
        "postgresql+asyncpg://career:career@localhost:5432/career_catalyst"
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide settings; cached so the environment is parsed only once."""
    return Settings()
