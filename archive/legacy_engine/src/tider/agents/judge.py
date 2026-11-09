"""Agente 4 — Juez: verifica que la hipótesis esté respaldada por la evidencia. Combina LLM + chequeos deterministas."""

from __future__ import annotations

from datetime import date

from ..state import Hypothesis, IncidentState, Verdict
from .prompts import JUDGE_SYSTEM as SYSTEM

STALE_DAYS = 180
NOT_EVIDENCE = {"doc", "error", "empty"}  # documentos, fallos y consultas vacías no cuentan como telemetría


def judge(state: IncidentState, deps) -> dict:
    h = Hypothesis(**state["hypothesis"])
    it = state.get("iterations", 0) + 1
    if not deps.use_judge:  # ablación: sin juez, se confía en la hipótesis
        v = Verdict(confidence=0.9, supported=h.proposed_action != "escalate", notes="juez desactivado")
        return {"verdict": v.model_dump(), "iterations": it, "audit": [{"agent": "judge", "disabled": True}]}

    ev = "\n".join(f"- ({e.kind}) {e.source}: {e.summary[:400]}" for e in h.evidence) or "(sin evidencia)"
    try:
        out = (deps.judge_llm or deps.llm).complete_json(
            "judge", SYSTEM, f"HIPÓTESIS: {h.model_dump_json(exclude={'evidence'})}\nEVIDENCIA:\n{ev}"
        )
        v = Verdict(
            **{k: out[k] for k in ("supported", "confidence", "missing", "notes") if out.get(k) is not None}
        )
    except (
        Exception
    ) as e:  # JSON inválido, veredicto mal formado o fallo de la API: sin veredicto no hay respaldo
        v = Verdict(supported=False, confidence=0.0, notes=f"juez sin respuesta válida ({type(e).__name__})")

    # Chequeos deterministas (el LLM no puede subir la confianza por encima de lo que la evidencia permite)
    telemetry_kinds = {e.kind for e in h.evidence if e.kind not in NOT_EVIDENCE}
    cap, notes = 1.0, []
    if not telemetry_kinds:
        v.supported, cap = False, 0.0
        notes.append("sin evidencia de telemetría")
    elif len(telemetry_kinds) < 2:
        cap = min(cap, 0.7)
        notes.append("evidencia de un solo tipo")
    stale = 0
    for e in h.evidence:
        if e.kind == "doc":
            for c in state.get("context", []):
                if c["doc_id"] == e.source and c.get("updated"):
                    if (date.today() - date.fromisoformat(c["updated"])).days > STALE_DAYS:
                        stale += 1
    if stale:
        cap = min(cap, 1.0 - 0.1 * stale)
        notes.append(f"{stale} documento(s) citado(s) desactualizado(s)")
    v.confidence = round(min(v.confidence, cap), 2)
    v.notes = "; ".join(filter(None, [v.notes, *notes]))
    return {
        "verdict": v.model_dump(),
        "iterations": it,
        "audit": [
            {
                "agent": "judge",
                "supported": v.supported,
                "confidence": v.confidence,
                "missing": v.missing,
                "notes": v.notes,
            }
        ],
    }
