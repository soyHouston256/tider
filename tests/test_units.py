import pytest
from tider.decision.policy import decide, load_policy
from tider.executor.runbook import build
from tider.lake.ingest import parse_mermaid, split_markdown
from tider.state import Evidence, Hypothesis, Verdict
from tider.tools.kube import guard

CFG = load_policy()


def hyp(action="runbook:rollout-restart", params=None, kinds=("metric", "k8s")):
    return Hypothesis(component="recommendation", reason="fuga de memoria", proposed_action=action,
                      action_params=params if params is not None else {"deployment": "recommendation"},
                      evidence=[Evidence(source="t", kind=k, summary="x") for k in kinds])


def test_mermaid_edges_use_labels():
    edges = parse_mermaid("graph LR\n FE[frontend] --> CART[cart]\n CART --> VK[valkey-cart]")
    assert {(e.src, e.dst) for e in edges} == {("frontend", "cart"), ("cart", "valkey-cart")}


def test_split_markdown_keeps_headings():
    chunks = split_markdown("# A\ntexto\n## B\notro")
    assert len(chunks) == 2 and chunks[1].startswith("## B")


def test_kube_guard_blocks_writes():
    guard(["get", "pods"]); guard(["rollout", "history", "deployment/x"])
    for bad in (["delete", "pod", "x"], ["rollout", "restart", "deployment/x"], ["exec", "x"]):
        with pytest.raises(PermissionError):
            guard(bad)


def test_policy_allows_restart_with_confidence():
    d = decide(hyp(), Verdict(supported=True, confidence=0.9), "otel-demo", CFG)
    assert (d.route, d.action) == ("runbook", "rollout-restart")


def test_policy_escalates_low_confidence_unsupported_or_wrong_namespace():
    assert decide(hyp(), Verdict(supported=True, confidence=0.5), "otel-demo", CFG).route == "escalate"
    assert decide(hyp(), Verdict(supported=False, confidence=0.9, missing=["logs"]), "otel-demo", CFG).route == "escalate"
    assert decide(hyp(), Verdict(supported=True, confidence=0.95), "prod", CFG).route == "escalate"


def test_policy_undo_requires_deploy_evidence_and_scale_is_capped():
    v = Verdict(supported=True, confidence=0.95)
    assert decide(hyp("runbook:rollout-undo"), v, "otel-demo", CFG).route == "escalate"
    assert decide(hyp("runbook:rollout-undo", kinds=("deploy", "k8s")), v, "otel-demo", CFG).route == "runbook"
    assert decide(hyp("runbook:scale", {"deployment": "ad", "replicas": 50}), v, "otel-demo", CFG).route == "escalate"
    assert decide(hyp("runbook:scale", {"deployment": "ad", "replicas": 3}), v, "otel-demo", CFG).route == "runbook"


def test_policy_rejects_unknown_action():
    assert decide(hyp("runbook:delete-namespace"), Verdict(supported=True, confidence=1), "otel-demo", CFG).route == "escalate"


def test_runbook_build_is_templated_and_validates_names():
    assert build("scale", {"deployment": "ad", "replicas": 3}, "otel-demo")[-1] == "--replicas=3"
    with pytest.raises(ValueError):
        build("rollout-restart", {"deployment": "ad; rm -rf /"}, "otel-demo")
