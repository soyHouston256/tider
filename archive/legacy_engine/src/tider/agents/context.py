"""Agente 2 — Contexto (RAG sobre el context lake): runbooks, arquitectura, incidentes parecidos y topología."""

from __future__ import annotations

from ..state import Alert, IncidentState


def gather_context(state: IncidentState, deps) -> dict:
    if not deps.use_rag:
        return {"context": [], "audit": [{"agent": "context", "skipped": "rag desactivado"}]}
    a = Alert(**state["alert"])
    q = f"{a.name} {a.service or ''} {a.annotations.get('summary', '')} {state.get('handler', '')}"
    ctx: list[dict] = []
    ctx += deps.store.search(q, k=3, doc_type="runbook", service=a.service)
    ctx += deps.store.search(q, k=1, doc_type="architecture")
    ctx += deps.store.search(q, k=2, doc_type="incident", service=a.service)
    if a.service:
        n = deps.store.neighbors(a.service)
        ctx.append(
            {
                "doc_id": "topology",
                "doc_type": "topology",
                "title": f"Dependencias de {a.service}",
                "service": a.service,
                "updated": None,
                "text": f"upstream (llaman a {a.service}): {n['upstream']}; downstream (dependencias de {a.service}): {n['downstream']}",
                "score": 1.0,
            }
        )
    return {"context": ctx, "audit": [{"agent": "context", "docs": [c["doc_id"] for c in ctx]}]}
