"""Exploratory control: run the same log reader twice, changing only the severity filter."""

from unittest.mock import patch

from tider.console.investigation_tools import InvestigationTools
from tider.console.models import AnalyzeRequest, Signal
from tider.console.settings import Settings

from .data import HERE, read
from .score import proportion, records_by_query


def collect_log_control():
    cases = read(HERE / "windows.json")
    labels = read(HERE / "incident_labels.json")
    settings = Settings(evidence_mode="mock", agent_web_enabled=False, tavily_api_key="", agent_log_budget=80)
    rows = {}
    for case in cases:
        request = AnalyzeRequest(incident_id=case["id"], scope="general", mode="mock",
                                 start="2026-11-01T12:00:00Z", end="2026-11-01T12:10:00Z")
        signals = [Signal.model_validate(s) for s in case["signals"]]
        row = {"required": labels[case["id"]]["required_records"]}
        with patch("tider.console.investigation_tools.mock_signals", return_value=signals):
            for method, errors_only in (("errors_only", True), ("all_severities", False)):
                tools = InvestigationTools(settings, request, lake=None)
                result = tools.registry.call("search_logs", errors_only=errors_only)
                if result["kind"] not in {"log", "empty"}:
                    raise ValueError("Consulta de control incompleta")
                if result["data"] and (result["data"]["truncated"] or result["data"]["next_offset"] is not None):
                    raise ValueError("La ventana de control requiere paginación")
                projected = {"evidence": [s.model_dump(mode="json") for s in tools.signals], "observations": [
                    {"id": "Q1", "tool": "search_logs", "kind": result["kind"], "data": result["data"]}]}
                row[method] = sorted(records_by_query(case, projected)["Q1"])
        rows[case["id"]] = row
    pos = [r for r in rows.values() if r["required"]]
    return {"all_required_retrieved": {m: proportion([set(r["required"]) <= set(r[m]) for r in pos])
                                        for m in ("errors_only", "all_severities")}, "cases": rows}
