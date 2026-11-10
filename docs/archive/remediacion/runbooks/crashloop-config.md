---
type: runbook
title: CrashLoopBackOff por configuración
updated: 2026-10-11
---
# CrashLoopBackOff por configuración errónea

## Diagnóstico
1. `kubectl get pods`: el pod reinicia en bucle. Ver `logs --previous` para el error de arranque (variable faltante, puerto, archivo de configuración que no abre).
2. `deployment_status`: ¿hubo un rollout en los últimos minutos? `rollout history` muestra las revisiones.
3. Si el error apunta a un archivo montado, `kube_describe` del pod (volúmenes) y del ConfigMap: ¿falta la clave o cambió el contenido?

## Mitigación
- La configuración vive en la plantilla del pod (variables de entorno, imagen, args) y cambió con un rollout reciente: `runbook:rollout-undo`, y después `pr:manifests` para que el repo no la vuelva a aplicar.
- La configuración vive en un **ConfigMap editado en su lugar**: `rollout-undo` **no** lo revierte (el ConfigMap no forma parte de las revisiones del deployment) y reiniciar tampoco ayuda. `pr:manifests` para revertir el ConfigMap; una persona reinicia después.
- Error de código en el arranque: `pr:app`; reiniciar no ayuda.
