from unittest.mock import Mock

import pytest

from tider.agents.deps import Deps
from tider.decision.policy import load_policy
from tider.executor import escalate, pr, runbook
from tider.graph import build_graph
from tider.lake.store import InMemoryStore
from tider.llm import ScriptedLLM
from tider.tools.base import Tool, ToolRegistry


@pytest.mark.parametrize("action", ["runbook:rollout-restart", "pr:manifests", "escalate"])
def test_observation_mode_never_executes_or_notifies(monkeypatch, action):
    blocked = Mock(side_effect=AssertionError("Unexpected execution"))
    monkeypatch.setenv("TIDER_DRY_RUN", "false")
    monkeypatch.setattr(runbook, "execute", blocked)
    monkeypatch.setattr(pr, "propose", blocked)
    monkeypatch.setattr(escalate, "escalate", blocked)
    tools = ToolRegistry(
        [
            Tool("logs", "logs", "log", lambda: "Error"),
            Tool("metrics", "metrics", "metric", lambda: "High memory"),
        ]
    )
    llm = ScriptedLLM(
        {
            "investigator": [
                {"action": "tool", "tool": "logs"},
                {"action": "tool", "tool": "metrics"},
                {
                    "action": "final",
                    "hypothesis": {
                        "component": "cartservice",
                        "reason": "Test",
                        "proposed_action": action,
                        "action_params": {"deployment": "cartservice"},
                    },
                },
            ],
            "judge": {"supported": True, "confidence": 0.95},
            "reporter": "Test report",
        }
    )
    policy = load_policy()
    policy["namespaces"] = ["boutique"]
    store = InMemoryStore()
    graph = build_graph(Deps(llm, store, tools, policy), observation_only=True)
    result = graph.invoke(
        {"alert": {"name": "Test", "service": "cartservice", "namespace": "boutique"}, "audit": []}
    )
    assert result["execution"]["mode"] == "observation"
    assert result["execution"]["executed"] is False
    assert result["resolved"] is False
    assert not store.docs
    blocked.assert_not_called()
    if action.startswith("runbook:"):
        assert result["execution"]["command"] == "kubectl -n boutique rollout restart deployment/cartservice"
