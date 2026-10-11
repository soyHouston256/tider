"""Webhook de Alertmanager + ingesta del lake. Ejecutar: uvicorn tider.api:app"""
from __future__ import annotations
import os
from fastapi import BackgroundTasks, FastAPI
from .agents.deps import Deps
from .config import ROOT, env
from .decision.policy import load_policy
from .graph import build_graph, run_alert
from .lake.ingest import ingest_dir
from .lake.store import InMemoryStore, PgVectorStore
from .llm import AnthropicLLM
from .tools import default_registry

app = FastAPI(title="Tider")
_graph = None
_store = None
RESULTS: list[dict] = []


def _init():
    global _graph, _store
    if _graph is None:
        _store = PgVectorStore(env("DATABASE_URL")) if env("DATABASE_URL") and os.getenv("TIDER_STORE") == "pg" else InMemoryStore()
        ingest_dir(_store, ROOT / "docs")
        _graph = build_graph(Deps(AnthropicLLM(), _store, default_registry(), load_policy()))
    return _graph


def _to_alert(a: dict) -> dict:
    l = a.get("labels", {})
    return {"name": l.get("alertname", "unknown"), "service": l.get("service") or l.get("deployment"),
            "namespace": l.get("namespace", "otel-demo"), "severity": l.get("severity", "warning"),
            "starts_at": a.get("startsAt"), "labels": l, "annotations": a.get("annotations", {})}


def _process(alert: dict):
    final = run_alert(_init(), alert)
    RESULTS.append({k: final.get(k) for k in ("alert", "hypothesis", "verdict", "decision", "execution", "resolved", "audit")})


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/webhook/alertmanager")
def alertmanager(payload: dict, bg: BackgroundTasks):
    firing = [a for a in payload.get("alerts", []) if a.get("status") == "firing"]
    for a in firing:
        bg.add_task(_process, _to_alert(a))
    return {"accepted": len(firing)}


@app.post("/lake/ingest")
def lake_ingest(path: str = "docs"):
    _init()
    return {"ingested": ingest_dir(_store, ROOT / path)}


@app.get("/incidents")
def incidents():
    return RESULTS
