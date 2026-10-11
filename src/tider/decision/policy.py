"""Decisor DETERMINISTA: no usa LLM. Combina hipótesis + veredicto del juez + lista permitida.
Las precondiciones se leen de datos estructurados de herramientas (Evidence.data), nunca del texto del LLM."""
from __future__ import annotations
from pathlib import Path
import yaml
from ..state import Decision, Hypothesis, Verdict

DEFAULT = Path(__file__).with_name("allowlist.yaml")


def load_policy(path: str | Path = DEFAULT) -> dict:
    return yaml.safe_load(Path(path).read_text(encoding="utf-8"))


def escalate(reason: str) -> Decision:
    return Decision(route="escalate", action="escalate", reason=reason)


def observed_status(h: Hypothesis, deployment: str) -> dict | None:
    """Último deployment_status observado para el deployment objetivo."""
    return next((e.data for e in reversed(h.evidence)
                 if e.kind == "deploy" and e.data and e.data.get("deployment") == deployment), None)


def decide(h: Hypothesis, v: Verdict, namespace: str, cfg: dict) -> Decision:
    action = h.proposed_action
    if action == "escalate":
        return escalate("El investigador propuso escalar.")
    if not v.supported:
        return escalate(f"El juez no respalda la hipótesis. Falta: {', '.join(v.missing) or 'evidencia'}.")
    if namespace not in cfg["namespaces"]:
        return escalate(f"Namespace '{namespace}' fuera de la lista permitida.")

    kind, _, name = action.partition(":")
    if kind == "runbook":
        rule = cfg["runbook"].get(name)
        if rule is None:
            return escalate(f"Acción '{name}' no está en la lista permitida.")
        if v.confidence < rule["min_confidence"]:
            return escalate(f"Confianza {v.confidence:.2f} < {rule['min_confidence']} requerida para {name}.")
        params = dict(h.action_params)
        dep = params.get("deployment")
        if not dep:
            return escalate("Falta el deployment objetivo.")
        if dep not in {h.component, *h.propagation}:
            return escalate(f"'{dep}' no es el componente de origen ni está en la cadena de propagación.")
        if dep in cfg.get("protected_deployments", []):
            return escalate(f"'{dep}' está protegido: solo una persona actúa sobre él.")
        st = observed_status(h, dep)
        if name in ("rollout-undo", "scale") and not st:
            return escalate(f"{name} exige deployment_status de '{dep}'.")
        if name == "rollout-undo":
            age, limit = st.get("last_rollout_age_minutes"), rule["max_rollout_age_minutes"]
            if st.get("revisions", 0) < 2 or age is None or age > limit:
                return escalate(f"No hay un rollout reciente que deshacer (último hace {age} min, máx {limit}).")
        if name == "scale":
            if st.get("hpa"):
                return escalate(f"'{dep}' lo maneja el HPA '{st['hpa']}': escalar a mano se pisa con él.")
            r, cur = params.get("replicas"), st.get("replicas", 0)
            if not isinstance(r, int) or r <= cur or r > rule["max_replicas"]:
                return escalate(f"replicas={r!r} inválido: debe ser mayor que {cur} (actual) y como máximo {rule['max_replicas']}.")
            params["current_replicas"] = cur   # precondición de kubectl scale: si cambió desde que se observó, no escala
        return Decision(route="runbook", action=name, params=params,
                        reason=f"Confianza {v.confidence:.2f}, acción permitida.")
    if kind == "pr":
        rule = cfg["pr"].get(name)
        if rule is None or v.confidence < rule["min_confidence"]:
            return escalate(f"PR '{name}' no permitido o confianza insuficiente ({v.confidence:.2f}).")
        return Decision(route="pr", action=name, params=h.action_params,
                        reason=f"Cambio propuesto para revisión humana (confianza {v.confidence:.2f}).")
    return escalate(f"Tipo de acción desconocido: {action}")
