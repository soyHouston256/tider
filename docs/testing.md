# Pruebas del agente

Ejecutar desde la raíz del repositorio, después de `make setup`:

```bash
make test
make lint
```

La suite usa herramientas, clientes y respuestas simulados. No requiere GCP, AWS,
Kubernetes, claves de modelos ni un navegador abierto. Las salidas operativas de
prueba se escriben en directorios temporales de pytest.

## Cobertura

| Grupo | Qué comprueba |
|---|---|
| `tests/test_shared_modules.py` | Ingesta Markdown/Mermaid y registro de herramientas compartidos |
| `tests/console/test_console.py` | Cuatro escenarios, HTTP, archivos estáticos, filtro GCP, errores y enmascarado |
| `tests/console/test_rca.py` | Diagnóstico, servicio sin señales y ventana temporal |
| `tests/console/test_service.py` | Historial aislado, concurrencia y referencias de decisiones |
| `tests/console/test_sweep.py`, `test_signatures.py`, `test_estado.py`, `test_pipeline_v2.py` | Pipeline v2: barrido, firmas, estado, roles y juez, con Kubernetes y Cloud Logging simulados |
| `tests/console/test_recorder.py` | Registrador de estado y RBAC de solo lectura (`deploy/reader-rbac.yaml`) |
| `tests/console/test_observer_metrics.py` | Métricas del observador en el barrido: lectura por tramos, cubetas alineadas a `t0` y firmas de latencia y CPU |
| `tests/console/test_pilot_runner.py`, `test_pilot_score.py` | Orquestador y puntuación del piloto (`eval/pilot`) |
| `tests/console/test_quality_benchmark.py`, `test_e5_replay.py` | Puntuación del benchmark de `eval/quality` y reproducción de E5 |

## Comprobación manual en la consola

1. Ejecutar `make run` y abrir http://localhost:8080.
2. Elegir **Redis no disponible**: identifica `redis-cart`, cuatro señales y una
   propuesta de revisión humana. Abrir **Decisiones y sustento**; los IDs enlazan a
   la tabla de evidencia. La verificación aparece omitida porque no hubo una acción.
3. Elegir **Cart Service sin endpoints**: identifica `cartservice`, con tres señales.
4. Elegir **Operación normal** y **Sin telemetría**: no identifica una causa raíz;
   el recorrido registra la segunda ronda y la solicitud de más evidencia.
5. Elegir una ejecución anterior en el historial y comprobar que recupera su
   resultado. **Descargar JSON** conserva auditoría y decisiones del mismo análisis.

El identificador del escenario selecciona datos de entrada; el diagnóstico se
obtiene del contenido de las señales. Una prueba sustituye la evidencia de un caso
para comprobar que el motor no usa su etiqueta como respuesta.

## API

Con el servidor abierto:

```bash
curl -fsS http://localhost:8080/health
curl -fsS http://localhost:8080/v1/lab/config
curl -fsS -H 'Content-Type: application/json' \
  --data-binary @docs/examples/analyze.json http://localhost:8080/v1/incidents/analyze
```

El ejemplo tiene fechas fijas adecuadas para la simulación. Para GCP deben usarse
fechas del experimento y habilitar la fuente en el servidor.

## Evaluación

- `eval/quality`: recuperación y diagnóstico sobre entradas congeladas; se vuelve a puntuar sin
  proveedor con `.venv/bin/python -m eval.quality --verify`. Ver [su guía](../eval/quality/README.md).
- `eval/e5`: evaluación sintética E5; `uv run python eval/course_e5.py --replay` reproduce los
  registros. Ver [su guía](../eval/e5/README.md).
- `eval/pilot`: validación de firmas y campaña del piloto contra el laboratorio; el protocolo
  prerregistrado está en `eval/pilot/protocol.yaml`.

## Distribución

`uv build --wheel` empaqueta código y recursos de la consola. La imagen Docker
usa la misma configuración y lock. `docker compose --profile console config --quiet`
valida la configuración; para verificar la imagen y su arranque se necesita ejecutar
el build y comprobar `/health` en el contenedor.

## Context Lake · primera etapa

`tests/console/test_context_lake.py` comprueba Chroma efímero con embeddings
locales deterministas: aislamiento, recuperación con procedencia, duplicados,
retirada, formatos, límites y rechazo de entidades XML. Incluye diagramas draw.io
comprimidos y sin comprimir. No descarga modelos durante la suite.

Validación local de esta implementación: 73 pruebas aprobadas; lint y formato de
`src` y `tests` correctos. Prueba separada con el modelo de embeddings real:
una consulta de carrito recuperó antes su documento que el documento de pagos.
Esto es una comprobación funcional, no un benchmark de recuperación.

Navegador: carga Markdown, búsqueda, conservación tras recargar, retirada y carga
por arrastre de draw.io verificadas. Sin errores JavaScript; sin desbordamiento a
390, 768, 1024 y 1440 píxeles. Los documentos de prueba fueron retirados.

## Catálogo documental revisable

`tests/console/test_catalog_review.py` verifica extracción estructurada, fuentes,
agrupación, estado pendiente, confirmación, corrección de nombres, descarte,
invalidación al cambiar documentos, rechazo de revisiones antiguas y alcance de
logs por vecinos directos confirmados. Las llamadas cloud se simulan.

Se comprobó en un servidor local de prueba separado: confirmar cinco candidatos
tras renombrar uno y excluir otro actualiza el selector; recargar conserva la
revisión; añadir un documento invalida la confirmación y deshabilita el análisis
GKE hasta revisar de nuevo. La revisión se ajusta a escritorio y móvil de 390 px.
Los cambios de prueba no se aplicaron al catálogo de la sesión del usuario.

Mapa visual: seis nodos renderizados con las fuentes cargadas, actualización al
renombrar, acceso a fuente al seleccionar nodo y revisión sin desbordamiento en
móvil. Suite final de catálogo: 79 pruebas aprobadas; lint y formato correctos.
