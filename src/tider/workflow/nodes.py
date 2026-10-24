"""Decision, execution, verification and routing nodes for the shared graph."""

from ..agents.deps import Deps
from ..config import max_iter
from ..decision.policy import decide
from ..decision.policy import escalate as escalate_decision
from ..executor import escalate as esc
from ..executor import pr, runbook, verify
from ..state import Alert, Decision, Hypothesis, IncidentState, Verdict


def decide_node(state: IncidentState, deps: Deps) -> dict:
    h, v = Hypothesis(**state["hypothesis"]), Verdict(**state["verdict"])
    ns = Alert(**state["alert"]).namespace
    d = decide(h, v, ns, deps.policy)
    if (
        d.route == "runbook"
    ):  # límites con estado: interruptor, enfriamiento por deployment y presupuesto global
        blocked = deps.safety.reserve_action(d.params["deployment"])
        if blocked:
            d = escalate_decision(blocked)
    return {
        "decision": d.model_dump(),
        "audit": [{"agent": "decisor", "route": d.route, "action": d.action, "reason": d.reason}],
    }


def execute_node(state: IncidentState, deps: Deps) -> dict:
    d, a, h = Decision(**state["decision"]), state["alert"], state["hypothesis"]
    summary = f"{h['component']}: {h['reason']}"
    try:
        if d.route == "runbook":
            res = runbook.execute(d.action, d.params, a.get("namespace", "otel-demo"))
            if res.get("dry_run"):  # modo sombra: una persona ve qué habría hecho Tider
                res["escalation"] = esc.escalate(a, f"DRY-RUN: Tider ejecutaría `{res['command']}`", summary)[
                    "escalation"
                ]
        elif d.route == "pr":
            res = pr.propose(d.action, d.params, a, summary)
        else:
            res = esc.escalate(a, d.reason, summary)
    except Exception as e:  # un fallo del ejecutor siempre termina en una persona
        res = {
            **esc.escalate(a, f"Fallo del ejecutor en {d.action}: {type(e).__name__}: {e}", summary),
            "error": str(e),
        }
    return {
        "execution": res,
        "audit": [{"agent": "ejecutor", **{k: v for k, v in res.items() if k != "output"}}],
    }


def verify_node(state: IncidentState, deps: Deps) -> dict:
    ex, d = state.get("execution", {}), state.get("decision", {})
    if d.get("route") != "runbook" or ex.get("dry_run") or "error" in ex:
        return {"resolved": False, "audit": [{"agent": "verificador", "skipped": "sin acción ejecutada"}]}
    ok = bool(ex.get("executed")) and verify.verify_resolved(
        state["alert"], d.get("params", {}).get("deployment")
    )
    entry = {"agent": "verificador", "resolved": ok}
    if not ok:  # la acción falló o la alerta sigue activa: escalar, nunca quedarse callado
        why = "la alerta sigue activa" if ex.get("executed") else f"falló: {ex.get('output', '')[:300]}"
        h = state["hypothesis"]
        entry["escalation"] = esc.escalate(
            state["alert"],
            f"Tider ejecutó `{ex.get('command')}` y {why}.",
            f"{h['component']}: {h['reason']}",
        )["escalation"]
    return {"resolved": ok, "audit": [entry]}


def after_judge(state: IncidentState) -> str:
    v = state["verdict"]
    if not v["supported"] and v.get("missing") and state.get("iterations", 0) < max_iter():
        return "investigate"
    return "decide"


def preview_node(state: IncidentState, deps: Deps) -> dict:
    """Diagnóstico: muestra la decisión sin ejecutar ni notificar, al margen del entorno."""
    d = Decision(**state["decision"])
    execution = {
        "executed": False,
        "dry_run": True,
        "mode": "observation",
        "requires_operator": True,
        "route": d.route,
    }
    if d.route == "runbook":
        try:
            execution["command"] = " ".join(runbook.build(d.action, d.params, state["alert"]["namespace"]))
        except (ValueError, KeyError, TypeError):
            execution["error"] = "No se pudo construir una propuesta válida."
    return {"execution": execution, "audit": [{"agent": "ejecutor", **execution}]}
