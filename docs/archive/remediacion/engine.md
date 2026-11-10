# Motor operativo y evaluación

Esta guía corresponde a la entrada Alertmanager; la consola local se describe en
[README](../README.md) y usa el mismo grafo en modo observación.

## Flujo
alerta → **Intake** → **Contexto (RAG)** → **Investigador** (herramientas de solo lectura) → **Juez**
→ (si falta evidencia, vuelve al Investigador; `TIDER_MAX_ITER` rondas en total) → **Decisor** (reglas, sin LLM)
→ **Límites** (interruptor, enfriamiento, presupuesto) → **Ejecutor** (`runbook` | `pr` | `escalar`)
→ **Verificador** (espera el rollout y la resolución de la alerta) → **Reportero** (aprende solo de lo verificado).

**Regla de cierre:** todo camino que no termine en una alerta resuelta y verificada termina en una persona
(`out/escalations/` + log + Slack si `TIDER_SLACK_WEBHOOK`). Incluye: el LLM devuelve basura, el flujo falla,
el ejecutor falla, la acción se ejecutó y la alerta sigue activa, y el modo sombra (`TIDER_DRY_RUN=true`).

## Garantías de seguridad (probadas en `tests/`)
- **Lectura:** el investigador solo llama herramientas de lectura. Los argumentos del LLM se validan (nombres
  DNS-1123, tipos y namespace permitidos); el guardia de `kubectl` solo acepta verbos de lectura y flags de una lista
  cerrada (también `--flag=valor`). Las herramientas usan la credencial del lector.
- **Evidencia:** un fallo de herramienta o una consulta vacía **no** cuentan como evidencia (`kind=error|empty`).
  El juez baja la confianza si no hay telemetría, si es de un solo tipo o si los documentos citados están viejos.
- **Decisión:** el LLM propone, **no ejecuta**. El decisor aplica `decision/allowlist.yaml`: acción permitida,
  confianza mínima, namespace, el deployment debe ser el origen o estar en la cadena de propagación y no estar
  protegido. `rollout-undo` exige un rollout reciente y `scale` exige subir réplicas sin HPA, ambos verificados con
  datos estructurados de `deployment_status`, no con texto del LLM.
- **Límites con estado** (`safety.py`): misma alerta una vez por ventana (Alertmanager reenvía), enfriamiento por
  deployment, presupuesto de acciones por hora e interruptor de apagado (`TIDER_AUTONOMY=off` o `touch out/STOP`).
- **Ejecución:** comandos desde plantillas fijas; `TIDER_DRY_RUN=true` por defecto; sin `TIDER_EXECUTOR_KUBECONFIG`
  (ServiceAccount `tider-executor`) no se ejecuta nada. `scale` usa `--current-replicas` como precondición.
- **API:** todo menos `/healthz` exige `Authorization: Bearer $TIDER_API_TOKEN`; `/lake/ingest` solo lee de `docs/`.
- **Aprendizaje:** el reportero solo guarda en el lake incidentes verificados.
- Los documentos y las salidas de herramientas se marcan como datos en el prompt. Esto **no** es una garantía:
  la defensa real contra inyección es el decisor (ver escenario `injection_checkout`).

## Correr
```bash
make setup                              # versiones fijadas en uv.lock
.venv/bin/python -m pytest               # sin clúster ni red; no escribe en out/
export ANTHROPIC_API_KEY=...
.venv/bin/python eval/harness.py --repeats 3       # LLM directo vs sin juez vs sin RAG vs completo (siempre en dry-run)
export TIDER_API_TOKEN=...               # obligatorio
.venv/bin/uvicorn tider.api:app --port 8080        # webhook: POST /webhook/alertmanager
```
Python 3.15 todavía no instala (`uuid-utils`, dependencia de LangGraph, no tiene wheels): usar 3.11–3.14.
Context lake con Postgres: `docker compose --profile lake up -d pg` y `TIDER_STORE=pg` (el `PgVectorStore` está escrito pero **aún no probado**).
Variables de entorno: ver `.env.example`. RBAC y credencial del ejecutor: ver `../deploy/rbac.yaml`.

## Eval
5 escenarios en `eval/scenarios.yaml`: fuga de memoria (reiniciar), ConfigMap roto (PR: `rollout-undo` no revierte
un ConfigMap), despliegue malo (`rollout-undo`), falla por feature flag (escalar) e inyección en logs (escalar).
Los fixtures responden según los argumentos y exponen las mismas herramientas que producción.
El arnés reporta por separado **diagnóstico** (componente, causa, acción propuesta), **decisión** (acción final e
**INSEGURAS** = acción automática distinta de la correcta, la métrica clave) y **calibración** (acierto por tramo de
confianza del juez, para fijar los umbrales de `allowlist.yaml` con datos).

Para comprobar la integración sin servicios externos: `.venv/bin/python eval/mock_local.py --out out/mock_local`.
Ejecuta 30 casos sobre los cinco escenarios anteriores y un sexto de telemetría insuficiente, con respuestas
programadas y ejecución en dry-run. Cada escenario se prueba en condición nominal, rechazo del juez, confianza
baja, telemetría vacía y namespace no permitido. Guarda decisiones observadas, controles cumplidos o fallidos,
consultas a fixtures y huellas de los archivos. Esta prueba mide el funcionamiento del flujo y los controles;
no mide el acierto de un modelo real, el MTTR ni el costo de atención.

## Estado del motor operativo
| Pieza | Estado |
|---|---|
| Grafo, agentes, decisor, límites, ejecutor, guardias, API | Hecho y probado con LLM simulado |
| Lake en memoria + ingesta Markdown/Mermaid | Hecho y probado |
| Embeddings | `HashEmbedder` (placeholder); cambiar por un modelo real |
| `PgVectorStore` | Escrito, sin probar (Docker no disponible al escribirlo) |
| Herramientas Prometheus/Jaeger/OpenSearch/kubectl, verificador | Escritas, **sin probar contra un clúster real** |
| Prompts con LLM real | Sin evaluar; el arnés es el siguiente paso |
| Umbrales de confianza | Arbitrarios hasta medir la calibración con el arnés |
| Límites con estado | En memoria: valen para **una** réplica de Tider |
| PR real a GitHub | Pendiente (hoy escribe a `out/prs`) |
| Manifiesto de despliegue de Tider (Deployment, imagen) | Pendiente; el RBAC y el kubeconfig del ejecutor están en `deploy/` |
| Eval | 5 escenarios hechos a mano; hay que grabarlos del demo con `scripts/record_fixture.py` |

## Pendientes de diseño
- `rollout-restart` es la acción con la puerta más baja (sin precondición de datos). Si el arnés muestra
  acciones inseguras con reinicios, agregarle una precondición en `decision/policy.py`.
- Las acciones imperativas (`rollout undo`, `scale`) generan drift frente a Helm/GitOps: el repo de manifiestos
  las revierte en el siguiente sync. A mediano plazo, preferir `pr:manifests` y dejar los runbooks como freno de emergencia.
- No hay correlación entre alertas: N alertas de un mismo incidente son N investigaciones (acotadas por el
  enfriamiento y el presupuesto, pero sin agrupar).

## Continuación del agente
1. Contrastar el conector Cloud Logging de la consola con el laboratorio ChaosForge existente.
2. Añadir Cloud Monitoring y Cloud Trace, y registrar evidencia de fallos controlados en Online Boutique.
3. Comparar el baseline y un modelo real, con la causa inyectada separada de la entrada del investigador.
4. Validar persistencia y conectores antes de desplegar el agente. La consola conserva la ejecución en observación.
