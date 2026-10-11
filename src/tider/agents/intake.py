"""Agente 1 — Intake: normaliza la alerta y elige el handler (como los incident handlers de RCACopilot)."""
from __future__ import annotations
import re
from ..state import Alert, IncidentState

HANDLERS = [
    (r"oom|memory|memoria", "memory"),
    (r"crashloop|restart", "crashloop"),
    (r"imagepull", "imagepull"),
    (r"pending|unschedulable", "scheduling"),
    (r"latency|latencia|slow", "latency"),
    (r"error|5xx|failure|fail", "errors"),
    (r"cpu", "cpu"),
]


def intake(state: IncidentState, deps) -> dict:
    alert = Alert(**state["alert"])
    text = f"{alert.name} {alert.annotations.get('summary','')}".lower()
    handler = next((h for pat, h in HANDLERS if re.search(pat, text)), "generic")
    return {"handler": handler, "iterations": 0,
            "audit": [{"agent": "intake", "handler": handler, "alert": alert.name}]}
