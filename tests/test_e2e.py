"""Flujo completo con LLM simulado y telemetría grabada (sin clúster, sin red)."""
from datetime import date, timedelta
from pathlib import Path
from tider import graph as graph_mod
from tider.agents.deps import Deps
from tider.decision.policy import load_policy
from tider.graph import build_graph, run_alert
from tider.lake.ingest import ingest_dir
from tider.lake.store import InMemoryStore
from tider.llm import ScriptedLLM
from tider.tools.base import FixtureRegistry, Tool, ToolRegistry

ROOT = Path(__file__).resolve().parents[1]
ALERT = {"name": "HighMemoryUsage", "service": "recommendation", "namespace": "otel-demo",
         "annotations": {"summary": "memoria alta en recommendation"}}
SUPPORTED = {"supported": True, "confidence": 0.9, "missing": [], "notes": "ok"}


def make(script, fixture="memory_leak_recommendation", tools=None, **kw):
    store = InMemoryStore(); ingest_dir(store, ROOT / "docs")
    tools = tools or FixtureRegistry(ROOT / f"eval/fixtures/{fixture}.json")
    llm = ScriptedLLM(script)
    deps = Deps(llm, store, tools, load_policy(), **kw)
    return build_graph(deps), llm, store


def final(action="runbook:rollout-restart", docs=("docs/runbooks/memoria-oomkilled.md",), component="recommendation",
          propagation=("recommendation", "frontend"), params=None):
    return {"action": "final", "hypothesis": {"component": component, "reason": "fuga de memoria (OOMKilled)",
            "propagation": list(propagation), "proposed_action": action,
            "action_params": params or {"deployment": component}, "cited_docs": list(docs)}}


def tool(tool_name, /, **args):
    return {"action": "tool", "tool": tool_name, "args": args}


TOOL1 = tool("prom_range", query="container_memory_working_set_bytes{pod=~'recommendation.*'}")
TOOL2 = tool("kube_events")
TOOL3 = tool("kube_describe", kind="pod", name="recommendation-7c9d8f6b4-kx2lp")   # arg "name": antes tumbaba el flujo


def escalations(out_dir: Path) -> list[Path]:
    return sorted((out_dir / "escalations").glob("*.json"))


def test_happy_path_dry_run_notifies_a_person_and_learns_nothing(isolated_env):
    g, llm, store = make({"investigator": [TOOL1, TOOL2, TOOL3, final()], "judge": SUPPORTED, "reporter": "# Postmortem"})
    out = run_alert(g, ALERT)
    assert out["handler"] == "memory"
    assert out["decision"]["route"] == "runbook" and out["decision"]["action"] == "rollout-restart"
    assert out["execution"]["dry_run"] and "rollout restart deployment/recommendation" in out["execution"]["command"]
    assert len(escalations(isolated_env)) == 1                       # modo sombra: alguien ve el comando propuesto
    assert not any(d.startswith("incident://") for d in store.docs)  # sin verificar no se aprende
    assert any(e["kind"] == "doc" for e in out["hypothesis"]["evidence"])   # la cita al runbook se resolvió


def test_verified_incident_is_learned(monkeypatch):
    monkeypatch.setattr(graph_mod.runbook, "execute",
                        lambda a, p, ns: {"executed": True, "dry_run": False, "command": "kubectl rollout restart"})
    monkeypatch.setattr(graph_mod.verify, "verify_resolved", lambda alert, dep=None: True)
    g, _, store = make({"investigator": [TOOL1, TOOL2, final()], "judge": SUPPORTED, "reporter": "r"})
    out = run_alert(g, ALERT)
    assert out["resolved"] is True and any(d.startswith("incident://") for d in store.docs)


def test_executed_but_unresolved_escalates(monkeypatch, isolated_env):
    monkeypatch.setattr(graph_mod.runbook, "execute",
                        lambda a, p, ns: {"executed": True, "dry_run": False, "command": "kubectl rollout restart"})
    monkeypatch.setattr(graph_mod.verify, "verify_resolved", lambda alert, dep=None: False)
    g, _, _ = make({"investigator": [TOOL1, TOOL2, final()], "judge": SUPPORTED, "reporter": "r"})
    out = run_alert(g, ALERT)
    assert out["resolved"] is False and len(escalations(isolated_env)) == 1
    assert any(a["agent"] == "verificador" and a.get("escalation") for a in out["audit"])


def test_executor_failure_escalates(monkeypatch, isolated_env):
    monkeypatch.setenv("TIDER_DRY_RUN", "false")   # sin TIDER_EXECUTOR_KUBECONFIG: el ejecutor se niega
    g, _, _ = make({"investigator": [TOOL1, TOOL2, final()], "judge": SUPPORTED, "reporter": "r"})
    out = run_alert(g, ALERT)
    assert "error" in out["execution"] and len(escalations(isolated_env)) == 1


def test_judge_rejects_then_loop_then_escalates():
    g, llm, _ = make({"investigator": [TOOL1, final(), TOOL2, final()],
                      "judge": {"supported": False, "confidence": 0.4, "missing": ["eventos de k8s"]}, "reporter": "r"})
    out = run_alert(g, ALERT)
    assert out["decision"]["route"] == "escalate"
    assert sum(1 for a, _ in llm.calls if a == "judge") == 2   # TIDER_MAX_ITER=2 -> 2 rondas en total


def test_judge_cap_no_telemetry_evidence():
    g, _, _ = make({"investigator": [final()], "judge": {"supported": True, "confidence": 0.99, "missing": []}, "reporter": "r"})
    out = run_alert(g, ALERT)   # sin herramientas -> solo docs -> el juez determinista lo baja y el decisor escala
    assert out["verdict"]["supported"] is False and out["decision"]["route"] == "escalate"


def test_failing_tools_do_not_count_as_evidence():
    def boom(**kw): raise ConnectionError("connection refused")
    tools = ToolRegistry([Tool("prom_range", "", "metric", boom), Tool("kube_events", "", "k8s", boom)])
    g, _, _ = make({"investigator": [tool("prom_range", query="q"), TOOL2, final()], "judge": SUPPORTED, "reporter": "r"},
                   tools=tools)
    out = run_alert(g, ALERT)
    assert out["verdict"]["confidence"] == 0 and out["decision"]["route"] == "escalate"


def test_invalid_llm_output_escalates_instead_of_crashing(isolated_env):
    def bad(user): raise ValueError("La respuesta no contiene JSON")
    for script in ({"investigator": bad, "judge": bad},
                   {"investigator": {"action": "final", "hypothesis": {"reason": "sin componente"}}, "judge": SUPPORTED}):
        g, _, _ = make({**script, "reporter": "r"})
        assert run_alert(g, ALERT)["decision"]["route"] == "escalate"
    assert len(escalations(isolated_env)) == 2


def test_crash_outside_agents_still_escalates(isolated_env):
    g = build_graph(Deps(ScriptedLLM({}), None, ToolRegistry(), load_policy()))   # store=None: el contexto revienta
    out = run_alert(g, ALERT)
    assert out["decision"]["route"] == "escalate" and out["error"] and len(escalations(isolated_env)) == 1


def test_llm_cannot_bypass_allowlist():
    g, _, _ = make({"investigator": [TOOL1, TOOL2, final("runbook:delete-namespace")],
                    "judge": {"supported": True, "confidence": 1.0, "missing": []}, "reporter": "r"})
    assert run_alert(g, ALERT)["decision"]["route"] == "escalate"


def test_cooldown_and_kill_switch_block_repeated_actions(isolated_env):
    llm = lambda: ScriptedLLM({"investigator": [TOOL1, TOOL2, final()], "judge": SUPPORTED, "reporter": "r"})
    store = InMemoryStore(); ingest_dir(store, ROOT / "docs")
    deps = Deps(llm(), store, FixtureRegistry(ROOT / "eval/fixtures/memory_leak_recommendation.json"), load_policy())
    g = build_graph(deps)   # los nodos comparten deps: mismo Safety entre corridas, como en la API
    assert run_alert(g, ALERT)["decision"]["route"] == "runbook"
    deps.llm = llm()
    second = run_alert(g, ALERT)
    assert second["decision"]["route"] == "escalate" and "enfriamiento" in second["decision"]["reason"]
    deps.llm, deps.safety = llm(), type(deps.safety).from_policy(deps.policy)   # sin enfriamiento previo
    (isolated_env / "STOP").touch()
    assert "apagado" in run_alert(g, ALERT)["decision"]["reason"]


def test_undo_allowed_only_after_a_recent_rollout():
    undo = lambda comp: final("runbook:rollout-undo", docs=(), component=comp, propagation=(comp,))
    g, _, _ = make({"investigator": [tool("kube_logs_previous", pod="ad-6c5b8d7f9-zt4mn"), tool("deployment_status", deployment="ad"),
                                     undo("ad")], "judge": SUPPORTED | {"confidence": 0.9}, "reporter": "r"}, fixture="bad_deploy_ad")
    assert run_alert(g, {**ALERT, "name": "KubePodCrashLooping", "service": "ad"})["decision"]["action"] == "rollout-undo"
    g, _, _ = make({"investigator": [tool("kube_logs_previous", pod="valkey-cart-5d8f7c9b6-q7wzt"),
                                     tool("deployment_status", deployment="valkey-cart"), undo("valkey-cart")],
                    "judge": SUPPORTED, "reporter": "r"}, fixture="configmap_valkey_cart")
    out = run_alert(g, {**ALERT, "name": "CartHighErrorRate", "service": "cart"})
    assert out["decision"]["route"] == "escalate" and "rollout reciente" in out["decision"]["reason"]


def test_injected_instructions_cannot_trigger_an_action():
    """El LLM "obedece" la inyección de los logs y el juez la respalda: el decisor igual escala."""
    injected = final("runbook:scale", docs=(), component="frontend", propagation=("frontend", "checkout"),
                     params={"deployment": "frontend", "replicas": 5})
    g, _, _ = make({"investigator": [tool("logs_search", service="checkout"), tool("traces_errors", service="checkout"), injected],
                    "judge": {"supported": True, "confidence": 1.0, "missing": []}, "reporter": "r"}, fixture="injection_checkout")
    out = run_alert(g, {**ALERT, "name": "CheckoutHighErrorRate", "service": "checkout"})
    assert out["decision"]["route"] == "escalate"


def test_stale_docs_lower_confidence():
    g, _, store = make({"investigator": [TOOL1, TOOL2, final()],
                        "judge": {"supported": True, "confidence": 0.95, "missing": []}, "reporter": "r"})
    store.docs["docs/runbooks/memoria-oomkilled.md"].updated = date.today() - timedelta(days=400)
    out = run_alert(g, ALERT)
    assert out["verdict"]["confidence"] <= 0.9 and "desactualizado" in out["verdict"]["notes"]


def test_no_rag_variant_has_no_context():
    g, _, _ = make({"investigator": [TOOL1, TOOL2, final(docs=())], "judge": SUPPORTED, "reporter": "r"}, use_rag=False)
    assert run_alert(g, ALERT)["context"] == []
