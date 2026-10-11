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
from .config import max_iter
from .decision.policy import decide, escalate as escalate_decision
from .executor import escalate as esc, pr, runbook, verify
from .state import Alert, Decision, Hypothesis, IncidentState, Verdict

log = logging.getLogger("tider.graph")


def decide_node(state: IncidentState, deps: Deps) -> dict:
    h, v = Hypothesis(**state["hypothesis"]), Verdict(**state["verdict"])
    ns = Alert(**state["alert"]).namespace
    d = decide(h, v, ns, deps.policy)
    if d.route == "runbook":   # límites con estado: interruptor, enfriamiento por deployment y presupuesto global
        blocked = deps.safety.reserve_action(d.params["deployment"])
        if blocked:
            d = escalate_decision(blocked)
    return {"decision": d.model_dump(), "audit": [{"agent": "decisor", "route": d.route, "action": d.action, "reason": d.reason}]}


def execute_node(state: IncidentState, deps: Deps) -> dict:
    d, a, h = Decision(**state["decision"]), state["alert"], state["hypothesis"]
    summary = f"{h['component']}: {h['reason']}"
    try:
        if d.route == "runbook":
            res = runbook.execute(d.action, d.params, a.get("namespace", "otel-demo"))
            if res.get("dry_run"):   # modo sombra: una persona ve qué habría hecho Tider
                res["escalation"] = esc.escalate(a, f"DRY-RUN: Tider ejecutaría `{res['command']}`", summary)["escalation"]
        elif d.route == "pr":
            res = pr.propose(d.action, d.params, a, summary)
        else:
            res = esc.escalate(a, d.reason, summary)
    except Exception as e:   # un fallo del ejecutor siempre termina en una persona
        res = {**esc.escalate(a, f"Fallo del ejecutor en {d.action}: {type(e).__name__}: {e}", summary), "error": str(e)}
    return {"execution": res, "audit": [{"agent": "ejecutor", **{k: v for k, v in res.items() if k != "output"}}]}


def verify_node(state: IncidentState, deps: Deps) -> dict:
    ex, d = state.get("execution", {}), state.get("decision", {})
    if d.get("route") != "runbook" or ex.get("dry_run") or "error" in ex:
        return {"resolved": False, "audit": [{"agent": "verificador", "skipped": "sin acción ejecutada"}]}
    ok = bool(ex.get("executed")) and verify.verify_resolved(state["alert"], d.get("params", {}).get("deployment"))
    entry = {"agent": "verificador", "resolved": ok}
    if not ok:   # la acción falló o la alerta sigue activa: escalar, nunca quedarse callado
        why = "la alerta sigue activa" if ex.get("executed") else f"falló: {ex.get('output', '')[:300]}"
        h = state["hypothesis"]
        entry["escalation"] = esc.escalate(state["alert"], f"Tider ejecutó `{ex.get('command')}` y {why}.",
                                           f"{h['component']}: {h['reason']}")["escalation"]
    return {"resolved": ok, "audit": [entry]}


def after_judge(state: IncidentState) -> str:
    v = state["verdict"]
    if not v["supported"] and v.get("missing") and state.get("iterations", 0) < max_iter():
        return "investigate"
    return "decide"


def build_graph(deps: Deps):
    g = StateGraph(IncidentState)
    for name, fn in [("intake", intake), ("context", gather_context), ("investigate", investigate), ("judge", judge),
                     ("decide", decide_node), ("execute", execute_node), ("verify", verify_node), ("report", report)]:
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
        return {"alert": alert, "decision": escalate_decision(reason).model_dump(), "resolved": False, "error": reason,
                "execution": esc.escalate(alert, reason, "sin hipótesis (el flujo falló)"),
                "audit": [{"agent": "flujo", "error": reason}]}
