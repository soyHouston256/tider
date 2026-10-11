# Tider v4 — agente RCA con context lake, juez y decisor determinista

Esqueleto implementable (Python + LangGraph). v1 = Compose, v2 = k3d, v3 = GKE, **v4 = este código** (agentes + RAG).

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
uv venv --python 3.12 && uv pip install -e '.[dev,llm]'   # o pip; versiones fijadas en requirements.lock
pytest                                   # sin clúster ni red; no escribe en out/
export ANTHROPIC_API_KEY=...
python eval/harness.py --repeats 3       # LLM directo vs sin juez vs sin RAG vs completo (siempre en dry-run)
export TIDER_API_TOKEN=...               # obligatorio
uvicorn tider.api:app --port 8080        # webhook: POST /webhook/alertmanager
```
Python 3.15 todavía no instala (`uuid-utils`, dependencia de LangGraph, no tiene wheels): usar 3.11–3.14.
Context lake con Postgres: `docker compose up -d` y `TIDER_STORE=pg` (el `PgVectorStore` está escrito pero **aún no probado**).
Variables de entorno: ver `.env.example`. RBAC y credencial del ejecutor: ver `deploy/rbac.yaml`.

## Eval
5 escenarios en `eval/scenarios.yaml`: fuga de memoria (reiniciar), ConfigMap roto (PR: `rollout-undo` no revierte
un ConfigMap), despliegue malo (`rollout-undo`), falla por feature flag (escalar) e inyección en logs (escalar).
Los fixtures responden según los argumentos y exponen las mismas herramientas que producción.
El arnés reporta por separado **diagnóstico** (componente, causa, acción propuesta), **decisión** (acción final e
**INSEGURAS** = acción automática distinta de la correcta, la métrica clave) y **calibración** (acierto por tramo de
confianza del juez, para fijar los umbrales de `allowlist.yaml` con datos).

## Estado (honesto)
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

## Siguiente
1. k3d + Helm del OTel Demo; aplicar `deploy/rbac.yaml`; inyectar fallas (`scripts/inject_fault.py` o un despliegue
   malo: `kubectl set env deployment/ad AD_PORT=80a`) y grabar fixtures reales con `scripts/record_fixture.py`.
2. Probar las herramientas y el verificador contra el clúster y corregir lo que falle; conectar `PgVectorStore`.
3. Correr el arnés con LLM real (con `--temperature` > 0 para ver varianza), ajustar prompts y fijar umbrales con la calibración.
4. Recién con INSEGURAS = 0 en todos los escenarios, probar `TIDER_DRY_RUN=false` en k3d.
