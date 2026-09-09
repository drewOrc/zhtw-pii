"""Runtime configuration, loaded from environment variables and .env."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Project-wide settings shared by the data, train, and eval commands."""

    model_config = SettingsConfigDict(env_prefix="ZHTW_PII_", env_file=".env", extra="ignore")

    seed: int = 42
    data_dir: Path = Path("data")
    anthropic_api_key: str | None = Field(default=None, validation_alias="ANTHROPIC_API_KEY")


def get_settings() -> Settings:
    """Load Settings from the current environment and .env file."""
    return Settings()
