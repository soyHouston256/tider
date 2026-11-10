"""Compose lab evidence with the rules baseline (no LLM) or the adaptive engine (LLM)."""

from tider.state import Decision, Evidence, Hypothesis, Verdict
from tider.tools.base import Tool, ToolRegistry

from .baseline import diagnose
from .catalog_diagnosis import diagnose_catalog
from .explanation import explain
from .models import Analysis, AnalyzeRequest, Signal, WorkflowResult
from .settings import Settings

SIGNAL_KINDS = ("log", "metric", "trace")
RULES_NOTE = "Baseline por reglas; puntuación heurística, sin calibración estadística."
NOT_EVIDENCE = {"error", "empty"}


def reader(records: list[dict]):
    """No-argument tool: model arguments cannot replace the collected evidence."""

    def read():
        return {"signals": records} if records else ""

    return read


def verdict_for(baseline: Analysis, evidence: list[Evidence]) -> Verdict:
    """Deterministic checks kept from the archived judge: no telemetry, no support; one kind, capped."""
    supported = baseline.status == "hypothesis"
    confidence, notes = float(baseline.confidence or 0), [RULES_NOTE]
    kinds = {item.kind for item in evidence if item.kind not in NOT_EVIDENCE}
    if not kinds:
        supported, confidence = False, 0.0
        notes.append("sin evidencia de telemetría")
    elif len(kinds) < 2:
        confidence = min(confidence, 0.7)
        notes.append("evidencia de un solo tipo")
    return Verdict(
        supported=supported,
        confidence=round(confidence, 2),
        missing=[] if supported else ["Señales que respalden una causa concreta"],
        notes="; ".join(notes),
    )


class LabEngine:
    def __init__(self, settings: Settings, context_lake=None):
        self.settings = settings
        self.context_lake = context_lake

    def analyze_live(self, request: AnalyzeRequest, emit=None) -> Analysis:
        from .agentic import AgenticEngine

        return AgenticEngine(self.settings, self.context_lake).analyze_live(request, emit=emit)

    def analyze(self, request: AnalyzeRequest, evidence: list[Signal]) -> Analysis:
        """Rules-only diagnosis. Records only the steps that run; nothing is executed."""
        service = request.service or "general"
        snapshot = self.context_lake.catalog() if self.context_lake else None
        if (
            snapshot is not None
            and snapshot["status"] != "empty"
            and (request.mode or self.settings.evidence_mode) != "mock"
        ):
            baseline = diagnose_catalog(
                request.incident_id, service, evidence, snapshot.get("confirmed") or {}
            )
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
        tools = ["lab_" + kind for kind in SIGNAL_KINDS]
        observed = [Evidence(source=name, **registry.call(name)) for name in tools]
        verdict = verdict_for(baseline, observed)
        hypothesis = Hypothesis(
            component=baseline.component,
            reason=baseline.hypothesis,
            propagation=list(dict.fromkeys([baseline.component, service])),
            evidence=observed,
        )
        decision = Decision(
            route="escalate", action="escalate", reason="Revisión humana; no se ejecutan reparaciones."
        )
        report = baseline.hypothesis + "\n" + baseline.recommendation
        audit = [
            {
                "agent": "investigator",
                "tools": tools,
                "component": hypothesis.component,
                "action": decision.action,
                "reason": hypothesis.reason,
            },
            {"agent": "judge", **verdict.model_dump()},
            {
                "agent": "decisor",
                "route": decision.route,
                "action": decision.action,
                "reason": decision.reason,
            },
            {"agent": "reporter", "stored": None},
        ]
        workflow = WorkflowResult(
            handler="rules_baseline",
            hypothesis=hypothesis,
            verdict=verdict,
            decision=decision,
            execution={"mode": "observation", "executed": False, "requires_operator": True},
            resolved=False,
            report=report,
            audit=audit,
        )
        return Analysis(
            incident_id=request.incident_id,
            hypothesis=hypothesis.reason,
            component=hypothesis.component,
            confidence=verdict.confidence,
            evidence=evidence,
            recommendation=baseline.recommendation,
            status="hypothesis" if verdict.supported else "insufficient_evidence",
            engine="rules",
            reasoning_mode="rules",
            namespace=self.settings.gcp_namespace,
            workflow=workflow,
            decision_steps=explain(audit, evidence),
        )
