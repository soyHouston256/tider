"""Webhook de Alertmanager + ingesta del lake. Ejecutar: uvicorn tider.api:app
Todo menos /healthz exige `Authorization: Bearer $TIDER_API_TOKEN` (en Alertmanager: webhook_configs.http_config.authorization)."""

from __future__ import annotations

import json
import os
import secrets
import threading
from collections import deque

from fastapi import BackgroundTasks, Depends, FastAPI, Header, HTTPException

from .agents.deps import Deps
from .config import ROOT, env
from .decision.policy import load_policy
from .graph import build_graph, run_alert
from .lake.ingest import ingest_dir
from .lake.store import InMemoryStore, PgVectorStore
from .llm import AnthropicLLM
from .tools import default_registry

DOCS = (ROOT / "docs").resolve()
app = FastAPI(title="Tider")
_lock = threading.Lock()
_graph = None
_deps: Deps | None = None
RESULTS: deque[dict] = deque(maxlen=200)  # solo los últimos; el registro completo está en out/ y en los logs


def _init():
    global _graph, _deps
    with _lock:
        if _graph is None:
            store = (
                PgVectorStore(env("DATABASE_URL"))
                if env("DATABASE_URL") and os.getenv("TIDER_STORE") == "pg"
                else InMemoryStore()
            )
            ingest_dir(store, DOCS, base=ROOT)
            judge_model = env("TIDER_JUDGE_MODEL")
            _deps = Deps(
                AnthropicLLM(),
                store,
                default_registry(),
                load_policy(),
                judge_llm=AnthropicLLM(model=judge_model) if judge_model else None,
            )
            _graph = build_graph(_deps)
    return _graph


def require_token(authorization: str = Header(default="")):
    token = env("TIDER_API_TOKEN")
    if not token:
        raise HTTPException(503, "Define TIDER_API_TOKEN: la API no acepta peticiones sin autenticación.")
    if not secrets.compare_digest(authorization.encode(), f"Bearer {token}".encode()):
        raise HTTPException(401, "token inválido")


def _to_alert(a: dict) -> dict:
    labels = a.get("labels", {})
    return {
        "name": labels.get("alertname", "unknown"),
        "service": labels.get("service")
        or labels.get("service_name")
        or labels.get("deployment")
        or labels.get("container"),
        "namespace": labels.get("namespace", "otel-demo"),
        "severity": labels.get("severity", "warning"),
        "starts_at": a.get("startsAt"),
        "fingerprint": a.get("fingerprint"),
        "labels": labels,
        "annotations": a.get("annotations", {}),
    }


def _key(a: dict) -> str:
    return a.get("fingerprint") or json.dumps(a.get("labels", {}), sort_keys=True)


def _process(alert: dict):
    final = run_alert(_init(), alert)  # run_alert ya escala si el flujo falla
    RESULTS.append(
        {
            k: final.get(k)
            for k in ("alert", "hypothesis", "verdict", "decision", "execution", "resolved", "error", "audit")
        }
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/webhook/alertmanager", dependencies=[Depends(require_token)])
def alertmanager(payload: dict, bg: BackgroundTasks):
    _init()
    firing = [a for a in payload.get("alerts", []) if a.get("status") == "firing"]
    accepted = [
        a for a in firing if _deps.safety.claim_alert(_key(a))
    ]  # Alertmanager reenvía: una vez por ventana
    for a in accepted:
        bg.add_task(_process, _to_alert(a))
    return {"accepted": len(accepted), "deduplicated": len(firing) - len(accepted)}


@app.post("/lake/ingest", dependencies=[Depends(require_token)])
def lake_ingest(path: str = "docs"):
    _init()
    target = (ROOT / path).resolve()
    if not target.is_relative_to(DOCS):  # solo docs/: nada de rutas arbitrarias del servidor dentro del lake
        raise HTTPException(400, "path debe estar dentro de docs/")
    return {"ingested": ingest_dir(_deps.store, target, base=ROOT)}


@app.get("/incidents", dependencies=[Depends(require_token)])
def incidents():
    return list(RESULTS)
