"""Escalamiento a una persona. MVP: archivo + log. Luego: webhook de Slack/correo/ticket."""
from __future__ import annotations
import json, logging, time
from pathlib import Path
from ..config import ROOT

log = logging.getLogger("tider.escalate")


def escalate(alert: dict, reason: str, summary: str) -> dict:
    out = ROOT / "out" / "escalations"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{int(time.time())}-{alert.get('name','alert')}.json"
    f.write_text(json.dumps({"alert": alert, "reason": reason, "summary": summary}, indent=2, ensure_ascii=False))
    log.warning("ESCALADO: %s — %s", alert.get("name"), reason)
    return {"executed": False, "escalation": str(f)}


def verify_resolved(alert: dict) -> bool:
    """Consulta Alertmanager: ¿la alerta ya no está activa? Si no hay conexión, devuelve False (no asumimos éxito)."""
    import httpx
    from ..config import env
    try:
        r = httpx.get(f"{env('ALERTMANAGER_URL','http://localhost:9093')}/api/v2/alerts", params={"active": "true"}, timeout=10)
        active = {a["labels"].get("alertname") for a in r.json()}
        return alert.get("name") not in active
    except Exception:
        return False
