---
type: runbook
title: Aumento de errores en un servicio (cascada)
updated: 2026-10-11
---
# Aumento de errores en un servicio

## Diagnóstico
1. Identificar el servicio con más errores en las trazas, pero **no asumir que es el origen**: ubicar el servicio más abajo en la cadena de llamadas que ya falla (ver arquitectura).
2. Comparar con los servicios downstream (p. ej. `cart` depende de `valkey-cart`). Si la dependencia está caída o lenta, el origen es la dependencia.
3. Revisar eventos de Kubernetes y estado de pods de la dependencia.
4. Si los pods están sanos, sin reinicios ni rollouts recientes, y los errores son de lógica de negocio (pago rechazado, token inválido), la falla está en la aplicación o en un feature flag: ninguna acción de runbook la arregla.

## Mitigación
- Dependencia en `CrashLoopBackOff`: seguir el runbook de CrashLoopBackOff; reiniciar o escalar réplicas de un pod que no arranca no ayuda.
- Dependencia sana pero saturada (CPU o latencia alta, sin HPA): `runbook:scale` hacia arriba (máx. 5).
- Error introducido por un despliegue reciente del propio servicio: `runbook:rollout-undo` (requiere `deployment_status` con un rollout reciente).
- Pods sanos y errores de aplicación o de feature flag: `escalate`.
- Sin evidencia clara: `escalate`.
