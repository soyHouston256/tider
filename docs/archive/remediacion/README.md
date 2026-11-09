# Archivo: motor de remediación (grafo antiguo)

No vigente. Grafo antiguo (dominio OpenTelemetry Demo, con ejecutor). Archivado el 2026-11-09 por decisión del equipo; retomar en la iteración de remediación.

Decisiones 6, 19 y 26 (`recomend/_auditoria_consolidada.md`). El producto vigente es
solo el motor agéntico de la consola (`src/tider/console/agentic.py`). Este material
queda fuera del informe y de la ingesta del Context Lake. Inventario previo:
[../INVENTARIO_ARCHIVADO.md](../INVENTARIO_ARCHIVADO.md).

## Qué hay y dónde

| Material | Ubicación actual | Ubicación original |
|---|---|---|
| Grafo, agentes, workflow, política, ejecutor, safety, webhook | `archive/legacy_engine/src/tider/{graph.py,api.py,safety.py,agents/,workflow/,decision/,executor/}` | `src/tider/...` |
| Herramientas kube/Prometheus del dominio OTel | `archive/legacy_engine/src/tider/tools/{kube.py,observability.py}` | `src/tider/tools/` |
| Arnés y fixtures de evaluación del grafo | `archive/legacy_engine/eval/{harness.py,mock_local.py,scenarios.yaml,fixtures/}` | `eval/` |
| Scripts OTel | `archive/legacy_engine/scripts/{record_fixture.py,inject_fault.py}` | `scripts/` |
| Generadores del atlas | `archive/legacy_engine/scripts/{render_diagrams.py,export_drawio.py}` | `scripts/` |
| Atlas de 13 vistas (C4, secuencia, agentes, política...), `catalog.json`, `source/`, `svg/`, galería `index.html`, propuesta `proposals/TiderOps_Activacion_por_Eventos.drawio` | `atlas/` (esta carpeta) | `docs/diagrams/` |
| `default_registry()` original (kube + observability) | `archive/legacy_engine/src/tider/tools/__init__.py` (copia de referencia) | `src/tider/tools/__init__.py` |
| RBAC del ejecutor | `archive/legacy_engine/deploy/rbac.yaml` | `deploy/` |
| Tests del grafo | `tests/_archivo/{test_e2e,test_api,test_observation,test_units}.py` | `tests/` |
| Docs | `engine.md`, `architecture.md`, `architecture.mmd`, `diagrams/TiderOps_Grafo.drawio` (esta carpeta) | `docs/` |
| Runbooks de remediación OTel | `runbooks/` (copia de referencia) | `docs/runbooks/` (se conserva) |

El código está fuera de `src/` a propósito: `setuptools` empaqueta solo `src/` y el
`Dockerfile` copia solo `src/`, así el grafo no llega al wheel ni a la imagen.
`archive/` y `tests/_archivo/` están excluidos de `ruff`; `tests/_archivo/` está
excluido de pytest (`addopts = "--ignore=tests/_archivo"`).

**Runbooks:** `docs/runbooks/` se mantiene intacto porque es la entrada congelada del
benchmark `eval/quality` (`manifest.json` hashea esas rutas y el SHA-256 del manifiesto
es el identificador de protocolo de las capturas). Moverlo invalida
`python -m eval.quality --verify`. La copia de `runbooks/` aquí es idéntica byte a byte.
No añadir archivos a `docs/runbooks/`: `verify()` rechaza documentos extra.

## Cómo retomarlo

1. Mover de vuelta con `git mv`: `archive/legacy_engine/src/tider/*` → `src/tider/`,
   `archive/legacy_engine/eval/*` → `eval/`, `scripts/*` → `scripts/`,
   `deploy/rbac.yaml` → `deploy/`, `tests/_archivo/*.py` → `tests/`. Se conservó la
   estructura relativa, así que los imports relativos vuelven a funcionar sin cambios.
2. Restaurar `"decision/*.yaml"` en `[tool.setuptools.package-data]` y quitar el
   `addopts` de pytest y el `extend-exclude` de ruff en `pyproject.toml`.
3. `tider.tools.default_registry()` y `FixtureRegistry` sin `spec` hoy lanzan
   `RuntimeError("archivado: ver docs/archive/remediacion ...")` (nada vigente las usa;
   `FixtureRegistry` está en el módulo compartido `tools/base.py` y no se partió). Para
   reactivarlas: restaurar `tools/kube.py` y `tools/observability.py`, copiar
   `archive/legacy_engine/src/tider/tools/__init__.py` sobre `src/tider/tools/__init__.py`
   y devolver en `FixtureRegistry.__init__` la línea `spec or default_registry()`.
4. El modo sin LLM de la consola ya no usa el grafo (`console/analysis.py` llama a
   `baseline.py`/`catalog_diagnosis.py`); reconectarlo sería una decisión nueva.
5. Atlas: `render_diagrams.py` y `export_drawio.py` resuelven rutas como
   `parents[1]/docs/diagrams`; tras devolverlos a `scripts/`, mover también
   `docs/archive/remediacion/atlas/` a `docs/diagrams/`. Las vistas 06, 07 y 11 describen
   el grafo antiguo; el diagrama vigente es `docs/designs/tider-blueprint.drawio`.
6. El dominio es OpenTelemetry Demo (`otel-demo`, flagd); el producto vigente usa
   Online Boutique en ChaosForge. Hay que adaptar herramientas, política y runbooks.
