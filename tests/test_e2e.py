"""Flujo completo con LLM simulado y telemetría grabada (sin clúster, sin red)."""
import json
from datetime import date, timedelta
from pathlib import Path
from tider.agents.deps import Deps
from tider.decision.policy import load_policy
from tider.graph import build_graph, run_alert
from tider.lake.ingest import ingest_dir
from tider.lake.models import Chunk, Doc
from tider.lake.store import InMemoryStore
from tider.llm import ScriptedLLM
from tider.tools.base import FixtureRegistry

ROOT = Path(__file__).resolve().parents[1]
ALERT = {"name": "HighMemoryUsage", "service": "recommendation", "namespace": "otel-demo",
         "annotations": {"summary": "memoria alta en recommendation"}}


def make(script, **kw):
    store = InMemoryStore(); ingest_dir(store, ROOT / "docs")
    tools = FixtureRegistry(ROOT / "eval/fixtures/memory_leak_recommendation.json")
    llm = ScriptedLLM(script)
    return build_graph(Deps(llm, store, tools, load_policy(), **kw)), llm, store


def final(action="runbook:rollout-restart", docs=("docs/runbooks/memoria-oomkilled.md",)):
    return {"action": "final", "hypothesis": {"component": "recommendation", "reason": "fuga de memoria (OOMKilled)",
            "propagation": ["recommendation", "frontend"], "proposed_action": action,
            "action_params": {"deployment": "recommendation"}, "cited_docs": list(docs)}}


TOOL1 = {"action": "tool", "tool": "prom_range", "args": {"query": "memoria"}}
TOOL2 = {"action": "tool", "tool": "kube_events", "args": {}}


def test_happy_path_restarts_in_dry_run(monkeypatch):
    monkeypatch.setenv("TIDER_DRY_RUN", "true")
    g, llm, store = make({"investigator": [TOOL1, TOOL2, final()],
                          "judge": {"supported": True, "confidence": 0.9, "missing": [], "notes": "ok"},
                          "reporter": "# Postmortem"})
    out = run_alert(g, ALERT)
    assert out["handler"] == "memory"
    assert out["decision"]["route"] == "runbook" and out["decision"]["action"] == "rollout-restart"
    assert out["execution"]["dry_run"] and "rollout restart deployment/recommendation" in out["execution"]["command"]
    assert any(d.startswith("incident://") for d in store.docs)      # el incidente se aprende
    assert any(a["agent"] == "decisor" for a in out["audit"])
    assert any(e["kind"] == "doc" for e in out["hypothesis"]["evidence"])   # la cita al runbook se resolvió


def test_judge_rejects_then_loop_then_escalates():
    g, llm, _ = make({"investigator": [TOOL1, final(), TOOL2, final()],
                      "judge": [{"supported": False, "confidence": 0.4, "missing": ["eventos de k8s"]},
                                {"supported": False, "confidence": 0.4, "missing": ["eventos de k8s"]},
                                {"supported": False, "confidence": 0.4, "missing": ["eventos de k8s"]}],
                      "reporter": "r"})
    out = run_alert(g, ALERT)
    assert out["decision"]["route"] == "escalate"
    assert sum(1 for a in out["audit"] if a["agent"] == "judge") >= 2   # hubo re-investigación


def test_judge_cap_no_telemetry_evidence():
    g, _, _ = make({"investigator": [final()],
                    "judge": {"supported": True, "confidence": 0.99, "missing": []}, "reporter": "r"})
    out = run_alert(g, ALERT)   # sin herramientas -> solo docs -> el juez determinista lo baja y el decisor escala
    assert out["verdict"]["supported"] is False and out["decision"]["route"] == "escalate"


def test_llm_cannot_bypass_allowlist():
    g, _, _ = make({"investigator": [TOOL1, TOOL2, final("runbook:delete-namespace")],
                    "judge": {"supported": True, "confidence": 1.0, "missing": []}, "reporter": "r"})
    assert run_alert(g, ALERT)["decision"]["route"] == "escalate"


def test_stale_docs_lower_confidence():
    g, _, store = make({"investigator": [TOOL1, TOOL2, final()],
                        "judge": {"supported": True, "confidence": 0.95, "missing": []}, "reporter": "r"})
    old = date.today() - timedelta(days=400)
    d = store.docs["docs/runbooks/memoria-oomkilled.md"]; d.updated = old
    out = run_alert(g, ALERT)
    assert out["verdict"]["confidence"] <= 0.9 and "desactualizado" in out["verdict"]["notes"]


def test_no_rag_variant_has_no_context():
    g, _, _ = make({"investigator": [TOOL1, TOOL2, final(docs=())],
                    "judge": {"supported": True, "confidence": 0.9, "missing": []}, "reporter": "r"}, use_rag=False)
    assert run_alert(g, ALERT)["context"] == []
