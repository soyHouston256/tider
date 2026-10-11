"""Verificador: espera a que el rollout termine y luego consulta Alertmanager hasta que ESTA alerta deje de estar
activa o se acabe TIDER_VERIFY_TIMEOUT. Ante cualquier duda devuelve False: nunca asumimos éxito."""
from __future__ import annotations
import logging, time
import httpx
from ..config import env, verify_interval, verify_timeout
from ..tools import kube

log = logging.getLogger("tider.verify")


def alert_active(alert: dict) -> bool:
    """Busca la alerta por fingerprint; si no hay, por labels completos; si tampoco, por nombre. Sin respuesta = activa."""
    try:
        r = httpx.get(f"{env('ALERTMANAGER_URL', 'http://localhost:9093')}/api/v2/alerts",
                      params={"active": "true"}, timeout=10)
        r.raise_for_status()
        active = r.json()
    except Exception:
        log.exception("Alertmanager no responde")
        return True
    fp, labels = alert.get("fingerprint"), alert.get("labels") or {}
    if fp:
        return any(a.get("fingerprint") == fp for a in active)
    if labels:
        return any(a.get("labels") == labels for a in active)
    return any(a.get("labels", {}).get("alertname") == alert.get("name") for a in active)


def verify_resolved(alert: dict, deployment: str | None = None) -> bool:
    deadline = time.monotonic() + verify_timeout()
    if deployment:
        try:
            kube.rollout_status(deployment, alert.get("namespace", "otel-demo"), verify_timeout())
        except Exception:
            log.exception("el rollout de %s no terminó bien", deployment)
            return False
    while True:
        if not alert_active(alert):
            return True
        if time.monotonic() + verify_interval() > deadline:
            return False
        time.sleep(verify_interval())
