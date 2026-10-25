from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from tider.console.api import create_app
from tider.console.baseline import diagnose
from tider.console.models import Signal
from tider.console.providers.redaction import sanitize
from tider.console.settings import Settings

client = TestClient(create_app(Settings(evidence_mode="mock", llm_provider="none")))


def test_redis_root_cause():
    now = datetime.now(timezone.utc)
    r = client.post(
        "/v1/incidents/analyze",
        json={
            "incident_id": "MOCK-001",
            "service": "cartservice",
            "start": (now - timedelta(minutes=5)).isoformat(),
            "end": now.isoformat(),
        },
    )
    assert r.status_code == 200
    assert r.json()["component"] == "redis-cart"
    assert r.json()["status"] == "hypothesis"


def test_unknown_service_has_no_hallucinated_root_cause():
    now = datetime.now(timezone.utc)
    r = client.post(
        "/v1/incidents/analyze",
        json={
            "incident_id": "MOCK-002",
            "service": "paymentservice",
            "start": (now - timedelta(minutes=1)).isoformat(),
            "end": now.isoformat(),
        },
    )
    assert r.json()["status"] == "insufficient_evidence"


def test_rejects_overly_wide_window():
    now = datetime.now(timezone.utc)
    r = client.post(
        "/v1/incidents/analyze",
        json={
            "incident_id": "MOCK-003",
            "service": "cartservice",
            "start": (now - timedelta(hours=3)).isoformat(),
            "end": now.isoformat(),
        },
    )
    assert r.status_code == 422


def test_redacts_secrets():
    assert "abcdef" not in sanitize("token=abcdef user=test@example.com")
    assert "test@example.com" not in sanitize("user=test@example.com")


@pytest.mark.parametrize(
    "service,severity,operation,code,detail,expected",
    [
        ("frontend", "ERROR", "cart", "Unavailable", "connection refused", "hypothesis"),
        ("frontend", "ERROR", "payment", "Unavailable", "connection refused", "insufficient_evidence"),
        ("frontend", "INFO", "cart", "Unavailable", "connection refused", "insufficient_evidence"),
        ("frontend", "ERROR", "cart", "PermissionDenied", "connection refused", "insufficient_evidence"),
        ("frontend", "ERROR", "cart", "Unavailable", "deadline exceeded", "insufficient_evidence"),
        ("paymentservice", "ERROR", "cart", "Unavailable", "connection refused", "insufficient_evidence"),
    ],
)
def test_real_cart_rpc_pattern_is_specific(service, severity, operation, code, detail, expected):
    signal = Signal(
        timestamp=datetime.now(timezone.utc),
        service=service,
        source="log",
        severity=severity,
        message=(
            f"could not retrieve {operation}: rpc error: code = {code} desc = connection error: "
            f'desc = "transport: Error while dialing: dial tcp 192.0.2.1:7070: connect: {detail}"'
        ),
    )
    result = diagnose("unlabelled-incident", "frontend", [signal])
    assert result.status == expected
    if expected == "hypothesis":
        assert result.component == "cartservice"
        assert result.confidence <= 0.7
