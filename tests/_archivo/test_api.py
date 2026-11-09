"""API: autenticación, deduplicación de reenvíos de Alertmanager e ingesta limitada a docs/."""

from collections import deque
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tider import api
from tider.agents.deps import Deps
from tider.decision.policy import load_policy
from tider.graph import build_graph
from tider.lake.ingest import ingest_dir
from tider.lake.store import InMemoryStore
from tider.llm import ScriptedLLM
from tider.tools.base import ToolRegistry

ROOT = Path(__file__).resolve().parents[1]
PAYLOAD = {
    "alerts": [
        {
            "status": "firing",
            "fingerprint": "abc123",
            "startsAt": "2026-10-11T14:00:00Z",
            "labels": {"alertname": "HighMemoryUsage", "service": "recommendation", "namespace": "otel-demo"},
            "annotations": {"summary": "memoria alta"},
        },
        {"status": "resolved", "fingerprint": "zzz", "labels": {"alertname": "Otra"}},
    ]
}


@pytest.fixture
def client(monkeypatch):
    store = InMemoryStore()
    ingest_dir(store, ROOT / "docs")
    deps = Deps(
        ScriptedLLM(
            {
                "investigator": {
                    "action": "final",
                    "hypothesis": {"component": "recommendation", "reason": "x"},
                },
                "judge": {"supported": False, "confidence": 0.1},
                "reporter": "r",
            }
        ),
        store,
        ToolRegistry(),
        load_policy(),
    )
    monkeypatch.setattr(api, "_deps", deps)
    monkeypatch.setattr(api, "_graph", build_graph(deps))
    monkeypatch.setattr(api, "RESULTS", deque(maxlen=200))
    return TestClient(api.app)


def test_api_requires_a_configured_token(client, monkeypatch):
    assert client.get("/healthz").status_code == 200
    assert (
        client.post("/webhook/alertmanager", json=PAYLOAD).status_code == 503
    )  # sin token configurado no abre
    monkeypatch.setenv("TIDER_API_TOKEN", "s3creto")
    assert (
        client.post(
            "/webhook/alertmanager", json=PAYLOAD, headers={"Authorization": "Bearer otro"}
        ).status_code
        == 401
    )
    assert client.get("/incidents").status_code == 401


def test_webhook_processes_once_per_window(client, monkeypatch):
    monkeypatch.setenv("TIDER_API_TOKEN", "s3creto")
    auth = {"Authorization": "Bearer s3creto"}
    assert client.post("/webhook/alertmanager", json=PAYLOAD, headers=auth).json() == {
        "accepted": 1,
        "deduplicated": 0,
    }
    assert client.post("/webhook/alertmanager", json=PAYLOAD, headers=auth).json() == {
        "accepted": 0,
        "deduplicated": 1,
    }
    incidents = client.get("/incidents", headers=auth).json()
    assert len(incidents) == 1 and incidents[0]["alert"]["fingerprint"] == "abc123"
    assert incidents[0]["decision"]["route"] == "escalate"


def test_ingest_only_from_docs(client, monkeypatch):
    monkeypatch.setenv("TIDER_API_TOKEN", "s3creto")
    auth = {"Authorization": "Bearer s3creto"}
    for path in ("/etc", "docs/../src", ".."):
        assert client.post("/lake/ingest", params={"path": path}, headers=auth).status_code == 400, path
    assert client.post("/lake/ingest", params={"path": "docs/runbooks"}, headers=auth).json() == {
        "ingested": 4
    }
    assert (
        "docs/runbooks/cpu-alta.md" in api._deps.store.docs
    )  # mismo doc_id que la ingesta inicial: no duplica
