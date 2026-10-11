"""Grafo LangGraph: intake -> context -> investigate -> judge -(re-investigar)-> decide -> execute -> verify -> report."""
from __future__ import annotations
from functools import partial
from langgraph.graph import END, START, StateGraph
from .agents.context import gather_context
from .agents.deps import Deps
from .agents.intake import intake
from .agents.investigator import investigate
from .agents.judge import judge
from .agents.reporter import report
from .config import max_iter
from .decision.policy import decide
from .executor import escalate as esc, pr, runbook
from .state import Alert, Decision, Hypothesis, IncidentState, Verdict


def decide_node(state: IncidentState, deps: Deps) -> dict:
    h, v = Hypothesis(**state["hypothesis"]), Verdict(**state["verdict"])
    ns = Alert(**state["alert"]).namespace
    d = decide(h, v, ns, deps.policy)
    return {"decision": d.model_dump(), "audit": [{"agent": "decisor", "route": d.route, "action": d.action, "reason": d.reason}]}


def execute_node(state: IncidentState, deps: Deps) -> dict:
    d, a, h = Decision(**state["decision"]), state["alert"], state["hypothesis"]
    summary = f"{h['component']}: {h['reason']}"
    if d.route == "runbook":
        res = runbook.execute(d.action, d.params, a.get("namespace", "otel-demo"))
    elif d.route == "pr":
        res = pr.propose(d.action, d.params, a, summary)
    else:
        res = esc.escalate(a, d.reason, summary)
    return {"execution": res, "audit": [{"agent": "ejecutor", **{k: v for k, v in res.items() if k != "output"}}]}


def verify_node(state: IncidentState, deps: Deps) -> dict:
    ex = state.get("execution", {})
    ok = bool(ex.get("executed")) and esc.verify_resolved(state["alert"])
    return {"resolved": ok, "audit": [{"agent": "verificador", "resolved": ok}]}


def after_judge(state: IncidentState) -> str:
    v = state["verdict"]
    if not v["supported"] and v.get("missing") and state.get("iterations", 0) <= max_iter():
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
    return graph.invoke({"alert": alert, "audit": []})
