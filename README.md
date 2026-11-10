# TiderOps · Agentes de diagnóstico

Asesor de incidentes para Online Boutique: investiga, presenta la evidencia y propone
una acción para revisión humana; **no ejecuta cambios en el clúster**. El producto
vigente es un único motor agéntico (`src/tider/console/agentic.py`) y, como línea
base sin LLM, un modo por reglas (investigador → juez → decisor → reporte). El grafo
anterior con ejecutor (dominio OpenTelemetry Demo) está
[archivado](docs/archive/remediacion/README.md). **Todo el código del agente y su
consola está en este proyecto.** ChaosForge administra el laboratorio donde se inyectan los fallos.

## E5 y taller del 31 de octubre

La [guía de evaluación](eval/e5/README.md) contiene los datos sintéticos congelados,
semillas y comandos de reproducción. El [notebook ejecutado](eval/e5/E5_Equipo04.ipynb)
recalcula los resultados y verifica las 96 ejecuciones registradas sin consultar
al proveedor. Son 12 casos distintos; estos resultados no validan recuperación
ni reducción de MTTR en producción.

```sh
uv sync --extra llm --extra dev --frozen
uv run python eval/course_e5.py --replay
uv run python eval/course_e5.py --summarize
```

La demo por reglas funciona sin API; una investigación nueva con LLM requiere
Internet y credenciales locales. El ZIP de E5 conserva la versión exacta del
código y los registros cuando los cambios todavía no están publicados.

## Ejecutar

Desde este directorio, con Python 3.12 y `uv`:

```bash
make setup
make run
```

Abrir **http://localhost:8080**. Elegir un escenario y pulsar **Analizar incidente**.
Swagger está en **http://localhost:8080/docs**. Detener el servidor con Ctrl+C.
Para otro puerto: `make run PORT=8088`.

El entorno actual ya está instalado. `make setup` crea o sincroniza `.venv` con
`uv.lock`; no hace falta configurar `PYTHONPATH` ni instalar desde otra carpeta.
También se puede ejecutar `.venv/bin/python -m tider.console` o `.venv/bin/tider-console`.
Para cargar configuración local explícita: `cp .env.example .env`; `make run` la lee.

El inicio utiliza cuatro escenarios sintéticos y reglas deterministas, sin acceso
a servicios externos. La consola analiza y propone; todas sus ejecuciones son de
observación. Los resultados incluyen señales `S01…`, decisiones con su motivo,
rondas de investigación, JSON descargable e historial de 50 análisis en memoria.

## Dónde está cada cosa

```text
project/code/tider/
├── src/tider/
│   ├── state.py              # Contratos del estado, hipótesis, veredicto y decisión
│   ├── llm.py, config.py     # Adaptador del modelo y variables de entorno
│   ├── tools/base.py         # Contrato Tool/ToolRegistry de las herramientas
│   ├── lake/                 # Contexto, ingesta, búsqueda y almacenamiento
│   └── console/
│       ├── api.py            # Fábrica FastAPI y rutas HTTP
│       ├── service.py        # Caso de uso de análisis e historial aislado
│       ├── analysis.py       # Modo por reglas (sin LLM) y acceso al motor agéntico
│       ├── baseline.py       # Diagnóstico por reglas sobre las señales
│       ├── explanation.py    # Traducción de eventos a decisiones legibles
│       ├── models.py         # Solicitud, resultado y pasos validados
│       ├── settings.py       # Configuración por aplicación
│       ├── providers/        # Mock, Cloud Logging y enmascarado
│       ├── resources/        # Escenarios JSON y contexto de Online Boutique
│       └── static/           # HTML, CSS y JavaScript separados
├── tests/                    # Regresión del motor y pruebas de consola
├── eval/                     # Evaluación de escenarios y variantes
├── examples/                 # Solicitud de ejemplo para la API
├── docs/                     # Arquitectura, decisiones y guías
├── scripts/                  # Instalación y utilidades del laboratorio
├── archive/legacy_engine/    # Grafo antiguo archivado (no vigente, no se empaqueta)
├── pyproject.toml            # Dependencias, comandos y calidad
├── uv.lock                   # Versiones resueltas
├── Makefile                  # setup / run / test / lint / format / docker
└── Dockerfile                # Imagen de la misma aplicación
```

## Entender y modificar

| Documento | Contenido |
|---|---|
| [Blueprint vigente en draw.io](docs/designs/tider-blueprint.drawio) | Blueprint de 5 capas (Communication, Context, Environment, Autonomy, Criticality) y roles del asesor |
| [Atlas anterior (archivado)](docs/archive/remediacion/atlas/README.md) | No vigente: 13 vistas del grafo antiguo de 8 etapas |
| [Arquitectura (archivada)](docs/archive/remediacion/architecture.md) | No vigente: recorrido con el grafo antiguo |
| [Decisiones de diseño](docs/decisions.md) | Qué se eligió, por qué, alternativas y referencias del curso |
| [Pruebas](docs/testing.md) | Casos, comandos y comprobación manual de la consola |
| [Motor operativo (archivado)](docs/archive/remediacion/README.md) | No vigente: webhook Alertmanager, política y ejecutores del grafo antiguo |
| [Siguiente integración](docs/roadmap.md) | Conectores y evaluación del laboratorio real |

## Context Lake en memoria

La consola incluye un panel plegable para cargar Markdown y draw.io y buscar
fragmentos con su fuente. Usa Chroma en memoria y embeddings locales; la primera
carga descarga el modelo. El índice se pierde al reiniciar el servidor.
El botón Revisar catálogo propone servicios y relaciones con fuentes para tu
confirmación. Ese catálogo alimenta el selector GKE y orienta la consulta de logs;
el diagnóstico sigue por reglas y aún no razona sobre los documentos cargados. Ver [alcance y límites](docs/context-lake.md).

## Configuración opcional

| Variable | Predeterminado | Uso |
|---|---|---|
| `EVIDENCE_MODE` | `mock` | `gcp` habilita Cloud Logging con credenciales ADC |
| `GOOGLE_CLOUD_PROJECT` | `tider-ops` | Proyecto del laboratorio |
| `GCP_CLUSTER` / `GCP_LOCATION` | `chaosforge-lab` / `us-central1` | Alcance del filtro |
| `GCP_NAMESPACE` | `boutique` | Namespace analizado |
| `GCP_LOG_LIMIT` | `100` | Máximo de entradas, hasta 200 |
| `LLM_PROVIDER` | `none` | `anthropic` activa el adaptador de modelo |
| `TIDER_MODEL` | vacío | Modelo explícito al usar Anthropic |
| `HISTORY_LIMIT` | `50` | Análisis conservados por proceso |

`EVIDENCE_MODE=gcp make run` habilita la fuente GKE en la consola. Las consultas
se limitan a una ventana de hasta dos horas y a los servicios del incidente.
Actualmente el conector recibe logs. Un error del proveedor se muestra como error;
la selección de fuente se conserva.

Para usar el modelo: configurar `LLM_PROVIDER=anthropic`, `TIDER_MODEL` y
`ANTHROPIC_API_KEY`. El proveedor recibe la evidencia enmascarada. La consola
mantiene el modo observación. `make setup` incluye los extras `dev`, `gcp` y `llm`.

Alternativa Docker: `make docker`. Detener con
`docker compose --profile console down`. La imagen incluye el extra GCP y usa
reglas locales; para incluir un modelo externo debe añadirse el extra `llm` al build.
El servicio Postgres del motor se activa por separado con
`docker compose --profile lake up -d pg`.

## Validar un cambio

La evaluación local mide por separado los fragmentos que encuentra el RAG, los servicios localizados y los mecanismos identificados con evidencia. Incluye una corrida grabada que se puede volver a puntuar. [Comandos y resultados de la evaluación](eval/quality/README.md).

```bash
make test
make lint
```

La implementación anterior en `tider-mock/tiderops/agents/rca` fue absorbida aquí.
Los antiguos scripts de arranque redirigen a este proyecto. Los scripts de kind y
Terraform permanecen con los entornos; no contienen otra implementación del agente.
