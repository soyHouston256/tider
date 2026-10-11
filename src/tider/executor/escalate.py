"""Escalamiento a una persona: archivo en out/escalations + log + Slack (si TIDER_SLACK_WEBHOOK está definido).
Luego: correo/ticket."""
from __future__ import annotations
import json, logging, re, time, uuid
import httpx
from ..config import env, out_dir

log = logging.getLogger("tider.escalate")


def safe_name(text: object) -> str:
    """Nombre de archivo seguro: el nombre de la alerta viene de fuera (labels de Alertmanager)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "_", str(text))[:80] or "alerta"


def escalate(alert: dict, reason: str, summary: str) -> dict:
    out = out_dir() / "escalations"
    out.mkdir(parents=True, exist_ok=True)
    f = out / f"{time.strftime('%Y%m%dT%H%M%S')}-{safe_name(alert.get('name', 'alert'))}-{uuid.uuid4().hex[:6]}.json"
    f.write_text(json.dumps({"alert": alert, "reason": reason, "summary": summary}, indent=2, ensure_ascii=False),
                 encoding="utf-8")
    log.warning("ESCALADO: %s — %s", alert.get("name"), reason)
    notify(f"Tider escala {alert.get('name')} ({alert.get('service')}): {reason}\n{summary}")
    return {"executed": False, "escalation": str(f)}


def notify(text: str) -> None:
    url = env("TIDER_SLACK_WEBHOOK")
    if not url:
        return
    try:
        httpx.post(url, json={"text": text[:3000]}, timeout=10).raise_for_status()
    except Exception:   # el archivo y el log ya quedaron: un Slack caído no frena el flujo
        log.exception("no se pudo notificar a Slack")
