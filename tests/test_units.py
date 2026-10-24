import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from tider.decision.policy import decide, load_policy
from tider.executor import escalate as esc
from tider.executor.runbook import build, execute
from tider.lake.ingest import ingest_dir, parse_mermaid, split_markdown
from tider.lake.store import InMemoryStore
from tider.safety import Safety
from tider.state import Evidence, Hypothesis, Verdict
from tider.tools import kube
from tider.tools.base import FixtureRegistry, Tool, ToolRegistry
from tider.tools.kube import guard

ROOT = Path(__file__).resolve().parents[1]
CFG = load_policy()
OK = Verdict(supported=True, confidence=0.95)


def status(dep="ad", replicas=1, age=9, revisions=3, hpa=None):
    return {
        "deployment": dep,
        "replicas": replicas,
        "ready": replicas,
        "revision": revisions,
        "revisions": revisions,
        "last_rollout_age_minutes": age,
        "hpa": hpa,
    }


def hyp(
    action="runbook:rollout-restart",
    params=None,
    kinds=("metric", "k8s"),
    component="recommendation",
    st=None,
):
    ev = [Evidence(source="t", kind=k, summary="x") for k in kinds]
    if st:
        ev.append(Evidence(source="deployment_status", kind="deploy", summary=json.dumps(st), data=st))
    return Hypothesis(
        component=component,
        reason="causa",
        propagation=[component, "frontend"],
        proposed_action=action,
        action_params=params if params is not None else {"deployment": component},
        evidence=ev,
    )


def test_mermaid_edges_use_labels():
    edges = parse_mermaid("graph LR\n FE[frontend] --> CART[cart]\n CART --> VK[valkey-cart]")
    assert {(e.src, e.dst) for e in edges} == {("frontend", "cart"), ("cart", "valkey-cart")}


def test_split_markdown_keeps_headings_and_cuts_long_lines():
    chunks = split_markdown("# A\ntexto\n## B\notro")
    assert len(chunks) == 2 and chunks[1].startswith("## B")
    assert all(len(c) <= 100 for c in split_markdown("x" * 250, max_chars=100))


def test_kube_guard_blocks_writes_unlisted_flags_and_other_namespaces():
    ns = ["-n", "otel-demo"]
    guard(["get", "pods", *ns])
    guard(["rollout", "history", "deployment/x", *ns])
    guard(["get", "events", "--sort-by=.lastTimestamp", *ns])
    for bad in (
        ["delete", "pod", "x", *ns],
        ["rollout", "restart", "deployment/x", *ns],
        ["exec", "x", *ns],
        ["describe", "pod", "--token=abc", *ns],
        ["describe", "pod", "x", "--as=system:admin", *ns],
        ["get", "pods", "--context=prod", *ns],
        ["logs", "x", "--kubeconfig=/tmp/k", *ns],
        ["get", "pods"],
        ["logs", "x", "-n", "kube-system"],
        ["get", "pods", "-nkube-system"],
    ):
        with pytest.raises(PermissionError):
            guard(bad)


def test_kube_tools_validate_llm_args_before_running_kubectl():
    reg = ToolRegistry(kube.tools())
    for args in (
        {"kind": "pod", "name": "--context=prod"},
        {"kind": "secret", "name": "x"},
        {"kind": "pod", "name": "x", "namespace": "kube-system"},
    ):
        res = reg.call("kube_describe", **args)  # "name" como argumento ya no choca con el registro
        assert res["kind"] == "error", args


def test_deployment_status_reads_revision_age_and_hpa(monkeypatch):
    def ts(minutes):
        return (datetime.now(timezone.utc) - timedelta(minutes=minutes)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def rs(name, rev, minutes, owner="ad"):
        return {
            "metadata": {
                "name": name,
                "creationTimestamp": ts(minutes),
                "annotations": {"deployment.kubernetes.io/revision": rev},
                "ownerReferences": [{"kind": "Deployment", "name": owner}],
            }
        }

    out = {
        "deployment": {
            "metadata": {"annotations": {"deployment.kubernetes.io/revision": "7"}},
            "status": {"readyReplicas": 1},
            "spec": {"replicas": 2, "template": {"spec": {"containers": [{"image": "demo:ad"}]}}},
        },
        "replicasets": {
            "items": [rs("ad-new", "7", 9), rs("ad-old", "6", 5000), rs("cart-x", "7", 1, owner="cart")]
        },
        "hpa": {"items": [{"metadata": {"name": "cart-hpa"}, "spec": {"scaleTargetRef": {"name": "cart"}}}]},
    }
    monkeypatch.setattr(kube, "_run", lambda args, timeout=20: json.dumps(out[args[1]]))
    st = kube.deployment_status("ad")
    assert (st["replicas"], st["revision"], st["revisions"], st["hpa"]) == (2, 7, 2, None)
    assert 8 <= st["last_rollout_age_minutes"] <= 10

    def no_hpa_permission(args, timeout=20):
        if args[1] == "hpa":
            raise RuntimeError("forbidden")
        return json.dumps(out[args[1]])

    monkeypatch.setattr(kube, "_run", no_hpa_permission)
    assert kube.deployment_status("ad")["hpa"] == "desconocido"  # el decisor no escala a ciegas


def test_tool_failures_and_empty_results_are_not_evidence():
    def boom(**kw):
        raise ConnectionError("connection refused")

    reg = ToolRegistry(
        [
            Tool("prom", "", "metric", boom),
            Tool("vacia", "", "metric", lambda: "[]"),
            Tool("datos", "", "deploy", lambda: {"replicas": 2}),
        ]
    )
    assert reg.call("prom")["kind"] == "error"
    assert reg.call("vacia")["kind"] == "empty"
    assert reg.call("datos")["data"] == {"replicas": 2}


def test_fixture_registry_behaves_like_production():
    reg = FixtureRegistry(ROOT / "eval/fixtures/memory_leak_recommendation.json")
    assert (
        "deployment_status" in reg.describe() and "logs_search" in reg.describe()
    )  # mismas herramientas que prod
    assert reg.call("prom_range", query="container_memory_working_set_bytes")["kind"] == "metric"
    assert reg.call("prom_range", query="algo_que_no_se_grabo")["kind"] == "empty"  # los args importan
    assert (
        reg.call("kube_logs_previous", pod="recommendation-7c9d8f6b4-kx2lp")["kind"] == "log"
    )  # tipo de prod
    assert reg.call("kube_describe", name="x")["kind"] == "error"  # falta "kind": como en prod
    assert reg.call("deployment_status", deployment="recommendation")["data"]["replicas"] == 1


def test_policy_allows_restart_with_confidence():
    d = decide(hyp(), Verdict(supported=True, confidence=0.9), "otel-demo", CFG)
    assert (d.route, d.action) == ("runbook", "rollout-restart")


def test_policy_escalates_low_confidence_unsupported_or_wrong_namespace():
    assert decide(hyp(), Verdict(supported=True, confidence=0.5), "otel-demo", CFG).route == "escalate"
    assert (
        decide(hyp(), Verdict(supported=False, confidence=0.9, missing=["logs"]), "otel-demo", CFG).route
        == "escalate"
    )
    assert decide(hyp(), OK, "prod", CFG).route == "escalate"


def test_policy_target_must_be_in_chain_and_not_protected():
    assert decide(hyp(params={"deployment": "kafka"}), OK, "otel-demo", CFG).route == "escalate"
    assert decide(hyp(component="flagd"), OK, "otel-demo", CFG).route == "escalate"


def test_policy_undo_requires_a_recent_rollout():
    assert (
        decide(hyp("runbook:rollout-undo", component="ad"), OK, "otel-demo", CFG).route == "escalate"
    )  # sin status
    assert (
        decide(hyp("runbook:rollout-undo", component="ad", st=status(age=4320)), OK, "otel-demo", CFG).route
        == "escalate"
    )
    assert (
        decide(
            hyp("runbook:rollout-undo", component="ad", st=status(revisions=1)), OK, "otel-demo", CFG
        ).route
        == "escalate"
    )
    assert (
        decide(hyp("runbook:rollout-undo", component="ad", st=status()), OK, "otel-demo", CFG).route
        == "runbook"
    )


def test_policy_scale_only_up_without_hpa_and_capped():
    def scale(r, **st):
        return decide(
            hyp("runbook:scale", {"deployment": "ad", "replicas": r}, component="ad", st=status(**st)),
            OK,
            "otel-demo",
            CFG,
        )

    assert scale(1, replicas=3).route == "escalate"  # hacia abajo
    assert scale(3, replicas=3).route == "escalate"  # sin cambio
    assert scale(50).route == "escalate"  # tope
    assert scale(3, hpa="ad-hpa").route == "escalate"
    d = scale(3, replicas=2)
    assert d.route == "runbook" and d.params["current_replicas"] == 2


def test_policy_rejects_unknown_action():
    assert (
        decide(hyp("runbook:delete-namespace"), Verdict(supported=True, confidence=1), "otel-demo", CFG).route
        == "escalate"
    )


def test_runbook_build_is_templated_and_validates_names():
    assert build("scale", {"deployment": "ad", "replicas": 3}, "otel-demo")[-1] == "--replicas=3"
    assert "--current-replicas=2" in build(
        "scale", {"deployment": "ad", "replicas": 3, "current_replicas": 2}, "otel-demo"
    )
    for bad in ("ad; rm -rf /", "--all", 7):
        with pytest.raises(ValueError):
            build("rollout-restart", {"deployment": bad}, "otel-demo")


def test_runbook_never_runs_without_executor_credential(monkeypatch):
    monkeypatch.setenv("TIDER_DRY_RUN", "false")
    with pytest.raises(PermissionError):
        execute("rollout-restart", {"deployment": "ad"}, "otel-demo")


def test_safety_dedup_cooldown_budget_and_kill_switch(monkeypatch, isolated_env):
    now = [0.0]
    s = Safety(cooldown_minutes=30, max_actions_per_hour=2, clock=lambda: now[0])
    assert s.claim_alert("fp1") and not s.claim_alert("fp1")  # reenvío de Alertmanager
    assert s.reserve_action("ad") is None
    assert "enfriamiento" in s.reserve_action("ad")
    assert s.reserve_action("cart") is None
    assert "Presupuesto" in s.reserve_action("payment")
    now[0] = 3601
    assert s.claim_alert("fp1") and s.reserve_action("payment") is None
    isolated_env.mkdir(parents=True, exist_ok=True)
    (isolated_env / "STOP").touch()
    assert "apagado" in s.reserve_action("frontend")
    monkeypatch.setenv("TIDER_STOP_FILE", str(isolated_env / "no-existe"))
    monkeypatch.setenv("TIDER_AUTONOMY", "off")
    assert "apagado" in s.reserve_action("frontend")


def test_generic_runbooks_are_found_for_any_service():
    store = InMemoryStore()
    ingest_dir(store, ROOT / "docs")
    res = store.search("crashloop configuración CrashLoopBackOff", k=3, doc_type="runbook", service="cart")
    ids = [r["doc_id"] for r in res]
    assert "docs/runbooks/crashloop-config.md" in ids and len(ids) == len(set(ids))  # un trozo por documento


def test_escalation_files_do_not_collide_and_names_are_safe(isolated_env):
    a = {"name": "../../x/y"}
    f1, f2 = esc.escalate(a, "r", "s")["escalation"], esc.escalate(a, "r", "s")["escalation"]
    assert f1 != f2 and Path(f1).parent == isolated_env / "escalations"
