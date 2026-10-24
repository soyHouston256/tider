"""Present recorded workflow events as facts; never run another model to explain them."""

from .models import DecisionStep, Signal

TITLES = {
    "intake": "Recepción",
    "context": "Contexto",
    "investigator": "Investigación",
    "judge": "Evaluación",
    "decisor": "Decisión",
    "ejecutor": "Propuesta",
    "verificador": "Verificación",
    "reporter": "Reporte",
}
ROUTES = {"escalate": "Revisión humana", "runbook": "Propuesta de runbook", "pr": "Propuesta de cambio"}


def explain(audit: list[dict], evidence: list[Signal]) -> list[DecisionStep]:
    steps = []
    consulted: list[str] = []
    for sequence, event in enumerate(audit, 1):
        stage = event["agent"]
        refs = []
        status = "completed"
        if stage == "intake":
            outcome = f"Ruta de investigación: {event['handler']}"
            reason = "El receptor clasifica el nombre y el resumen de la alerta."
        elif stage == "context":
            outcome = f"{len(event.get('docs', []))} referencias recuperadas"
            reason = ", ".join(event.get("docs", [])) or event.get("skipped", "Sin contexto disponible.")
            if event.get("skipped"):
                status = "skipped"
        elif stage == "investigator":
            kinds = {tool.removeprefix("lab_") for tool in event.get("tools", [])}
            refs = [signal.id for signal in evidence if signal.source in kinds]
            consulted = list(dict.fromkeys([*consulted, *refs]))
            outcome = f"Componente propuesto: {event['component']}"
            reason = event.get("reason", "Hipótesis registrada por el investigador.")
        elif stage == "judge":
            supported = event.get("supported", False)
            outcome = f"{'Hipótesis respaldada' if supported else 'Solicita más evidencia'} · {event.get('confidence', 0):.0%}"
            reason = event.get("notes") or "; ".join(event.get("missing", [])) or "Veredicto registrado."
            status = "completed" if supported else "needs_review"
            refs = consulted.copy()
        elif stage == "decisor":
            outcome = ROUTES.get(event["route"], event["route"])
            reason = event["reason"]
            status = "needs_review"
            refs = consulted.copy()
        elif stage == "ejecutor":
            outcome = "Propuesta disponible para el operador"
            reason = "Modo observación: 0 acciones ejecutadas."
            if event.get("command"):
                reason += f" Comando propuesto: {event['command']}"
            if event.get("error"):
                reason += f" {event['error']}"
            status = "needs_review"
        elif stage == "verificador":
            outcome = "Verificación omitida" if event.get("skipped") else "Verificación completada"
            reason = event.get("skipped") or f"Incidente resuelto: {event.get('resolved', False)}"
            status = "skipped" if event.get("skipped") else "completed"
        elif stage == "reporter":
            outcome = "Informe disponible"
            reason = "El informe conserva la hipótesis, evidencia y propuesta."
            if not event.get("stored"):
                reason += " La memoria de casos resueltos no se actualizó."
        else:
            outcome = "Evento registrado"
            reason = "Consultar el detalle técnico."
        steps.append(
            DecisionStep(
                sequence=sequence,
                stage=stage,
                title=TITLES.get(stage, stage),
                outcome=outcome,
                reason=reason,
                status=status,
                evidence_ids=refs,
            )
        )
    return steps
