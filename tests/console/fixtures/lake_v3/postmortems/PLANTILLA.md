---
id: PM-<NN>
servicio: <servicio>
tipo_doc: postmortem
mecanismo: <scale_zero | wrong_port | latency | cpu_limit>
plataforma: kubernetes
app: online-boutique
fecha: <AAAA-MM-DD de la corrida>
corrida_chaosforge_id: <uuid del experimento en ChaosForge>
revision_lake: <revisión del Context Lake congelada al escribir este postmortem>
revision: 1
fuente: <archivos exportados: logs del namespace, eventos K8s, proyección /api/observations>
conjunto: historial
---
# PM-<NN> · <servicio> · <mecanismo>

> **REGLA (decisión 13).**
> - Las señales se pegan **tal cual** aparecieron: líneas de log y eventos con su timestamp, sin editar, resumir ni traducir. Se permite omitir líneas repetidas dejando una nota de omisión con el conteo y el rango de tiempo; nunca se edita una línea.
> - Lo que se pega aquí no se interpreta. La interpretación (resumen, línea de tiempo razonada, causa raíz, lecciones) va **separada y al final**.
> - Si una fuente no tenía datos en la ventana, se escribe `SIN_DATOS` y se indica la fuente. No se rellena.
>
> Este documento es un **antecedente, no evidencia**: no confirma por sí mismo un diagnóstico futuro (decisión 12).
>
> **Sin culpables (blameless):** se describen sistemas, señales y decisiones, nunca personas.
>
> **Fragmentación:** se divide por sección (`## …`) y cada fragmento enlaza a este id.

## Metadatos
| Campo | Valor |
|---|---|
| id | PM-<NN> |
| servicio | <servicio> |
| mecanismo | <mecanismo> (parámetros: <p. ej. replicas=0, duración=120 s>) |
| fecha | <AAAA-MM-DD> |
| corrida ChaosForge id | <uuid> |
| revisión Lake | <revisión congelada> |
| ventana exportada | <T0 UTC> – <T1 UTC> (desde 5 min antes de la inyección hasta 5 min después de la recuperación) |
| periodo de falla (para conteos) | <inicio> – <restaurado> (registro de ChaosForge) |
| tráfico | loadgenerator `USERS=<n>`, `RATE=<n>`, réplicas=<n> (si no se registró: "no registrado") |
| exportado por / fecha | <script o proceso> / <AAAA-MM-DD> |

## Señales observadas (crudas, copiadas tal cual: líneas de log y eventos con timestamp)
### Eventos de Kubernetes (namespace boutique)
```text
<timestamp UTC>  <tipo>  <reason>  <involvedObject.kind>/<involvedObject.name>  <message>
```
### Logs del servicio objetivo
```text
<timestamp UTC>  <severity>  <pod>  <mensaje tal cual>
```
(Si no hay ninguna línea: `SIN_DATOS (0 entradas en la ventana)`.)
### Logs de llamadores y otros servicios del namespace (severity ≥ WARNING)
```text
<timestamp UTC>  <severity>  <servicio>/<pod>  <mensaje tal cual>
  (N líneas más con el mismo patrón entre T1 y T2 omitidas; ver datos/PM-<NN>/<archivo>)
```
### Observaciones del observador ChaosForge (/api/observations, si aplica)
```text
<at>  http=[<path>:<status>:<elapsed_ms>]  dependency=<success>/<elapsed_ms>  coverage=<complete|incomplete>
```
### Estado de objetos al inicio y al final de la ventana
```text
<salida de kubectl get deploy/pods/endpointslices, con hora de captura>
```

---
*A partir de aquí empieza la interpretación. Todo lo que sigue se escribe después de pegar las señales.*

## Resumen
<1–2 frases: qué falló, cuánto duró, qué vieron los usuarios y cómo se restauró.>

## Línea de tiempo (UTC)
Formato "guion": una fila por hecho, en orden, cada una respaldada por una señal pegada arriba.

| t (UTC) | Qué ocurrió | Señal que lo respalda (fuente y línea de arriba) |
|---|---|---|
| | Inyección solicitada (registro de ChaosForge) | |
| | Disparador visible en el clúster (evento) | |
| | Primer síntoma en el servicio objetivo | |
| | Primer síntoma en un llamador | |
| | Restauración (evento de escalado de vuelta) | |
| | Último síntoma atribuible en un llamador | |
| | Recuperación estable verificada | |

## Detección
- **Cómo y cuándo se hace visible:** <primera señal (log de llamador, evento, sonda) y su t; demora respecto del disparador>.
- **Qué señal lo discrimina:** <p. ej. `connection refused` hacia el puerto del objetivo + `ScalingReplicaSet … to 0`>.
- **Qué NO lo habría detectado:** <p. ej. sondas `/` y `/cart` en 200; barrido solo `severity>=ERROR`; logs del propio objetivo (sin instancias no hay logs)>.

## Impacto
Cifras exactas, calculadas sobre los archivos de `datos/`. Siempre se informa también el ruido de base (antes de la inyección).

| Servicio | líneas ≥ WARNING antes (5 min) | durante la falla | después | patrón dominante |
|---|---|---|---|---|
| <servicio> | | | | |

- Operaciones de usuario afectadas: <navegar / ver producto / carrito / checkout / ninguna visible>, con conteo de respuestas 5xx vs. 2xx/3xx de frontend en el periodo de falla.
- Servicios con síntomas (víctimas): <lista, según `topologia.yaml`>
- Duración del impacto observable: <primer síntoma → último síntoma atribuible>
- Lo que **no** se pudo observar: <p. ej. sin tráfico de checkout → SIN_DATOS; truncamiento del export>

## Causa raíz y disparador
- **Disparador (trigger):** <el evento que inició el incidente; p. ej. escalado del Deployment a 0 réplicas>.
- **Causa raíz:** <la condición que produjo el impacto; p. ej. servicio sin instancias listas ni endpoints>.

| componente | t_inicio (UTC) | razón (vocabulario cerrado) | runbook |
|---|---|---|---|
| <servicio> | <primer punto anómalo> | <servicio-sin-instancias \| configuracion-incorrecta \| dependencia-lenta \| saturacion-cpu> | RB-0<n> |

Condición (texto corto): <…>

## Remediación
- Acción aplicada (qué sistema o proceso, cuándo): <p. ej. "Restaurar" automático de ChaosForge al vencer la duración>
- Verificación: <qué señal se despejó y durante cuánto tiempo se mantuvo estable>

## Lecciones aprendidas
### Qué salió bien
- <…>
### Qué salió mal
- <…>
### Dónde tuvimos suerte
- <…>
### Qué confundió
- <señales engañosas, falta de logs, avisos con severidad baja, ruido de base, etc.>
### Brechas del Lake
- <ficha o runbook que habría que corregir; registrar como hallazgo, no editar retroactivamente la revisión congelada>

## Acciones
En el laboratorio son **propuestas**: `Responsable = por asignar`. Solo asesoría; ninguna acción incluye comandos que modifiquen el clúster.

| Acción | Tipo (mitigar / prevenir / proceso / otro) | Responsable | Seguimiento |
|---|---|---|---|
| <…> | <…> | por asignar | <hallazgo / issue / revisión del Lake> |

## Información de apoyo
- Eventos: [`datos/PM-<NN>/eventos-k8s.json`](datos/PM-<NN>/eventos-k8s.json)
- Logs ≥ WARNING (completos): [`datos/PM-<NN>/logs-warning-o-mas.json`](datos/PM-<NN>/logs-warning-o-mas.json)
- Logs de todas las severidades (truncado): [`datos/PM-<NN>/logs-boutique.json`](datos/PM-<NN>/logs-boutique.json)
- Estado final: [`datos/PM-<NN>/estado-final.txt`](datos/PM-<NN>/estado-final.txt)
- Observaciones: [`datos/PM-<NN>/observaciones.json`](datos/PM-<NN>/observaciones.json)
- Metadatos de la corrida: [`datos/PM-<NN>/corrida.yaml`](datos/PM-<NN>/corrida.yaml)

---
*Referencias del formato:* Google SRE Book, Apéndice D "Example Postmortem" (https://sre.google/sre-book/example-postmortem/); Google SRE Book, cap. 15 "Postmortem Culture: Learning from Failure" (https://sre.google/sre-book/postmortem-culture/); PagerDuty Postmortem Template (https://response.pagerduty.com/after/post_mortem_template/).
