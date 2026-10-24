"""Regression tests for composition, trace integrity and concurrent isolation."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from tider.console.analysis import LabEngine
from tider.console.models import AnalyzeRequest
from tider.console.providers import EvidenceProvider
from tider.console.service import AnalysisService
from tider.console.settings import Settings


def service(limit=50):
    settings = Settings(evidence_mode="mock", llm_provider="none", history_limit=limit)
    return AnalysisService(settings, EvidenceProvider(settings), LabEngine(settings))


def request(identifier="RUN-1", scenario="redis_down", service="cartservice"):
    end = datetime.now(timezone.utc)
    return AnalyzeRequest(
        incident_id=identifier, service=service, start=end - timedelta(minutes=5), end=end, scenario=scenario
    )


def test_history_is_owned_by_each_application_and_returns_copies():
    first, second = service(limit=2), service()
    for identifier in ("ONE", "TWO", "THREE"):
        first.analyze(request(identifier))
    history = first.history()
    assert [item.incident_id for item in history] == ["THREE", "TWO"]
    history[0].workflow.audit.clear()
    assert first.history()[0].workflow.audit
    assert second.history() == []


def test_parallel_analyses_keep_separate_evidence_and_decisions():
    app = service()
    requests = [
        request(f"RUN-{index}", "redis_down" if index % 2 else "missing_telemetry") for index in range(8)
    ]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(app.analyze, requests))
    assert len({result.run_id for result in results}) == len(requests)
    for query, result in zip(requests, results):
        assert result.incident_id == query.incident_id
        assert result.status == ("hypothesis" if query.scenario == "redis_down" else "insufficient_evidence")
        assert len(result.evidence) == (4 if query.scenario == "redis_down" else 0)
    assert len(app.history()) == len(requests)


def test_decision_trace_links_only_observed_signals_and_preserves_rounds():
    app = service()
    for scenario in ("redis_down", "healthy", "missing_telemetry"):
        result = app.analyze(request(scenario=scenario))
        steps = result.decision_steps
        assert [step.sequence for step in steps] == list(range(1, len(steps) + 1))
        assert [step.stage for step in steps] == [event["agent"] for event in result.workflow.audit]
        ids = {signal.id for signal in result.evidence}
        assert all(set(step.evidence_ids) <= ids for step in steps)
        assert all(step.reason and step.outcome for step in steps)
        verification = next(step for step in steps if step.stage == "verificador")
        assert verification.status == "skipped"
        assert "sin acción ejecutada" in verification.reason
        if scenario != "redis_down":
            assert len([step for step in steps if step.stage == "judge"]) == 2
        for step in steps:
            if step.stage == "judge":
                assert step.status == ("completed" if scenario == "redis_down" else "needs_review")
