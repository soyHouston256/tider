# Tider v4 — agente RCA con context lake, juez y decisor determinista

Esqueleto implementable (Python + LangGraph). v1 = Compose, v2 = k3d, v3 = GKE, **v4 = este código** (agentes + RAG).

## Flujo
alerta → **Intake** → **Contexto (RAG)** → **Investigador** (herramientas de solo lectura) → **Juez**
→ (si falta evidencia, vuelve al Investigador, tope `TIDER_MAX_ITER`) → **Decisor** (reglas, sin LLM)
→ **Ejecutor** (`runbook` | `pr` | `escalar`) → **Verificador** → **Reportero** (guarda el incidente en el lake).

## Garantías de seguridad (probadas en `tests/`)
- El investigador solo llama herramientas de lectura; `kubectl` pasa por un guardia que rechaza escrituras.
- El LLM propone, **no ejecuta**: el decisor aplica `decision/allowlist.yaml` (acciones, confianza mínima, tope de réplicas, namespace).
- El ejecutor arma comandos desde plantillas fijas; `TIDER_DRY_RUN=true` por defecto.
- El juez baja la confianza si no hay evidencia de telemetría, si es de un solo tipo o si los documentos citados están desactualizados.
- Los documentos del lake se tratan como datos, no como instrucciones.

## Correr
```bash
pip install -e '.[dev,llm]'
pytest                                   # 14 pruebas, sin clúster ni red
export ANTHROPIC_API_KEY=...
python eval/harness.py --repeats 3       # LLM directo vs sin juez vs sin RAG vs completo
uvicorn tider.api:app --port 8080        # webhook: POST /webhook/alertmanager
```
Context lake con Postgres: `docker compose up -d` y `TIDER_STORE=pg` (el `PgVectorStore` está escrito pero **aún no probado**).

## Estado (honesto)
| Pieza | Estado |
|---|---|
| Grafo, agentes, decisor, ejecutor, guardias | Hecho y probado con LLM simulado |
| Lake en memoria + ingesta Markdown/Mermaid | Hecho y probado |
| Embeddings | `HashEmbedder` (placeholder); cambiar por un modelo real |
| `PgVectorStore` | Escrito, sin probar |
| Herramientas Prometheus/Jaeger/OpenSearch/kubectl | Escritas, **sin probar contra un clúster real** |
| Prompts con LLM real | Sin evaluar; el arnés es el siguiente paso |
| PR real a GitHub, Slack | Pendientes (hoy escriben a `out/`) |
| Eval | 2 escenarios con telemetría inventada a mano; hay que grabar escenarios reales del demo |

## Siguiente
1. k3d + Helm del OTel Demo; aplicar `deploy/rbac.yaml`; `scripts/inject_fault.py` y grabar fixtures reales.
2. Probar las herramientas contra el clúster y corregir lo que falle.
3. Correr el arnés con LLM real y ajustar prompts.
