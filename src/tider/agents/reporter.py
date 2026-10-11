"""Agente 7 — Reportero/aprendiz: postmortem + guarda el incidente en el lake para casos futuros.
Solo se aprende de incidentes VERIFICADOS (la alerta se resolvió tras la acción): guardar hipótesis sin verificar
haría que Tider se citara a sí mismo como evidencia en el siguiente incidente."""
from __future__ import annotations
from datetime import date
from ..lake.models import Chunk, Doc
from ..state import IncidentState

SYSTEM = "Eres el Reportero de Tider. Redacta un postmortem breve en español (Resumen, Causa raíz, Evidencia, Acción, Siguiente paso)."


def report(state: IncidentState, deps) -> dict:
    h, d, ex = state.get("hypothesis", {}), state.get("decision", {}), state.get("execution", {})
    facts = (f"Alerta: {state['alert']}\nCausa: {h.get('component')} — {h.get('reason')}\n"
             f"Propagación: {h.get('propagation')}\nDecisión: {d}\nEjecución: {ex}\nResuelta: {state.get('resolved')}")
    try:
        text = deps.llm.complete_text("reporter", SYSTEM, facts)
    except Exception:
        text = "# Postmortem (plantilla)\n" + facts
    if not state.get("resolved"):
        return {"report": text, "audit": [{"agent": "reporter", "stored": None, "why": "no verificado: no se aprende"}]}
    alert = state["alert"]
    doc = Doc(id=f"incident://{alert.get('name')}/{alert.get('starts_at') or date.today().isoformat()}",
              doc_type="incident", service=alert.get("service"), title=f"Incidente {alert.get('name')}",
              updated=date.today(), meta={"resolved": True, "action": d.get("action")})
    deps.store.upsert(doc, [Chunk(doc.id, 0, f"{alert.get('name')} {h.get('component')} {h.get('reason')} acción {d.get('action')} "
                                             f"(verificado: la alerta se resolvió tras la acción)\n{text}")], [])
    return {"report": text, "audit": [{"agent": "reporter", "stored": doc.id}]}
