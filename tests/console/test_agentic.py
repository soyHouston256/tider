"""Offline adaptive investigations; no cloud calls or paid model required."""
from datetime import datetime, timedelta, timezone
from threading import RLock

import pytest

from tider.console.agentic import AgenticEngine, scrub
from tider.console.investigation_tools import InvestigationTools
from tider.console.models import AnalyzeRequest, Signal
from tider.console.service import AnalysisService
from tider.console.settings import Settings
from tider.llm import ScriptedLLM


class Lake:
    lock = RLock()
    revision = 1

    def catalog(self):
        return {"status": "confirmed", "revision": self.revision,
                "confirmed": {"services": [{"name": "frontend"}, {"name": "shippingservice"}],
                              "relations": []}}

    def snapshot_documents(self):
        return [{"doc_id": "uploaded", "text": "frontend calls shippingservice", "title": "architecture.md"}]

    def search(self, query, k=4):
        return self.snapshot_documents()


def request(**kwargs):
    end = datetime.now(timezone.utc)
    return AnalyzeRequest(incident_id="ADAPTIVE", scope="general", start=end-timedelta(minutes=10),
                          end=end, mode="gcp", **kwargs)


def settings(**kwargs):
    return Settings(llm_provider="anthropic", tider_model="test-model", evidence_mode="gcp", **kwargs)


def final(cites=None):
    return {"action": "final", "component": "shippingservice", "finding": "Envios no accesible desde frontend",
            "cites": cites or ["Q2"], "missing": ["No se conoce el motivo de la caída"]}


def test_adapts_query_to_observation_and_uses_uploaded_context(monkeypatch):
    queries = []
    def logs(service, start, end, cfg, services, **kwargs):
        queries.append(services)
        return [Signal(timestamp=start, service="frontend", source="log", message="shipping connection refused")]
    monkeypatch.setattr("tider.console.investigation_tools.gcp_signals", logs)
    def choose(prompt):
        if '"id": "Q2"' in prompt:
            return final()
        if "frontend calls shippingservice" in prompt:
            return {"action": "tool", "tool": "search_logs", "args": {"services": ["frontend"], "text": "shipping"}}
        return {"action": "tool", "tool": "context_search", "args": {"query": "shipping"}}
    llm = ScriptedLLM({"investigator": choose, "judge": {"supported": True, "notes": "Conexión rechazada observada"}})
    result = AgenticEngine(settings(), Lake(), llm).analyze_live(request())
    assert result.status == "hypothesis"
    assert queries == [["frontend"]]
    assert result.investigation["tool_calls"] == 2
    assert result.workflow.context[0]["doc_id"] == "uploaded"
    assert result.workflow.execution["executed"] is False
    assert result.evidence[0].id == "S01"


def test_reviewer_rejection_causes_new_query(monkeypatch):
    monkeypatch.setattr("tider.console.investigation_tools.gcp_signals", lambda *a, **k: [
        Signal(timestamp=a[1], service="frontend", source="log", message="shipping connection refused")])
    llm = ScriptedLLM({"investigator": [
        {"action": "tool", "tool": "search_logs", "args": {}}, final(["Q1"]),
        {"action": "tool", "tool": "search_logs", "args": {"services": ["shippingservice"]}}, final()],
        "judge": [{"supported": False, "notes": "Comprueba destino"}, {"supported": True, "notes": "Respaldado"}]})
    result = AgenticEngine(settings(), Lake(), llm).analyze_live(request())
    assert result.status == "hypothesis"
    assert len([e for e in result.decision_steps if e.stage == "judge"]) == 2
    assert result.investigation["tool_calls"] == 2


@pytest.mark.parametrize("cite", ["Q1", "invented"])
def test_document_only_and_invented_citations_never_support(cite):
    llm = ScriptedLLM({"investigator": [
        {"action": "tool", "tool": "context_search", "args": {"query": "shipping"}}, final([cite])],
        "judge": {"supported": True}})
    result = AgenticEngine(settings(agent_max_steps=3), Lake(), llm).analyze_live(request())
    assert result.status == "insufficient_evidence"
    assert result.investigation["stop_reason"] == "budget"
    assert not any(agent == "judge" for agent, _ in llm.calls)


def test_tool_args_cannot_escape_scope_or_window(monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Must not call cloud")
    monkeypatch.setattr("tider.console.investigation_tools.gcp_signals", forbidden)
    tools = InvestigationTools(settings(), request(), Lake())
    with pytest.raises(ValueError):
        tools.search_logs(services=["unapproved"])
    with pytest.raises(ValueError):
        tools.search_logs(start="2000-01-01T00:00:00+00:00")
    assert tools.registry.call("execute", command="anything")["kind"] == "error"


def test_log_budget_and_group_pagination_are_explicit(monkeypatch):
    calls = []
    def logs(*a, **k):
        calls.append(k)
        return [Signal(timestamp=a[1], service="frontend", source="log", message=f"error {i}") for i in range(11)]
    monkeypatch.setattr("tider.console.investigation_tools.gcp_signals", logs)
    tools = InvestigationTools(settings(agent_log_budget=10), request(), Lake())
    first = tools.search_logs()
    second = tools.search_logs(offset=5)
    assert first["truncated"] and first["next_offset"] == 5
    assert len(second["groups"]) == 5 and second["next_offset"] is None
    assert len(calls) == 1 and calls[0]["max_records"] == 11
    with pytest.raises(ValueError):
        tools.search_logs(text="new")
    assert len(tools.signals) == 10


def test_context_revision_change_blocks_mixed_sources():
    lake = Lake()
    tools = InvestigationTools(settings(), request(), lake)
    lake.revision += 1
    with pytest.raises(ValueError):
        tools.context_search("shipping")


def test_optional_tools_absent_without_configuration():
    tools = InvestigationTools(settings(), request(), Lake())
    assert "service_state" not in tools.registry.describe()
    assert "search_documentation" not in tools.registry.describe()


def test_structured_redaction_preserves_valid_payload_over_600_chars():
    value = {"text": "x"*1000, "nested": {"token": "not-a-real-secret", "msg": "Bearer abc123"}}
    result = scrub(value)
    assert len(result["text"]) == 1000
    assert "abc123" not in str(result)


def test_service_does_not_preload_logs_in_agent_mode():
    class Provider:
        def load(self, req):
            pytest.fail("Agent chooses queries, not service prefetch")
    llm = ScriptedLLM({"investigator": {"action": "final", "component": "desconocido",
                                      "finding": "Sin evidencia", "cites": []}})
    engine = AgenticEngine(settings(), Lake(), llm)
    service = AnalysisService(settings(), Provider(), engine)
    result = service.analyze(request())
    assert result.run_id and len(service.history()) == 1
    assert result.status == "insufficient_evidence"


def test_stream_emits_actual_steps_then_final_result(monkeypatch):
    import json

    from fastapi.testclient import TestClient

    from tider.console.api import create_app
    class Provider:
        def load(self, request):
            pytest.fail("No prefetch")
    llm = ScriptedLLM({"investigator": {"action": "final", "component": "desconocido", "finding": "Sin evidencia"}})
    cfg = settings()
    service = AnalysisService(cfg, Provider(), AgenticEngine(cfg, Lake(), llm))
    client = TestClient(create_app(cfg, service))
    response = client.post('/v1/incidents/investigate-stream', json=request().model_dump(mode='json'))
    events = [json.loads(line) for line in response.text.splitlines()]
    assert events[0]['type'] == 'step'
    assert events[-1]['type'] == 'result'
    assert events[-1]['result']['investigation']['model_calls'] == 1
    assert client.post('/v1/incidents/investigate-stream', json=request().model_dump(mode='json'),
                       headers={'Origin': 'https://untrusted.example'}).status_code == 403


def test_history_persists_snapshot_across_service_restart(tmp_path):
    class Provider:
        pass
    cfg = settings(investigation_history_path=str(tmp_path/'history.sqlite'))
    llm = ScriptedLLM({"investigator": {"action": "final", "component": "desconocido", "finding": "Sin evidencia"}})
    engine = AgenticEngine(cfg, Lake(), llm)
    first = AnalysisService(cfg, Provider(), engine)
    result = first.analyze(request())
    second = AnalysisService(cfg, Provider(), engine)
    saved = second.history()[0]
    assert saved.run_id == result.run_id
    assert saved.investigation['catalog']['revision'] == 1
    assert saved.workflow.context[0]['doc_id'] == 'uploaded'


def test_mcp_follows_empty_pages_and_uses_fixed_read_tool():
    import json

    import httpx

    from tider.console.providers.logging_mcp import LoggingMCPClient
    seen = []
    def handler(req):
        body = json.loads(req.content)
        seen.append(body)
        data = {'nextPageToken':'second'} if len(seen)==1 else {'entries':[
            {'timestamp':'2026-10-26T08:00:00Z', 'textPayload':'failure', 'severity':'ERROR'}]}
        return httpx.Response(200, json={'result':{'structuredContent':data}})
    client = LoggingMCPClient('test-project', httpx.Client(transport=httpx.MockTransport(handler)), token='test')
    rows = list(client.list_entries('scoped filter', 'timestamp desc', 100, 2))
    assert rows[0].payload == 'failure'
    assert seen[1]['params']['arguments']['pageToken'] == 'second'
    assert all(body['params']['name'] == 'list_log_entries' for body in seen)
    assert seen[0]['params']['arguments']['resourceNames'] == ['projects/test-project']
    client.close()


def test_external_search_rejects_environment_details(monkeypatch):
    tools = InvestigationTools(settings(agent_web_enabled=True, tavily_api_key='fake'), request(), Lake())
    with pytest.raises(ValueError):
        tools.search_documentation('errors from tider-ops')
    with pytest.raises(ValueError):
        tools.search_documentation('connect to 10.0.0.1')


def test_kube_command_is_scoped_and_never_uses_shell(monkeypatch):
    import json
    from types import SimpleNamespace
    calls = []
    def run(args, **kwargs):
        calls.append(args)
        assert not kwargs.get('shell')
        kind = args[args.index('get')+1]
        payload = {'spec':{'replicas':0,'selector':{'matchLabels':{'app':'shippingservice'}}},'status':{}} if kind=='deployment' else {'items':[]}
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))
    monkeypatch.setattr('tider.console.investigation_tools.subprocess.run', run)
    tools = InvestigationTools(settings(agent_reader_kubeconfig='/reader', agent_kube_context='lab'), request(), Lake())
    result = tools.service_state('shippingservice')
    assert result['desired'] == 0 and result['temporal_scope'] == 'current_only_not_incident_history'
    assert all('--namespace' in args and 'boutique' in args and '--context' in args for args in calls)


def test_model_connection_error_is_not_reported_as_missing_evidence():
    class BrokenModel:
        def complete_json(self, *args):
            raise TypeError('unsupported client parameter')
    with pytest.raises(RuntimeError, match='modelo'):
        AgenticEngine(settings(), Lake(), BrokenModel()).analyze_live(request())
