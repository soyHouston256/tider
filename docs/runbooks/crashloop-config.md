---
type: runbook
title: CrashLoopBackOff por configuración
service: ad
updated: 2026-09-18
---
# CrashLoopBackOff por configuración errónea

## Diagnóstico
1. `kubectl get pods`: el pod reinicia en bucle. Ver `logs --previous` para el error de arranque (variable faltante, puerto, ConfigMap inválido).
2. Revisar `rollout history`: ¿cambió la configuración en la última revisión?

## Mitigación
- Cambio reciente de configuración: `runbook:rollout-undo` y luego corregir con `pr:manifests`.
- Error de código en el arranque: `pr:app`; reiniciar no ayuda.
