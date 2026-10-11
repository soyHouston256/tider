"""Decisor DETERMINISTA: no usa LLM. Combina hipótesis + veredicto del juez + lista permitida."""
from __future__ import annotations
from pathlib import Path
import yaml
from ..state import Decision, Hypothesis, Verdict

DEFAULT = Path(__file__).with_name("allowlist.yaml")


def load_policy(path: str | Path = DEFAULT) -> dict:
    return yaml.safe_load(Path(path).read_text())


def escalate(reason: str) -> Decision:
    return Decision(route="escalate", action="escalate", reason=reason)


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
        need = rule.get("requires_evidence_kind")
        if need and not any(e.kind == need for e in h.evidence):
            return escalate(f"{name} exige evidencia de tipo '{need}'.")
        params = dict(h.action_params)
        if not params.get("deployment"):
            return escalate("Falta el deployment objetivo.")
        if name == "scale":
            r = params.get("replicas")
            if not isinstance(r, int) or r < 1 or r > rule["max_replicas"]:
                return escalate(f"replicas fuera de rango (máx {rule['max_replicas']}).")
        return Decision(route="runbook", action=name, params=params,
                        reason=f"Confianza {v.confidence:.2f}, acción permitida.")
    if kind == "pr":
        rule = cfg["pr"].get(name)
        if rule is None or v.confidence < rule["min_confidence"]:
            return escalate(f"PR '{name}' no permitido o confianza insuficiente ({v.confidence:.2f}).")
        return Decision(route="pr", action=name, params=h.action_params,
                        reason=f"Cambio propuesto para revisión humana (confianza {v.confidence:.2f}).")
    return escalate(f"Tipo de acción desconocido: {action}")
