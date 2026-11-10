---
type: runbook
title: CPU alta sostenida
updated: 2026-10-11
---
# CPU alta sostenida

## Diagnóstico
1. `rate(container_cpu_usage_seconds_total[5m])` frente al `limit`. ¿Hay throttling?
2. ¿La carga subió (más peticiones) o el código gasta más por petición?
3. `deployment_status`: réplicas actuales, si hay HPA y si hubo un rollout reciente.

## Mitigación
- Más carga legítima y **sin HPA**: `runbook:scale` hacia arriba (máx. 5 réplicas).
- Si un HPA maneja el deployment, escalar a mano se pisa con él: `escalate` (o `pr:manifests` para ajustar el HPA).
- Gasto anómalo tras un despliegue: `runbook:rollout-undo`.
