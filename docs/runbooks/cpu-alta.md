---
type: runbook
title: CPU alta sostenida
service: ad
updated: 2026-09-25
---
# CPU alta sostenida

## Diagnóstico
1. `rate(container_cpu_usage_seconds_total[5m])` frente al `limit`. ¿Hay throttling?
2. ¿La carga subió (más peticiones) o el código gasta más por petición?

## Mitigación
- Más carga legítima: `runbook:scale` (máx. 5 réplicas).
- Gasto anómalo tras un despliegue: `runbook:rollout-undo`.
- Si el HPA ya está al máximo: `escalate`.
