"""Configuration loaded once per application, never by a provider import."""

from pathlib import Path
from typing import Literal

from pydantic import AliasChoices, Field
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
    agent_model_effort: Literal["low", "medium", "high"] | None = None
    agent_log_budget: int = Field(default=2000, ge=10, le=10000)
    agent_kube_context: str = ""
    agent_reader_kubeconfig: str = ""
    tavily_api_key: str = ""
    agent_web_enabled: bool = False
    agent_metrics_enabled: bool = False
    agent_observer_url: str = ""  # Operator-configured localhost port-forward; never model supplied.
    agent_expand_log_activity: bool = False  # Opt-in pending independent false-attribution checks.
    agent_events_enabled: bool = True
    history_limit: int = Field(default=50, ge=1, le=100)
    # Pipeline v2 (diseño piloto, Fase 1). v1 sigue siendo el valor por defecto; volver atrás es cambiar la variable.
    pipeline: Literal["v1", "v2"] = Field(default="v1", validation_alias=AliasChoices("TIDER_PIPELINE", "pipeline"))
    # Barrido: dos lecturas por servicio (A14), cada una con su cuota; el presupuesto es por servicio.
    sweep_quota_per_service: int = Field(default=40, ge=1, le=500)  # lectura severity>=WARNING
    sweep_info_quota_per_service: int = Field(default=40, ge=1, le=500)  # lectura < WARNING, solo tráfico
    sweep_timeout_seconds: int = Field(default=30, ge=5, le=120)
    healthy_traffic_min_lines: int = Field(default=3, ge=1, le=100)  # K del predicado de sano
    # Función de anomalía (A03): cubetas de la línea base, mínimo de eventos y ruido de arranque.
    anomaly_bucket_seconds: int = Field(default=30, ge=5, le=600)
    anomaly_min_events: int = Field(default=3, ge=1, le=100)
    lifecycle_grace_seconds: int = Field(default=15, ge=0, le=300)
    # Registrador de estado (solo laboratorio, A15).
    recorder_db_path: str = ""
    recorder_interval_seconds: int = Field(default=10, ge=2, le=60)
    recorder_retention_hours: int = Field(default=48, ge=1, le=168)

    @classmethod
    def from_env(cls, env_file: str | Path | None = None) -> "Settings":
        return cls(_env_file=env_file)
