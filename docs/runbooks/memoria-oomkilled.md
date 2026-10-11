---
type: runbook
title: Pod OOMKilled / uso de memoria creciente
service: recommendation
updated: 2026-09-20
---
# Pod OOMKilled / memoria creciente

## Síntomas
Alerta de memoria alta o reinicios con motivo `OOMKilled`. En `kubectl describe pod` aparece `Last State: Terminated (OOMKilled)`.

## Diagnóstico
1. Revisar `container_memory_working_set_bytes` del pod en los últimos 30 min: ¿crece sin parar (fuga) o salta de golpe (pico)?
2. Revisar si hubo un rollout reciente (`rollout history`). Si empezó tras un despliegue, sospechar de ese cambio.
3. Revisar el límite de memoria en el manifiesto frente al uso normal.

## Mitigación
- Fuga que reaparece tras reiniciar: `runbook:rollout-restart` alivia, pero hay que abrir un PR (`pr:app`) para corregir la causa.
- Límite demasiado bajo respecto al uso normal: `pr:manifests` para subir el límite (no se corrige reiniciando).
- Empezó justo tras un despliegue: `runbook:rollout-undo` (requiere evidencia del rollout).
