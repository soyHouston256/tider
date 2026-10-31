"""Validated public contracts for analysis, evidence and readable decisions."""

from datetime import datetime, timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from tider.state import Decision, Hypothesis, Verdict


class Signal(BaseModel):
    id: str = ""
    timestamp: datetime
    service: str
    source: Literal["log", "metric", "trace"]
    message: str
    severity: str = "INFO"
    trace_id: str | None = None


class AnalyzeRequest(BaseModel):
    objective: str = Field(default="Investiga el incidente y determina qué evidencia falta.", max_length=2000)
    incident_id: str = Field(min_length=1, max_length=128)
    scope: Literal["focused", "general"] = "general"
    service: str | None = Field(default=None, min_length=1, max_length=63, pattern=r"^[a-z0-9](?:[-a-z0-9]*[a-z0-9])?$")
    start: datetime
    end: datetime
    mode: Literal["mock", "gcp"] | None = None
    scenario: Literal["redis_down", "cart_unavailable", "healthy", "missing_telemetry"] = "redis_down"

    @model_validator(mode="after")
    def valid_window(self):
        # Older API clients that explicitly provide a service keep their focused scope.
        # A symptom without a service starts a general investigation.
        if "scope" not in self.model_fields_set:
            self.scope = "focused" if self.service else "general"
        if self.scope == "focused" and not self.service:
            raise ValueError("Selecciona un servicio para el análisis enfocado.")
        if self.scope == "general":
            self.service = None
        if self.start.tzinfo is None or self.end.tzinfo is None:
            raise ValueError("Las fechas deben incluir zona horaria.")
        if self.start >= self.end or self.end - self.start > timedelta(hours=2):
            raise ValueError("La ventana debe ser positiva y no superar dos horas.")
        return self


class DecisionStep(BaseModel):
    sequence: int
    stage: str
    title: str
    outcome: str
    reason: str
    status: Literal["completed", "needs_review", "skipped"]
    evidence_ids: list[str] = Field(default_factory=list)


class UnscoredVerdict(BaseModel):
    confidence: None = None
    supported: bool = False
    missing: list[str] = Field(default_factory=list)
    notes: str = ""


class WorkflowResult(BaseModel):
    handler: str = "generic"
    context: list[dict] = Field(default_factory=list)
    hypothesis: Hypothesis | None = None
    verdict: Verdict | UnscoredVerdict | None = None
    decision: Decision | None = None
    execution: dict = Field(default_factory=dict)
    resolved: bool = False
    report: str = ""
    audit: list[dict] = Field(default_factory=list)


class Analysis(BaseModel):
    scope: Literal["focused", "general"] = "focused"
    incident_id: str
    hypothesis: str
    component: str
    confidence: float | None = Field(ge=0, le=1)
    evidence: list[Signal]
    recommendation: str
    status: Literal["hypothesis", "partial", "insufficient_evidence"] = "hypothesis"
    disclaimer: str = "Hipótesis para revisión humana. Sin remediación ejecutada."
    evidence_mode: Literal["mock", "gcp"] = "mock"
    engine: str = "langgraph"
    reasoning_mode: str = "rules"
    namespace: str = "boutique"
    elapsed_ms: float = 0
    run_id: str = ""
    analyzed_at: datetime | None = None
    workflow: WorkflowResult = Field(default_factory=WorkflowResult)
    investigation: dict = Field(default_factory=dict)
    decision_steps: list[DecisionStep] = Field(default_factory=list)
