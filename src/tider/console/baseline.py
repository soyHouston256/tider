"""Baseline por reglas: la hipótesis se obtiene de señales, nunca del ID del caso."""

import re

from .models import Analysis, Signal


def diagnose(incident_id: str, service: str, evidence: list[Signal]) -> Analysis:
    errors = [s for s in evidence if s.severity.upper() in {"ERROR", "CRITICAL", "ALERT", "EMERGENCY"}]
    redis = [
        s
        for s in errors
        if s.service in {"cartservice", "redis-cart"}
        and re.search(
            r"redis(?:-cart)?(?: connection|:6379)?.{0,60}(refused|unavailable|timeout)", s.message, re.I
        )
    ]
    cart = [
        s
        for s in errors
        if s.service in {"frontend", "checkoutservice", "cartservice"}
        and re.search(r"cartservice.{0,60}(no available endpoints|connection refused)", s.message, re.I)
    ]
    if redis and not cart:
        return Analysis(
            incident_id=incident_id,
            hypothesis="Redis no está disponible para cartservice.",
            component="redis-cart",
            confidence=0.7,
            evidence=evidence,
            recommendation="Comprobar la disponibilidad de redis-cart y la conexión desde cartservice.",
        )
    if cart and not redis:
        return Analysis(
            incident_id=incident_id,
            hypothesis="Cart Service no tiene un endpoint disponible.",
            component="cartservice",
            confidence=0.7,
            evidence=evidence,
            recommendation="Comprobar réplicas, readiness y endpoints de cartservice en boutique.",
        )
    return Analysis(
        incident_id=incident_id,
        hypothesis="La evidencia no permite identificar una causa raíz.",
        component=service,
        confidence=0,
        evidence=evidence,
        recommendation="Revisar la ventana y añadir trazas, métricas y eventos del despliegue.",
        status="insufficient_evidence",
    )
