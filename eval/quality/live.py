"""One configured model attempt per synthetic window. The engine sees only neutral inputs."""

import argparse
import os
from datetime import datetime, timezone
from unittest.mock import patch

from dotenv import load_dotenv

from tider.console.agentic import AgenticEngine
from tider.console.catalog_review import CatalogReview
from tider.console.context_lake import ContextLake
from tider.console.models import AnalyzeRequest, Signal
from tider.console.settings import Settings

from .data import HERE, ROOT, digest, read, runbooks, save, verify

OBJECTIVE = ("Investiga la ventana de la tienda. Identifica el componente y el mecanismo que respalda "
             "la evidencia. Si no se pueden identificar, indica qué queda desconocido y cita tus consultas.")


def synthetic_lake():
    lake = ContextLake()
    for path in [HERE / "topology.md", *runbooks()]:
        lake.add(path.name, path.read_text(encoding="utf-8"))
    catalog = lake.catalog()
    lake.confirm_catalog(CatalogReview(revision=catalog["revision"], **catalog["proposal"]))
    return lake


def run_window(case, settings, lake):
    request = AnalyzeRequest(incident_id=case["id"], objective=OBJECTIVE, scope="general", mode="mock",
                             start="2026-11-01T12:00:00Z", end="2026-11-01T12:10:00Z")
    signals = [Signal.model_validate(s) for s in case["signals"]]
    if any(not request.start <= s.timestamp <= request.end for s in signals):
        raise ValueError("Señal fuera de ventana")
    with patch("tider.console.investigation_tools.mock_signals", return_value=signals):
        result = AgenticEngine(settings, lake).analyze_live(request)
    # Preserve the emitted finding, citations and actual retrieved data for deterministic scoring.
    investigation = result.investigation
    return {"component": result.component, "status": result.status, "evidence": [
        row.model_dump(mode="json") for row in result.evidence],
        **{key: investigation[key] for key in ("candidate", "stop_reason", "review_status", "observations",
                                                "errors", "model", "model_calls", "model_requests")}}


def main(out, *, cases_path=HERE / "windows.json", protocol=HERE / "manifest.json", reverse=False, expand_activity=False):
    verify()
    load_dotenv(ROOT / ".env", override=False)
    model = os.environ.get("TIDER_MODEL")
    if not model or not os.environ.get("ANTHROPIC_API_KEY"):
        raise ValueError("Configura TIDER_MODEL y ANTHROPIC_API_KEY para medir el modelo.")
    settings = Settings(evidence_mode="mock", llm_provider="anthropic", tider_model=model,
                        agent_model_effort=os.environ.get("AGENT_MODEL_EFFORT") or None,
                        google_cloud_project="synthetic", gcp_cluster="offline", gcp_namespace="boutique",
                        agent_events_enabled=False, agent_expand_log_activity=expand_activity,
                        agent_metrics_enabled=False, agent_web_enabled=False,
                        tavily_api_key="", agent_reader_kubeconfig="", agent_kube_context="",
                        agent_observer_url="", agent_max_steps=6, agent_timeout_seconds=100, agent_log_budget=80,
                        investigation_history_path="")
    lake = synthetic_lake()
    out.mkdir(parents=True, exist_ok=False)
    from inspect import getfile
    from pathlib import Path

    from tider.console.investigation_tools import InvestigationTools
    from tider.llm import AnthropicLLM

    sources = [Path(getfile(obj)) for obj in (AgenticEngine, InvestigationTools, ContextLake, AnthropicLLM)]
    code = {f.name: digest(f) for f in [Path(__file__), ROOT / "uv.lock", *sources]}
    save(out / "run.json", {"protocol": digest(protocol), "model": model,
                            "expand_log_activity": expand_activity, "effort": settings.agent_model_effort, "steps": settings.agent_max_steps,
                            "timeout_seconds": settings.agent_timeout_seconds, "log_budget": settings.agent_log_budget,
                            "started_utc": datetime.now(timezone.utc).isoformat(),
                            "code": code})
    cases = read(cases_path)
    for case in reversed(cases) if reverse else cases:
        result = run_window(case, settings, lake)
        save(out / (case["id"] + ".json"), {"id": case["id"], "result": result})
        print(case["id"], result["status"], result["stop_reason"], result["model_calls"], flush=True)
        if any(e.get("code") == "authentication" for e in result["errors"]):
            raise RuntimeError("El proveedor rechazó la credencial; se conservó el intento.")


if __name__ == "__main__":
    from pathlib import Path

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True, help="Directorio nuevo para hasta ocho ventanas facturables")
    main(parser.parse_args().out)
