import json
from datetime import datetime, timedelta, timezone
from threading import RLock
from types import SimpleNamespace

import pytest

from tider.console.investigation_tools import InvestigationTools
from tider.console.models import AnalyzeRequest, Signal
from tider.console.providers.operational_observer import observer_url, read_observations
from tider.console.settings import Settings


class Lake:
    lock = RLock()

    def catalog(self):
        return {"status": "confirmed", "revision": 1,
                "confirmed": {"services": [{"name": "cartservice"}], "relations": []}}

    def snapshot_documents(self):
        return []


def tools():
    end = datetime.now(timezone.utc)
    req = AnalyzeRequest(incident_id="offline-test", service="cartservice", mode="gcp",
                         start=end - timedelta(minutes=5), end=end)
    settings = Settings(agent_observer_url="http://127.0.0.1:18092", agent_events_enabled=False)
    return InvestigationTools(settings, req, Lake())


@pytest.mark.parametrize("url", ["http://example.com", "http://localhost/api/evidence/x", "http://user@localhost", "https://localhost", "http://localhost?path=/api/state"])
def test_observer_cannot_be_retargeted(url):
    with pytest.raises(ValueError):
        observer_url(url)


def test_projection_summarizes_successful_slow_requests_and_omits_truth(monkeypatch):
    end = datetime.now(timezone.utc)
    data = {"mode": "GKE", "observations": [{"at": end.timestamp() - i, "service": "cartservice",
        "coverage": "complete", "synthetic": False, "mechanism": "hidden_truth", "original": "private",
        "configuration": {"container": "server", "redis_address": "redis-cart:6379", "secret": "private"},
        "http": [{"path": "/cart", "status": 200, "elapsed_ms": 300}],
        "dependency": {"success": True, "elapsed_ms": 280}} for i in (3, 2, 1)]}
    calls = []
    def get(url, **kwargs):
        calls.append((url, kwargs))
        return SimpleNamespace(content=json.dumps(data).encode(), json=lambda: data, raise_for_status=lambda: None)
    monkeypatch.setattr("tider.console.providers.operational_observer.httpx.get", get)
    result = read_observations("http://127.0.0.1:18092", "cartservice", end - timedelta(seconds=10), end, 4)
    assert all(b["errors"] == 0 and b["latency_median_ms"] == 300 for b in result["buckets"])
    assert "hidden_truth" not in json.dumps(result) and "private" not in json.dumps(result)
    assert calls[0][0].endswith("/api/observations") and calls[0][1]["timeout"] == 4


def test_late_logs_can_refresh_once_without_resetting_budget(monkeypatch):
    t = tools()
    calls = []
    def logs(*args, **kwargs):
        calls.append(1)
        return [] if len(calls) == 1 else [Signal(timestamp=t.request.start, service="cartservice", source="log", message="Redis connection failed")]
    monkeypatch.setattr("tider.console.investigation_tools.gcp_signals", logs)
    assert t.search_logs() == ""
    assert t.search_logs() == "" and len(calls) == 1
    before = t.log_remaining
    assert t.search_logs(refresh=True)["records"] == 1
    assert t.log_remaining == before - 1 and len(calls) == 2
    with pytest.raises(ValueError):
        t.search_logs(refresh=True)


def test_budget_exhaustion_prevents_network_call(monkeypatch):
    t = tools()
    t.deadline = 101
    monkeypatch.setattr("tider.console.investigation_tools.monotonic", lambda: 100)
    monkeypatch.setattr("tider.console.investigation_tools.read_observations", lambda *a: pytest.fail("unexpected network call"))
    with pytest.raises(TimeoutError):
        t.operation_evidence("cartservice")


def test_simulation_never_counts_as_live_cloud_evidence(monkeypatch):
    t = tools()
    monkeypatch.setattr("tider.console.investigation_tools.read_observations", lambda *a: {"buckets": [{"synthetic": True}]})
    with pytest.raises(ValueError, match="simulaciones"):
        t.operation_evidence("cartservice")


def test_empty_operational_observations_cannot_support_a_finding(monkeypatch):
    from tider.console.agentic import AgenticEngine
    from tider.llm import ScriptedLLM
    t = tools()
    monkeypatch.setattr("tider.console.investigation_tools.read_observations", lambda *a: {"buckets": []})
    def choose(prompt):
        if '"id": "Q1"' not in prompt:
            return {"action": "tool", "tool": "operation_evidence", "args": {"service": "cartservice"}}
        return {"action": "final", "component": "cartservice", "finding": "El carrito está lento", "cites": ["Q1"]}
    model = ScriptedLLM({"investigator": choose, "judge": {"supported": True, "notes": "should not run"}})
    result = AgenticEngine(t.settings, Lake(), model).analyze_live(t.request)
    assert not result.workflow.verdict.supported


def test_state_exposes_only_allowed_nonsecret_dependency_fields(monkeypatch):
    t = tools()
    dep = {"metadata": {"generation": 5}, "spec": {"replicas": 1, "selector": {"matchLabels": {"app": "cartservice"}},
        "template": {"spec": {"containers": [{"name": "server", "resources": {"limits": {"cpu": "50m"}},
            "env": [{"name": "REDIS_ADDR", "value": "redis-cart:6380"}, {"name": "PASSWORD", "value": "never-export"},
                    {"name": "PRODUCT_CATALOG_SERVICE_ADDR", "valueFrom": {"secretKeyRef": {"name": "secret-ref"}}}]}]}}}}
    def run(args, **kwargs):
        obj = dep if args[args.index("get") + 1] == "deployment" else {"items": []}
        return SimpleNamespace(returncode=0, stdout=json.dumps(obj))
    monkeypatch.setattr("tider.console.investigation_tools.subprocess.run", run)
    result = t.service_state("cartservice")
    assert result["configuration"]["containers"][0]["dependencies"] == {"REDIS_ADDR": "redis-cart:6380"}
    assert "never-export" not in json.dumps(result) and "secret-ref" not in json.dumps(result)
