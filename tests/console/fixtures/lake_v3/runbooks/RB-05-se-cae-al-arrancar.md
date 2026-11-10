---
id: RB-05
modo_falla: se-cae-al-arrancar
mecanismo: ninguno (sin inyector en ChaosForge)
estado_validacion: declarada, no validada
tipo_doc: runbook
servicio: "*"
plataforma: kubernetes
app: online-boutique
revision: 1
fecha: 2026-11-09
fuente: recomend/_bibliografia_firmas.md §9.3.B; recomend/modelo_comun.md (terminaciones_en_ventana); recomend/_auditoria_consolidada.md (decisión 21)
---
# RB-05 · Se cae al arrancar (crash loop)

> **Declarada, no validada.** ChaosForge no tiene inyector para este modo; firma y reparación no se han verificado en el laboratorio (decisión 21). Tider puede reportarla como hipótesis, y la reparación es una **sugerencia no verificada**.

El proceso del contenedor termina con error poco después de arrancar; Kubernetes lo reinicia una y otra vez con espera creciente (`CrashLoopBackOff`).

**Respaldo en la literatura:** OpenRCA "process termination" (Tabla 5); ITBench CorruptDeployment y JVMCodeReturnFault. Los predicados son [INF].

## Firma
**CONFIRMA**, si se cumple todo lo obligatorio y al menos un corroborante:
- **Obligatorio [INF]:** `terminaciones_en_ventana ≥ 3` para el servicio (el modelo común no usa reinicios por instancia). En Kubernetes: `restartCount` crece 3 o más veces, o `waiting.reason == CrashLoopBackOff`.
- **Obligatorio [INF]:** Instancia `codigo_salida ≠ 0` **y** `motivo_fin ≠ OOMKilled` (si es OOMKilled, ir a RB-06).
- **Corroborante:** logs del contenedor **anterior** (`--previous`) con excepción o error fatal antes de salir.
- **Corroborante:** eventos `BackOff` ("Back-off restarting failed container").

**DESCARTA [INF]:** `restartCount` estable y contenedor Ready toda la ventana, o todas las terminaciones son OOMKilled (RB-06).

**SIN_DATOS:** no hay eventos ni estado del pod, o los logs previos ya rotaron.

## Cómo distinguir causa de víctima
- **La causa** es el servicio que se reinicia; sus llamadores ven errores **intermitentes** (endpoint que aparece y desaparece).
- Si un Cambio de configuración o imagen precede al primer crash y el log de salida lo explica (variable faltante, destino inalcanzable), la razón es **configuración incorrecta** (RB-02), no crash loop (decisión 21).
- Si el log de salida nombra una dependencia con anomalía propia anterior, la raíz es la dependencia (RB-01 o RB-03 sobre D).

## Pasos de verificación (SOLO LECTURA)
```sh
NS=boutique; SVC=<servicio>
kubectl -n $NS get pods -l app=$SVC -o wide
kubectl -n $NS get pods -l app=$SVC -o jsonpath='{range .items[*]}{.metadata.name}{" restarts="}{.status.containerStatuses[0].restartCount}{" waiting="}{.status.containerStatuses[0].state.waiting.reason}{" last="}{.status.containerStatuses[0].lastState.terminated.reason}{"/"}{.status.containerStatuses[0].lastState.terminated.exitCode}{"\n"}{end}'
kubectl -n $NS describe pod <pod> | sed -n '/Last State/,/Ready/p;/Events:/,$p'
kubectl -n $NS logs <pod> -c server --previous --tail=100
kubectl -n $NS rollout history deploy/$SVC
```
Cloud Logging: `logName="projects/tider-ops/logs/events" AND jsonPayload.involvedObject.namespace="boutique" AND jsonPayload.reason="BackOff"`.

## Acción de reparación sugerida
**ACCIÓN HUMANA: Tider no ejecuta esto.** Sugerencia no verificada.

Este runbook no propone comandos de cambio hasta que el modo de falla se valide con un inyector (decisión 21).

**Pasos de diagnóstico para que la persona decida** (solo lectura): sirven para elegir entre volver a la revisión anterior o corregir la causa que indique el log `--previous`. No reiniciar a ciegas: un crash loop no se corrige reiniciando.
```sh
NS=boutique; SVC=<servicio>
# ¿Hubo una revisión nueva justo antes del primer crash? Comparar la actual con la anterior
kubectl -n $NS rollout history deploy/$SVC
kubectl -n $NS rollout history deploy/$SVC --revision=<rev_actual>
kubectl -n $NS rollout history deploy/$SVC --revision=<rev_anterior>
kubectl -n $NS get rs -l app=$SVC -o wide
# ¿El log de salida nombra una variable, Secret, ConfigMap o destino? ¿Existe?
kubectl -n $NS logs <pod> -c server --previous --tail=100
kubectl -n $NS get configmap,secret
```
Si el primer crash coincide con una revisión nueva y la anterior arrancaba, la opción a evaluar es revertir la revisión; si el log apunta a un recurso externo (Secret o ConfigMap faltante), revertir no lo corrige.

## Cómo verificar que funcionó
- `restartCount` deja de crecer y el contenedor queda Ready.
- Sin eventos `BackOff` nuevos y sin errores en los llamadores, estable tras una espera de 3–5 minutos (duración [INF], a calibrar); la práctica de esperar y re-verificar sigue a ITBench C.5.2 [LIT]. La espera es más larga porque el backoff puede ocultar una recaída.

## Riesgos de la reparación
- `rollout undo` revierte todos los campos de la revisión.
- Si la causa es externa (p. ej. un Secret borrado), el rollback no la corrige.
- Los logs `--previous` se pierden si el pod se recrea: exportarlos **antes** de actuar.

## Equivalente en ECS (breve)
- Firma: tareas STOPPED repetidas (`terminaciones_en_ventana ≥ 3`) con "Essential container in task exited" y `exitCode ≠ 0` y ≠ 137. ECS reemplaza tasks en lugar de reiniciarlas.
- Reparación humana: `update-service` con la task definition anterior.
- ECS retiene tareas detenidas solo un tiempo limitado; si ya no están, SIN_DATOS [INF].
