"""Configuration loaded once per application, never by a provider import."""

from pathlib import Path
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")

    evidence_mode: Literal["mock", "gcp"] = "mock"
    google_cloud_project: str = "tider-ops"
    gcp_cluster: str = "chaosforge-lab"
    gcp_location: str = "us-central1"
    gcp_namespace: str = "boutique"
    gcp_log_limit: int = Field(default=100, ge=1, le=200)
    llm_provider: Literal["none", "anthropic"] = "none"
    tider_model: str = ""
    history_limit: int = Field(default=50, ge=1, le=100)

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        return cls(_env_file=env_file)
