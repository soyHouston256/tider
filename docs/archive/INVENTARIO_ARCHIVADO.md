# Inventario previo al archivado del grafo antiguo

Fecha: 2026-11-09. Rama: `archivo-grafo-antiguo`. Decisiones 6, 19 y 26 de
`recomend/_auditoria_consolidada.md`. Inventario hecho con `grep` sobre `src/`,
`tests/`, `eval/`, `scripts/`, `Makefile`, `pyproject.toml`, `Dockerfile`,
`docker-compose.yml`, `.env.example`, `README.md` y `docs/` antes de mover nada.

Línea base: `uv run pytest -q` → **174 passed**. `ruff check src tests` → 20 errores
(todos en `console/catalog_diagnosis.py` y `tests/console/`); `ruff format --check`
→ 29 archivos sin formatear. `python -m eval.quality --verify` → exit 0;
`eval/quality/followup/autoresearch.sh` → exit 0.

## 1. Módulos del grafo antiguo y quién los importa

| Módulo | Importado desde (fuera del propio grafo) | Clasificación |
|---|---|---|
| `src/tider/graph.py` | `console/analysis.py:8` (`build_graph`), `api.py:17`, `eval/harness.py:28`, `eval/mock_local.py:105`, `tests/test_e2e.py:8`, `tests/test_api.py:12`, `tests/test_observation.py:8` | Exclusivo del grafo, salvo la consola (modo sin LLM) |
| `src/tider/agents/` (`deps`, `intake`, `context`, `investigator`, `judge`, `reporter`, `prompts`) | `console/analysis.py:6` (`Deps`), `api.py:14`, `eval/harness.py:26`, `eval/mock_local.py:103`, `tests/test_e2e.py:6`, `tests/test_api.py:10`, `tests/test_observation.py:5` | Exclusivo del grafo, salvo la consola (modo sin LLM) |
| `src/tider/workflow/nodes.py` | `graph.py:20`, `tests/test_e2e.py:13` | Exclusivo |
| `src/tider/decision/` (`policy.py`, `allowlist.yaml`) | `console/analysis.py:7` (`load_policy`), `graph.py`, `workflow/nodes.py`, `tools/kube.py:16`, `api.py:16`, `eval/harness.py:27`, `eval/mock_local.py:104`, `tests/test_units.py:7`, `tests/test_e2e.py:7`, `tests/test_api.py:11`, `tests/test_observation.py:6`; `pyproject.toml` package-data `decision/*.yaml` | Exclusivo, salvo la consola (modo sin LLM) |
| `src/tider/executor/` (`escalate`, `pr`, `runbook`, `verify`) | `graph.py:18`, `workflow/nodes.py:7-8`, `tests/test_units.py:8-9`, `tests/test_observation.py:7` | Exclusivo |
| `src/tider/safety.py` | `agents/deps.py:6`, `tests/test_units.py:12` | Exclusivo |
| `src/tider/api.py` (webhook Alertmanager + `/lake/ingest`) | `tests/test_api.py:9`; mencionado en `docs/engine.md:42`, `docs/architecture.md:87`, `scripts/render_diagrams.py:54` (texto) | Exclusivo. No hay entry point en `pyproject.toml` ni en `Makefile`/`Dockerfile` |
| `src/tider/tools/kube.py`, `tools/observability.py` | `tools/__init__.py:7` (`default_registry`, import diferido), `executor/verify.py:12`, `tests/test_units.py:14,16`, `scripts/record_fixture.py:15`; `kube.py` importa `decision.policy` | Exclusivo (herramientas del dominio OTel; la consola usa `console/investigation_tools.py`) |
| `deploy/rbac.yaml` | `docs/engine.md:46,75`, `README.md:78` | Exclusivo (RBAC del ejecutor, namespace `otel-demo`) |

## 2. Módulos compartidos que se quedan

| Módulo | Uso por la consola / evaluación vigente |
|---|---|
| `tider/state.py` | `console/agentic.py:11`, `console/models.py:8` (`Decision`, `Evidence`, `Hypothesis`, `Verdict`) |
| `tider/llm.py` | `console/agentic.py:10`, `console/analysis.py:11`, `console/providers/*`, `eval/course_e5.py:22`, `eval/quality/live.py:67`, tests de consola (`ScriptedLLM`) |
| `tider/config.py` | `llm.py:9` (`env`) |
| `tider/tools/base.py` | `console/investigation_tools.py:12`, `console/analysis.py:12`, `tests/console/test_console.py:189` (`Tool`, `ToolRegistry`) |
| `tider/lake/ingest.py` | `console/context_lake.py:18` (`split_markdown`), `console/catalog_review.py:9` (`parse_mermaid`), `console/analysis.py:9` (`ingest_dir`) |
| `tider/lake/store.py`, `embed.py`, `models.py`, `schema.sql` | `console/analysis.py:10` (`InMemoryStore`, solo para el grafo); `lake/ingest.py` usa `models`; `docker-compose.yml` monta `schema.sql` |

`tools/__init__.py:default_registry()` y `tools/base.py:FixtureRegistry` se quedan
(módulo compartido), pero su ruta por defecto importa `tools.kube`/`observability`,
que se archivan. Ver riesgos en el README del archivo.

## 3. Dependencias de la consola con el grafo

- `console/api.py:14` importa `LabEngine` al cargar la app; `console/analysis.py:6-12`
  importa `tider.graph`, `tider.agents.deps`, `tider.decision.policy` y
  `tider.lake.store`. Con cualquier `LLM_PROVIDER`, archivar el grafo rompía el arranque.
- `LabEngine.analyze` (ruta usada por `AnalysisService` cuando `LLM_PROVIDER=none`)
  envolvía `console/baseline.py`/`catalog_diagnosis.py` en un `ScriptedLLM` y lo
  ejecutaba con `build_graph(..., observation_only=True)`.
- Con `LLM_PROVIDER=anthropic` la consola usa `LabEngine.analyze_live` →
  `console/agentic.py` (no depende del grafo antiguo; usa su propio `StateGraph`).

## 4. Tests

| Archivo | Depende del grafo | Tests |
|---|---|---|
| `tests/test_e2e.py` | Sí (`graph`, `agents`, `decision`, `workflow`, `eval/fixtures`, `docs/`) | 15 |
| `tests/test_api.py` | Sí (`tider.api`, `docs/runbooks`) | 3 |
| `tests/test_observation.py` | Sí (`graph`, `executor`) | 3 |
| `tests/test_units.py` | Sí, salvo 3 tests de módulos compartidos (`parse_mermaid`, `split_markdown`, `ToolRegistry`) | 18 |
| `tests/console/test_console.py` | Indirecto: verifica las 8 etapas del grafo en el modo sin LLM | 17 |
| `tests/console/test_service.py` | Indirecto: etapa `verificador` y dos rondas del juez | 3 |
| `tests/console/test_general_scope.py` | Indirecto (`LabEngine.analyze`) | 4 |
| `tests/conftest.py` | Variables del ejecutor (`TIDER_DRY_RUN`, `TIDER_EXECUTOR_KUBECONFIG`...) | fixture |

## 5. Evaluación y scripts

| Archivo | Depende de |
|---|---|
| `eval/harness.py` | `graph`, `agents.deps`, `decision.policy`, `FixtureRegistry`, `eval/scenarios.yaml`, `eval/fixtures/` |
| `eval/mock_local.py` | `graph`, `agents.deps`, `decision.policy`, `eval/scenarios.yaml`, `eval/fixtures/` |
| `eval/scenarios.yaml`, `eval/fixtures/*.json` | Solo `harness.py`, `mock_local.py`, `tests/test_e2e.py`, `tests/test_units.py` |
| `scripts/record_fixture.py` | `tools.default_registry` (kube/observability) |
| `scripts/inject_fault.py` | flagd del OpenTelemetry Demo (`otel-demo`) |
| `eval/quality/data.py:34-35` | **`docs/runbooks/*.md`**; `eval/quality/manifest.json:7-10` hashea esas rutas y el SHA-256 del manifiesto es el ID de protocolo de `recordings/retrieval-v1.json` |
| `eval/quality/live.py`, `retrieve.py`, `followup/compare.py` | `runbooks()` (mismo directorio) |
| `eval/course_e5.py`, `eval/e5/` | Solo consola (`agentic`, `baseline`) |
| `scripts/render_diagrams.py`, `scripts/export_drawio.py` | `docs/diagrams/` |

## 6. Empaquetado y despliegue

- `pyproject.toml`: único entry point `tider-console = tider.console.__main__:main`
  (no hay entry point del webhook). Package-data incluye `decision/*.yaml`.
  `[tool.setuptools.packages.find] where = ["src"]`: todo lo que esté bajo `src/` se empaqueta.
- `Makefile`: `run` → `python -m tider.console`; `lint` → `ruff` sobre `src tests`.
  Sin referencias al webhook.
- `Dockerfile`: `COPY src/ src/` y `CMD python -m tider.console`. Sin referencias al
  webhook; `.dockerignore` solo deja pasar `pyproject.toml`, `uv.lock` y `src/`.
- `docker-compose.yml`: servicio `console`; `pg` monta `src/tider/lake/schema.sql`.
- `.env.example`: bloque "Motor operativo opcional" con variables que solo lee el
  grafo antiguo (`TIDER_API_TOKEN`, `TIDER_JUDGE_MODEL`, `TIDER_EXECUTOR_KUBECONFIG`, ...).

## 7. Documentación del motor antiguo

| Documento | Contenido | Referenciado por |
|---|---|---|
| `docs/engine.md` | Webhook Alertmanager, política, ejecutores | `README.md:93`, `docs/testing.md:64`, `docs/architecture.md:88` |
| `docs/architecture.md` | Recorrido consola → `LabEngine` → `graph.py` | `README.md:90` |
| `docs/architecture.mmd` | Topología OpenTelemetry Demo | nadie (lo ingerían los tests del grafo vía `ingest_dir(docs/)`) |
| `docs/runbooks/` (4) | Runbooks de remediación OTel | `eval/quality` (corpus congelado), tests del grafo |
| `docs/diagrams/TiderOps_Grafo.drawio` | Grafo de agentes antiguo | nadie |
| `docs/diagrams/` (atlas de 13 vistas, `catalog.json`, `source/`, `svg/`) | Consola + grafo compartido (vistas 06, 07 y 11 describen el grafo) | `README.md:89`, `docs/roadmap.md:27`, `scripts/render_diagrams.py` |
| `docs/roadmap.md`, `docs/decisions.md`, `docs/testing.md` | Mencionan el grafo como motor de la consola | `README.md` |
