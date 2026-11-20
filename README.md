# TiderOps · Agentes de diagnóstico

Asesor de incidentes para Online Boutique: investiga, presenta la evidencia y propone
una acción para revisión humana; **no ejecuta cambios en el clúster**. La consola
tiene dos caminos de análisis: el motor agéntico (`src/tider/console/agentic.py`,
pipeline v1, predeterminado) y el pipeline v2 del piloto
(`src/tider/console/pipeline_v2.py`, con `TIDER_PIPELINE=v2`). Cada uno tiene un modo
por reglas, sin LLM, como línea base. **Todo el código del agente y su consola está
en este proyecto.** ChaosForge administra el laboratorio donde se inyectan los fallos.

## Ejecutar el prototipo

Requisitos: `git`, `make` y [`uv`](https://docs.astral.sh/uv/getting-started/installation/).
No hace falta tener Python instalado: `uv` descarga la versión 3.12. Este modo no usa nube,
claves ni Kubernetes. Probado en macOS y Linux.

```bash
git clone https://github.com/soyHouston256/tider.git
cd tider
make setup    # crea .venv con las versiones exactas de uv.lock
make run      # consola en http://localhost:8080
```

1. Abrir **http://localhost:8080**.
2. Elegir el escenario **Redis no disponible** y pulsar **Analizar incidente**.
3. La consola identifica `redis-cart`, muestra las cuatro señales que lo sustentan, cada decisión
   con su motivo y una propuesta para revisión humana. Nada se ejecuta sobre ningún sistema.

Los otros tres escenarios dan: **Cart Service sin endpoints** → `cartservice` (tres señales);
**Operación normal** y **Sin telemetría** → ninguna causa raíz, porque la evidencia no alcanza.

Swagger está en **http://localhost:8080/docs**. Detener el servidor con Ctrl+C. Para otro
puerto: `make run PORT=8088`. Para comprobar la instalación: `make test` (286 pruebas, menos
de un minuto, sin red).

`make setup` crea o sincroniza `.venv` con `uv.lock`; no hace falta configurar `PYTHONPATH`.
Sin `make`, lo mismo se hace con
`uv sync --frozen --extra dev --extra gcp --extra llm --python 3.12` y
`.venv/bin/python -m tider.console`.
`make run` lee un archivo `.env` si existe (`cp .env.example .env`); sin él usa los valores
predeterminados, que son los de este modo.

El modo predeterminado usa cuatro escenarios sintéticos y reglas deterministas, sin acceso
a servicios externos. Los resultados incluyen señales `S01…`, decisiones con su motivo,
rondas de investigación, JSON descargable e historial de 50 análisis en memoria.

## Piloto en el laboratorio (pipeline v2)

El piloto corre contra Online Boutique en GKE, con fallas inyectadas por ChaosForge.
Requiere credenciales ADC, el panel de ChaosForge abierto y un `.env` con
`EVIDENCE_MODE=gcp`, `TIDER_PIPELINE=v2`, `RECORDER_DB_PATH`, `LAKE_V3_PATH` y
`AGENT_OBSERVER_URL` (`.env.example` lista todas las variables). Del observador de
ChaosForge salen las medidas de latencia y de CPU; sin él, las firmas que las usan
quedan sin datos.

```bash
uv run python -m tider.console.recorder --env-file .env   # registrador de estado; se deja corriendo
set -a; source .env; set +a                               # el orquestador lee el entorno del shell
uv run python -m eval.pilot.runner --validate-signatures --dry-run   # imprime el plan sin llamar a nada
uv run python -m eval.pilot.runner --validate-signatures --out out/runs/<carpeta>
```

`--validate-signatures` inyecta cada mecanismo una vez y escribe `gate.json`; `--campaign`
exige ese `gate.json` con `go = true`. El [diseño del piloto](docs/designs/tider-diseno-piloto.md)
describe el pipeline y la evaluación; el protocolo prerregistrado está en
`eval/pilot/protocol.yaml`.

Para analizar un caso real desde la consola, con el registrador corriendo:

```bash
set -a; source .env; set +a
TIDER_PIPELINE=v2 LLM_PROVIDER=none make run
```

En la consola: **Revisar catálogo** → seleccionar todo → **Confirmar catálogo**; elegir
**Logs de GKE · reales** y la ventana del incidente (**Últimos 10 minutos** o **Elegir horas
de hoy**); pulsar **Analizar incidente**. El inicio de la ventana se toma como inicio del
incidente, y el tramo anterior de la misma duración, como línea base.

### Estado y límites al 19/11/2026

- En ensayos con fallas reales inyectadas, el pipeline v2 en modo reglas confirmó la firma
  esperada, y ninguna otra, para servicio sin instancias (`scale_zero`), configuración
  incorrecta (`wrong_port`) y dependencia lenta (`latency`). En el control sin falla no
  confirmó ninguna. Las trazas y el detalle están en
  [`eval/pilot/results/`](eval/pilot/results/README.md).
- Saturación de CPU (`cpu_limit`): Tider la detectó en un ensayo, pero ChaosForge no acreditó
  la inyección porque su plazo de preparación venció antes de poder medir el efecto. No se
  cuenta como validada.
- La campaña de 70 casos del protocolo todavía no se ejecutó: no hay métricas de exactitud
  del piloto.
- En el laboratorio se probó el modo por reglas. El Investigador y el Juez con modelo del
  pipeline v2 solo se ejercitaron con clientes simulados, en las pruebas automáticas.
- La latencia y la CPU salen del observador de ChaosForge, que solo mide `cartservice` y su
  dependencia de Redis. La latencia es la mediana por tramos de 30 s (ver
  `src/tider/console/evidence/gke.py`).

## Evaluación E5 (sintética, 31 de octubre)

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

`--replay` vuelve a ejecutar el motor sobre las respuestas registradas: coincidía con
el código congelado el 29/10/2026 (el del ZIP de E5) y deja de coincidir con el motor
actual, que cambió después. `--summarize` recalcula las métricas desde los registros.

La demo por reglas funciona sin API; una investigación nueva con LLM requiere
Internet y credenciales locales. El ZIP de E5 conserva la versión exacta del
código y los registros cuando los cambios todavía no están publicados.

## Dónde está cada cosa

```text
tider/
├── src/tider/
│   ├── state.py              # Contratos de evidencia, hipótesis, veredicto y decisión
│   ├── llm.py, config.py     # Adaptadores de modelo y lectura de variables de entorno
│   ├── tools/base.py         # Contrato Tool/ToolRegistry de las herramientas
│   ├── lake/                 # Ingesta Markdown y Mermaid que usa el Context Lake
│   └── console/
│       ├── api.py            # Fábrica FastAPI y rutas HTTP
│       ├── service.py        # Caso de uso de análisis e historial aislado
│       ├── analysis.py       # Modo por reglas (sin LLM) y acceso a los motores
│       ├── agentic.py        # Motor agéntico (pipeline v1)
│       ├── pipeline_v2.py    # Pipeline v2 del piloto: barrido, firmas, roles, juez y reporte
│       ├── signatures.py     # Verificador de firmas (catálogo en resources/catalog_v1.yaml)
│       ├── recorder.py       # Registrador de estado de Kubernetes (tider-recorder)
│       ├── evidence/         # Barrido y modelo común de evidencia
│       ├── providers/        # Mock, Cloud Logging, catálogo y enmascarado
│       ├── resources/        # Escenarios sintéticos y catálogo de firmas
│       └── static/           # HTML, CSS, JavaScript y fuentes de la consola
├── tests/                    # Pruebas del núcleo y de la consola
├── eval/
│   ├── pilot/                # Protocolo, orquestador, puntuación y resultados del piloto
│   ├── quality/              # Benchmark de recuperación y diagnóstico (entradas congeladas)
│   └── e5/                   # Evaluación sintética E5 y sus registros
├── docs/                     # Diseño, decisiones, guías, runbooks y solicitud de ejemplo
├── deploy/                   # RBAC de solo lectura del registrador y del barrido
├── scripts/                  # Instalación del entorno
├── out/                      # Salidas locales (corridas, historial); no se versionan
├── pyproject.toml            # Dependencias, comandos y calidad
├── uv.lock                   # Versiones resueltas
├── Makefile                  # setup / run / test / lint / format / docker
└── Dockerfile                # Imagen de la misma aplicación
```

## Entender y modificar

| Documento | Contenido |
|---|---|
| [Estado y visión del producto](docs/designs/tider-pagina-asesor.md) | Qué existe, qué se construye y qué queda en plan |
| [Blueprint vigente en draw.io](docs/designs/tider-blueprint.drawio) | Blueprint de 5 capas (Communication, Context, Environment, Autonomy, Criticality) y roles del asesor |
| [RFC del asesor de incidentes](docs/designs/tider-asesor-incidentes.md) | Propuesta de producto y alcance; [resumen](docs/designs/tider-asesor-incidentes-resumen.md) |
| [Diseño del piloto](docs/designs/tider-diseno-piloto.md) | Pipeline v2, firmas, registrador y protocolo de evaluación |
| [Revisión del diseño del piloto](docs/designs/tider-diseno-piloto-revision.md) | Acciones A01–A47 y decisiones P1–P9 que citan el código y el protocolo |
| [Sistema visual](docs/designs/sistema-visual/DESIGN.md) | Colores, tipografía y componentes de la consola |
| [Investigación adaptativa](docs/agentic-investigation.md) | Cómo investiga el motor agéntico y sus límites |
| [Context Lake](docs/context-lake.md) | Alcance y límites de la recuperación documental |
| [Decisiones de diseño](docs/decisions.md) | Qué se eligió, por qué, alternativas y referencias del curso |
| [Pruebas](docs/testing.md) | Casos, comandos y comprobación manual de la consola |

`docs/runbooks/` es el corpus congelado del benchmark de `eval/quality`: no se edita ni se
le agregan archivos sin versionar ese protocolo.

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

## Validar un cambio

La evaluación local mide por separado los fragmentos que encuentra el RAG, los servicios localizados y los mecanismos identificados con evidencia. Incluye una corrida grabada que se puede volver a puntuar. [Comandos y resultados de la evaluación](eval/quality/README.md).

```bash
make test
```

`make lint` revisa el estilo con ruff. Hoy reporta avisos de formato pendientes en archivos
anteriores; no afectan la ejecución ni las pruebas.
