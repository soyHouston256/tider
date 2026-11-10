"""Grafo LangGraph: intake -> context -> investigate -> judge -(re-investigar)-> decide -> execute -> verify -> report.
Regla de cierre: todo camino que no termine en una alerta resuelta y verificada termina en una persona."""

from __future__ import annotations

import logging
from functools import partial

from langgraph.graph import END, START, StateGraph

from .agents.context import gather_context
from .agents.deps import Deps
from .agents.intake import intake
from .agents.investigator import investigate
from .agents.judge import judge
from .agents.reporter import report
from .decision.policy import escalate as escalate_decision
from .executor import escalate as esc
from .state import IncidentState
from .workflow.nodes import after_judge, decide_node, execute_node, preview_node, verify_node

log = logging.getLogger("tider.graph")


def build_graph(deps: Deps, *, observation_only: bool = False):
    g = StateGraph(IncidentState)
    for name, fn in [
        ("intake", intake),
        ("context", gather_context),
        ("investigate", investigate),
        ("judge", judge),
        ("decide", decide_node),
        ("execute", preview_node if observation_only else execute_node),
        ("verify", verify_node),
        ("report", report),
    ]:
        g.add_node(name, partial(fn, deps=deps))
    g.add_edge(START, "intake")
    g.add_edge("intake", "context")
    g.add_edge("context", "investigate")
    g.add_edge("investigate", "judge")
    g.add_conditional_edges("judge", after_judge, {"investigate": "investigate", "decide": "decide"})
    g.add_edge("decide", "execute")
    g.add_edge("execute", "verify")
    g.add_edge("verify", "report")
    g.add_edge("report", END)
    return g.compile()


def run_alert(graph, alert: dict) -> IncidentState:
    """Corre el flujo. Si algo falla fuera de los agentes, se escala: una alerta nunca se pierde en silencio."""
    try:
        return graph.invoke({"alert": alert, "audit": []})
    except Exception as e:
        log.exception("el flujo falló para %s", alert.get("name"))
        reason = f"Fallo interno de Tider: {type(e).__name__}: {e}"
        return {
            "alert": alert,
            "decision": escalate_decision(reason).model_dump(),
            "resolved": False,
            "error": reason,
            "execution": esc.escalate(alert, reason, "sin hipótesis (el flujo falló)"),
            "audit": [{"agent": "flujo", "error": reason}],
        }
