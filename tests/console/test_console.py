from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from tider.console.api import create_app
from tider.console.models import Signal
from tider.console.providers.redaction import sanitize
from tider.console.settings import Settings


@pytest.fixture
def settings():
    return Settings(
        evidence_mode="mock", llm_provider="none", google_cloud_project="tider-ops", gcp_namespace="boutique"
    )


@pytest.fixture
def app(settings):
    return create_app(settings)


def payload(**kwargs):
    now = datetime.now(timezone.utc)
    return {
        "incident_id": "CF-TEST",
        "service": "cartservice",
        "mode": "mock",
        "start": (now - timedelta(minutes=10)).isoformat(),
        "end": now.isoformat(),
        **kwargs,
    }


@pytest.mark.parametrize(
    "scenario,service,component,status,n",
    [
        ("redis_down", "cartservice", "redis-cart", "hypothesis", 4),
        ("cart_unavailable", "frontend", "cartservice", "hypothesis", 3),
        ("healthy", "cartservice", "cartservice", "insufficient_evidence", 2),
        ("missing_telemetry", "cartservice", "cartservice", "insufficient_evidence", 0),
    ],
)
def test_scenarios_run_the_real_graph(scenario, service, component, status, n, app):
    with TestClient(app) as c:
        r = c.post("/v1/incidents/analyze", json=payload(scenario=scenario, service=service))
        assert r.status_code == 200, r.text
        result = r.json()
        assert (result["component"], result["status"], len(result["evidence"])) == (component, status, n)
        assert result["workflow"]["execution"]["executed"] is False
        assert result["workflow"]["execution"]["mode"] == "observation"
        assert result["workflow"]["resolved"] is False
        assert {x["agent"] for x in result["workflow"]["audit"]} == {
            "intake",
            "context",
            "investigator",
            "judge",
            "decisor",
            "ejecutor",
            "verificador",
            "reporter",
        }
        assert c.get("/v1/incidents").json()[0]["run_id"] == result["run_id"]


def test_console_assets_and_host_boundary(app):
    with TestClient(app) as c:
        r = c.get("/")
        assert r.status_code == 200 and "Investigar incidente" in r.text
        assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
        assert c.get("/static/js/app.js").status_code == 200
        assert c.get("/static/css/app.css").status_code == 200
        assert c.get("/docs").status_code == 200
        assert c.get("/v1/lab/config").json()["gcp_enabled"] is False
        assert c.get("/", headers={"host": "attacker.example"}).status_code == 400


def test_diagnosis_uses_evidence_not_scenario_label(monkeypatch, app):
    sample = [
        Signal(
            timestamp=datetime.now(timezone.utc),
            service="cartservice",
            source="log",
            severity="ERROR",
            message="Redis connection refused",
        )
    ]
    monkeypatch.setattr(app.state.analysis_service.provider, "load", lambda *a, **kw: sample)
    r = TestClient(app).post("/v1/incidents/analyze", json=payload(scenario="healthy"))
    assert r.json()["component"] == "redis-cart"


@pytest.mark.parametrize(
    "change",
    [
        {"service": 'cartservice" OR severity>=INFO'},
        {"start": "2026-10-17T12:00:00"},
        {"start": "2026-10-17T12:00:00Z", "end": "2026-10-17T12:00:00Z"},
        {"scenario": "../credentials"},
        {"mode": "aws"},
    ],
)
def test_invalid_input_rejected(change, app):
    assert TestClient(app).post("/v1/incidents/analyze", json=payload(**change)).status_code == 422


def test_gcp_cannot_be_activated_by_the_browser(monkeypatch, app):
    from google.cloud import logging_v2

    client = Mock(side_effect=AssertionError("Cloud access must be disabled"))
    monkeypatch.setattr(logging_v2, "Client", client)
    r = TestClient(app).post("/v1/incidents/analyze", json=payload(mode="gcp"))
    assert r.status_code == 400
    client.assert_not_called()


def test_gcp_query_is_scoped_and_logs_are_redacted(monkeypatch, app, settings):
    from google.cloud import logging_v2

    monkeypatch.setattr(settings, "evidence_mode", "gcp")
    fake = Mock()
    fake.list_entries.return_value = [
        SimpleNamespace(
            payload={
                "message": "Request failed user=a@example.com",
                "error": "Redis connection refused token=secretXYZ",
                "extra": "sensitive-not-allowed",
            },
            labels={"k8s-pod/app": "cartservice"},
            timestamp=datetime.now(timezone.utc),
            severity="ERROR",
        )
    ]
    monkeypatch.setattr(logging_v2, "Client", lambda **kw: fake)
    response = TestClient(app).post("/v1/incidents/analyze", json=payload(mode="gcp"))
    assert response.status_code == 200, response.text
    result = response.json()
    query = fake.list_entries.call_args.kwargs["filter_"]
    for required in [
        'resource.type="k8s_container"',
        'project_id="tider-ops"',
        'cluster_name="chaosforge-lab"',
        'location="us-central1"',
        'namespace_name="boutique"',
        "timestamp >=",
        "timestamp <=",
        'labels."k8s-pod/app"="cartservice"',
        'labels."k8s-pod/app"="redis-cart"',
    ]:
        assert required in query
    assert fake.list_entries.call_args.kwargs["max_results"] is None
    assert "severity >= ERROR" in query
    assert result["evidence_mode"] == "gcp"
    assert result["component"] == "redis-cart"
    assert result["confidence"] <= 0.7
    assert {s["source"] for s in result["evidence"]} == {"log"}
    assert "Redis connection refused" in result["evidence"][0]["message"]
    assert "Request failed" in result["evidence"][0]["message"]
    assert all(s not in response.text for s in ["secretXYZ", "a@example.com", "sensitive-not-allowed"])
    fake.close.assert_called_once()


def test_provider_failure_does_not_fall_back_to_mock(monkeypatch, app):
    def failure(*a, **kw):
        raise RuntimeError("token=private-password")

    monkeypatch.setattr(app.state.analysis_service.provider, "load", failure)
    r = TestClient(app).post("/v1/incidents/analyze", json=payload(mode="gcp"))
    assert r.status_code == 503
    assert "private-password" not in r.text
    assert not app.state.analysis_service.history()


def test_redaction_handles_bearer_and_json_values():
    for raw in [
        "Authorization: Bearer tokenABC",
        '{"token": "tokenABC"}',
        "password=tokenABC",
        "api_key:tokenABC",
    ]:
        assert "tokenABC" not in sanitize(raw)


def test_tools_cannot_accept_invented_records():
    from tider.console.analysis import reader
    from tider.tools.base import Tool, ToolRegistry

    registry = ToolRegistry([Tool("lab_log", "logs", "log", reader([]))])
    assert registry.call("lab_log", records=[{"message": "fake"}])["kind"] == "error"


def test_no_external_effects_even_with_unsafe_environment(monkeypatch, app):
    import subprocess

    import httpx

    monkeypatch.setenv("TIDER_DRY_RUN", "false")
    monkeypatch.setenv("TIDER_SLACK_WEBHOOK", "https://example.com/do-not-send")
    blocked = Mock(side_effect=AssertionError("External side effect"))
    monkeypatch.setattr(subprocess, "run", blocked)
    monkeypatch.setattr(httpx, "post", blocked)
    r = TestClient(app).post("/v1/incidents/analyze", json=payload())
    assert r.status_code == 200
    blocked.assert_not_called()
