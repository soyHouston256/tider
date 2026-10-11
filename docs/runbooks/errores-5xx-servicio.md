---
type: runbook
title: Aumento de errores en un servicio (cascada)
service: cart
updated: 2026-09-22
---
# Aumento de errores en un servicio

## Diagnóstico
1. Identificar el servicio con más errores en las trazas, pero **no asumir que es el origen**: ubicar el servicio más abajo en la cadena de llamadas que ya falla (ver arquitectura).
2. Comparar con los servicios downstream (p. ej. `cart` depende de `valkey-cart`). Si la dependencia está caída o lenta, el origen es la dependencia.
3. Revisar eventos de Kubernetes y estado de pods de la dependencia.

## Mitigación
- Dependencia con pods en `CrashLoopBackOff` o sin réplicas: `runbook:scale` (máx. 5) o `runbook:rollout-restart` sobre la dependencia.
- Error introducido por un despliegue reciente del propio servicio: `runbook:rollout-undo`.
- Sin evidencia clara: `escalate`.
