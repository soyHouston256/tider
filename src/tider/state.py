"""Estado compartido del grafo. Se guarda como dicts (serializables) y se valida con pydantic en los bordes."""
from __future__ import annotations
import operator
from typing import Annotated, Any, TypedDict
from pydantic import BaseModel, Field


class Alert(BaseModel):
    name: str
    service: str | None = None
    namespace: str = "otel-demo"
    severity: str = "warning"
    starts_at: str | None = None
    labels: dict[str, str] = Field(default_factory=dict)
    annotations: dict[str, str] = Field(default_factory=dict)


class Evidence(BaseModel):
    source: str            # nombre de la herramienta o id del documento
    kind: str              # metric | log | trace | k8s | deploy | doc | incident
    summary: str
    ref: str | None = None


class Hypothesis(BaseModel):
    component: str
    reason: str
    propagation: list[str] = Field(default_factory=list)   # cadena de propagación
    evidence: list[Evidence] = Field(default_factory=list)
    proposed_action: str = "escalate"   # runbook:rollout-restart | runbook:rollout-undo | runbook:scale | pr:manifests | pr:app | escalate
    action_params: dict[str, Any] = Field(default_factory=dict)


class Verdict(BaseModel):
    confidence: float = 0.0
    supported: bool = False
    missing: list[str] = Field(default_factory=list)
    notes: str = ""


class Decision(BaseModel):
    route: str             # runbook | pr | escalate
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""


class IncidentState(TypedDict, total=False):
    alert: dict
    handler: str
    context: list[dict]
    hypothesis: dict
    verdict: dict
    iterations: int
    decision: dict
    execution: dict
    resolved: bool
    report: str
    audit: Annotated[list[dict], operator.add]
