"""Compose the shared graph with lab evidence and a selected reasoning provider."""

from importlib.resources import files
from pathlib import Path

from tider.agents.deps import Deps
from tider.decision.policy import load_policy
from tider.graph import build_graph
from tider.lake.ingest import ingest_dir
from tider.lake.store import InMemoryStore
from tider.llm import LLM, AnthropicLLM, ScriptedLLM
from tider.tools.base import Tool, ToolRegistry

from .baseline import diagnose
from .catalog_diagnosis import diagnose_catalog
from .explanation import explain
from .models import Analysis, AnalyzeRequest, Signal, WorkflowResult
from .settings import Settings

SIGNAL_KINDS = ("log", "metric", "trace")


def reader(records: list[dict]):
    """No-argument tool: model arguments cannot replace the collected evidence."""

    def read():
        return {"signals": records} if records else ""

    return read


def baseline_model(baseline: Analysis, service: str) -> ScriptedLLM:
    supported = baseline.status == "hypothesis"
    return ScriptedLLM(
        {
            "investigator": [
                *({"action": "tool", "tool": "lab_" + kind, "args": {}} for kind in SIGNAL_KINDS),
                {
                    "action": "final",
                    "hypothesis": {
                        "component": baseline.component,
                        "reason": baseline.hypothesis,
                        "propagation": list(dict.fromkeys([baseline.component, service])),
                        "proposed_action": "escalate",
                        "action_params": {},
                        "cited_docs": [],
                    },
                },
            ],
            "judge": {
                "supported": supported,
                "confidence": baseline.confidence,
                "missing": [] if supported else ["Señales que respalden una causa concreta"],
                "notes": "Baseline por reglas; puntuación heurística, sin calibración estadística.",
            },
            "reporter": baseline.hypothesis + "\n" + baseline.recommendation,
        }
    )


class LabEngine:
    def __init__(self, settings: Settings, context_lake=None):
        self.settings = settings
        self.context_lake = context_lake

    def analyze_live(self, request: AnalyzeRequest, emit=None) -> Analysis:
        from .agentic import AgenticEngine

        return AgenticEngine(self.settings, self.context_lake).analyze_live(request, emit=emit)

    def _model(self, baseline: Analysis, service: str) -> LLM:
        if self.settings.llm_provider == "none":
            return baseline_model(baseline, service)
        if not self.settings.tider_model:
            raise ValueError("Configura TIDER_MODEL antes de activar el modelo.")
        return AnthropicLLM(model=self.settings.tider_model)

    def analyze(self, request: AnalyzeRequest, evidence: list[Signal]) -> Analysis:
        service = request.service or "general"
        snapshot = self.context_lake.catalog() if self.context_lake else None
        if snapshot is not None and snapshot["status"] != "empty" and (request.mode or self.settings.evidence_mode) != "mock":
            baseline = diagnose_catalog(request.incident_id, service, evidence, snapshot.get("confirmed") or {})
        else:
            baseline = diagnose(request.incident_id, service, evidence)
        registry = ToolRegistry()
        for kind in SIGNAL_KINDS:
            records = [signal.model_dump(mode="json") for signal in evidence if signal.source == kind]
            registry.register(
                Tool(
                    "lab_" + kind, f"Evidencia de {kind} en la ventana del incidente.", kind, reader(records)
                )
            )
        # Mutable dependencies are isolated per run (including scripted model cursors).
        store = InMemoryStore()
        ingest_dir(store, Path(str(files("tider.console").joinpath("resources/context"))))
        policy = load_policy()
        policy["namespaces"] = [self.settings.gcp_namespace]
        model = self._model(baseline, service)
        graph = build_graph(Deps(model, store, registry, policy), observation_only=True)
        # HTTP owns failures; run_alert's external escalation is intentionally not used.
        state = graph.invoke(
            {
                "alert": {
                    "name": request.incident_id,
                    "service": service,
                    "namespace": self.settings.gcp_namespace,
                    "starts_at": request.start.isoformat(),
                    "annotations": {"summary": "Análisis de evidencia en Online Boutique"},
                },
                "audit": [],
            }
        )
        hypothesis, verdict = state["hypothesis"], state["verdict"]
        workflow = WorkflowResult(**{key: state[key] for key in WorkflowResult.model_fields if key in state})
        return Analysis(
            incident_id=request.incident_id,
            hypothesis=hypothesis["reason"],
            component=hypothesis["component"],
            confidence=verdict["confidence"],
            evidence=evidence,
            recommendation=baseline.recommendation
            if self.settings.llm_provider == "none"
            else state["decision"]["reason"],
            status="hypothesis" if verdict["supported"] else "insufficient_evidence",
            reasoning_mode="rules" if self.settings.llm_provider == "none" else "anthropic",
            namespace=self.settings.gcp_namespace,
            workflow=workflow,
            decision_steps=explain(state["audit"], evidence),
        )
