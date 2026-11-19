"""Contratos compartidos del análisis: evidencia, hipótesis, veredicto y decisión, validados con pydantic."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class Evidence(BaseModel):
    source: str  # nombre de la herramienta o id del documento
    kind: str  # metric | log | trace | k8s | deploy | doc | incident | error | empty (estos dos no cuentan)
    summary: str
    ref: str | None = None
    data: dict[str, Any] | None = (
        None  # salida estructurada (p. ej. deployment_status): la lee el decisor, no el LLM
    )


class Hypothesis(BaseModel):
    component: str
    reason: str
    propagation: list[str] = Field(default_factory=list)  # cadena de propagación
    evidence: list[Evidence] = Field(default_factory=list)
    proposed_action: str = "escalate"  # runbook:rollout-restart | runbook:rollout-undo | runbook:scale | pr:manifests | pr:app | escalate
    action_params: dict[str, Any] = Field(default_factory=dict)


class Verdict(BaseModel):
    confidence: float = 0.0
    supported: bool = False
    missing: list[str] = Field(default_factory=list)
    notes: str = ""


class Decision(BaseModel):
    route: str  # runbook | pr | escalate
    action: str
    params: dict[str, Any] = Field(default_factory=dict)
    reason: str = ""
