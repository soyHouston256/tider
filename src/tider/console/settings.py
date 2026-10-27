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
    agent_logging_transport: Literal["sdk", "mcp"] = "sdk"
    investigation_history_path: str = ""
    agent_max_steps: int = Field(default=12, ge=2, le=30)
    agent_timeout_seconds: int = Field(default=90, ge=10, le=300)
    agent_log_budget: int = Field(default=2000, ge=10, le=10000)
    agent_kube_context: str = ""
    agent_reader_kubeconfig: str = ""
    tavily_api_key: str = ""
    agent_web_enabled: bool = False
    agent_metrics_enabled: bool = False
    history_limit: int = Field(default=50, ge=1, le=100)

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        return cls(_env_file=env_file)
