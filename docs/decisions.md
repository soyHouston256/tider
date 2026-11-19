# Decisiones de diseño · 17/10/2026

Estado: aplicado. El objetivo de esta reorganización es mantener una sola aplicación,
hacer legible el flujo y conservar el comportamiento comprobable del motor.

## Referencias revisadas del curso

Repositorios locales de `utec/especialidades/agents`:

| Referencia | Patrón observado | Aplicación en TiderOps |
|---|---|---|
| `agents26_m5s13/main.py`, `prompt.py`, `toolbox.py` | Separación de instrucciones, herramientas y salida Pydantic | `agents/prompts.py`, `tools/` y contratos tipados de consola |
| `agents26m5s12/main.py`, `prompts.py`, `tools.py` | Entrada pequeña y herramientas explícitas | Comando instalable y registro acotado de herramientas |
| `agents26_m5s14/server/main.py`, `client/app.py` | Cliente separado de API | JS sin lógica de diagnóstico; FastAPI como borde HTTP |
| `Modulo6/sol/maslc.py` | Estado, clasificación y transiciones de LangGraph | `state.py`, agentes con responsabilidad concreta y `graph.py` declarativo |
| `agents26_m8s22/team.py` | Equipo con revisión y rutas de retorno | Rondas de investigación/juez visibles y acotadas |
| `Showdown/README.md` y agentes de consola | Distinción entre workflow, herramientas y agente | Modo de razonamiento explícito y fuentes registradas |
| `agents26_m8s23/README.md` | Contrato de invocación para pruebas; efectos al importar como problema | Inyección de dependencias y construcción explícita de la aplicación |

Los ejemplos son material didáctico: varios concentran un ejercicio completo en un
script. Para esta aplicación se adopta su separación conceptual y se organiza en
un paquete instalable. No se copian campañas, servicios externos ni efectos al importar.

## D01 · Un paquete y una raíz de desarrollo

**Problema:** el motor estaba en `project/tider`, la consola en
`tider-mock/tiderops/agents/rca/app`, con dos listas de dependencias y `PYTHONPATH`
manual. El Dockerfile dependía de la raíz completa del workspace.

**Decisión:** mantener una raíz canónica (actualmente `project/code/tider`), que ya contiene el repositorio del motor,
y absorber allí la consola en `src/tider/console`. Un `pyproject.toml` describe las
capacidades y `uv.lock` fija las versiones. HTML, CSS, JSON, Markdown de contexto,
política YAML y esquema SQL forman parte del paquete distribuible.

**Alternativas consideradas:** conservar dos proyectos con dependencia relativa;
crear un tercer proyecto para envolverlos. Ambas mantienen más puntos de instalación
sin aportar una separación de despliegue necesaria para este prototipo.

**Consecuencias:** un entorno, una suite y una imagen. Los launchers anteriores
redirigen a la raíz canónica. El código antiguo de consola se retira después de
validar la migración. ChaosForge, los entornos y la entrega histórica conservan
su finalidad separada.

## D02 · Orquestación, agentes y política separados

**Problema:** `graph.py` mezclaba transiciones y cuerpos de ejecución/verificación;
los prompts estaban intercalados con bucles de herramientas.

**Decisión:** `graph.py` declara el flujo; `agents/` contiene el trabajo de cada agente;
`agents/prompts.py` concentra las instrucciones; `workflow/nodes.py` contiene las
etapas deterministas. La política sigue en `decision/`, con su YAML.

**Consecuencia:** se puede revisar una transición, un prompt o una regla sin recorrer
la interfaz web o los clientes de infraestructura. No se añade otro framework ni
un sistema de plugins; LangGraph sigue siendo el único orquestador.

## D03 · Configuración y dependencias explícitas

**Problema:** la consola usaba configuración e historial globales. HTTP, obtención
de evidencia, invocación del motor y almacenamiento estaban en una sola función.

**Decisión:** `create_app()` compone `AnalysisService`, `EvidenceProvider` y
`LabEngine`. El servicio depende de contratos mínimos y posee su historial.
Cada ejecución construye sus dependencias mutables del grafo. Los conectores reciben
configuración; las importaciones no crean clientes cloud ni hacen consultas.

**Consecuencia:** dos aplicaciones o análisis concurrentes no comparten cursores de
respuestas ni resultados. El historial sigue siendo memoria local acotada; persistencia
y despliegue con varias réplicas siguen como trabajo de integración.

## D04 · Explicaciones desde eventos observados

**Problema:** para entender una decisión había que abrir un JSON y adivinar qué
ocurrió en cada ronda. Un diagrama con una marca por agente no muestra reintentos.

**Decisión:** conservar motivos del investigador/juez en cada evento; devolver
`DecisionStep` tipado con resultado, motivo, estado e IDs de señales consultadas.
La UI muestra esos pasos en orden y conserva el JSON como detalle técnico.

**Alternativa considerada:** pedir a otro modelo que redacte la explicación.
Se descarta porque añadiría costo, latencia y otra interpretación de los hechos.

**Consecuencia:** la explicación puede contrastarse directamente con la auditoría.
No se cambia la confianza, el diagnóstico ni la política para mejorar su presentación.

## D05 · Observación como capacidad del grafo de la consola

**Decisión conservada:** la consola compila `observation_only=True`. Las variables
del motor operativo no pueden habilitar remediaciones desde esta entrada. El modo
local usa datos sintéticos; GCP y el modelo externo se activan de forma explícita.

**Consecuencia:** los cuatro casos se prueban sin infraestructura ni consumo externo.
Las herramientas operativas siguen disponibles en la entrada autenticada del motor,
con sus propios controles y pruebas. Las pruebas no afirman validación del LLM o
acceso real al laboratorio cuando se utilizan clientes y respuestas simulados.

## D06 · Proveedor LLM provisional

**Estado al 20/10/2026:** Anthropic permanece como integración opcional provisional.
La elección del proveedor y del modelo definitivos sigue abierta. Cuando se
confirme, se actualizarán conjuntamente implementación, configuración, pruebas,
documentación y diagramas. El seguimiento se llevaba en `docs/roadmap.md`, retirado
del repositorio en D08.

## D07 · Retiro del grafo del núcleo · 09/11/2026

**Estado:** aplicado en la rama `archivo-grafo-antiguo`. Sustituye a D02 y D05 en lo
que describen el grafo `graph.py` como motor de la consola; las entradas anteriores
se conservan como registro histórico.

**Problema:** convivían dos motores. El grafo del núcleo (`graph.py`, agentes,
política, ejecutor, webhook Alertmanager) estaba escrito para el dominio
OpenTelemetry Demo (`otel-demo`, flagd), mientras el laboratorio vigente es Online
Boutique en ChaosForge. Su ejecutor con RBAC contradice el modo asesor del producto,
y la consola ya investiga con su propio motor agéntico; el grafo solo seguía en uso
para envolver el modo por reglas en un modelo guionado.

**Decisión:** el producto vigente es un único motor agéntico
(`src/tider/console/agentic.py`), solo asesor, más el modo por reglas
(`console/baseline.py`, `catalog_diagnosis.py`) como línea base sin LLM, que registra
investigador → juez → decisor → reporte sin ejecutar nada. El grafo, el ejecutor, el
webhook, sus herramientas OTel, su arnés de evaluación, sus pruebas y el atlas de 13
vistas se archivan dentro del repositorio (`archive/legacy_engine/`,
`tests/_archivo/`, `docs/archive/remediacion/`), fuera del paquete y de la imagen.
Fuente: decisiones 6, 19 y 26 de `recomend/_auditoria_consolidada.md`.

**Consecuencias:** `tider.tools.default_registry()` y `FixtureRegistry` sin `spec`
lanzan un error explícito ("archivado"). `docs/runbooks/` se conserva porque es el
corpus congelado de `eval/quality`. El diagrama vigente es
`docs/designs/tider-blueprint.drawio`. Retomar la remediación es una decisión nueva.
El material archivado se retiró del repositorio en D08 y se recupera desde el historial
de git.

## D08 · Limpieza del repositorio · 19/11/2026

**Problema:** el repositorio conservaba el motor anterior archivado, documentos de
etapas ya cerradas y código que ningún punto de entrada usaba. Dificultaba ver qué
forma parte del producto vigente.

**Decisión:** se retira del árbol todo lo que no usan la consola, el registrador, las
pruebas ni las evaluaciones, y la documentación que se conserva queda en `docs/`:

- `archive/legacy_engine/`, `tests/_archivo/` y `docs/archive/` (grafo anterior, sus
  pruebas, su arnés y el atlas de 13 vistas);
- `docs/roadmap.md` (estado del 17/10/2026), `notes/` y la v1 de `tokens.json`;
- los cinco informes de etapa de `docs/designs/revision/`; el informe consolidado, que
  define las acciones A01–A47 y las decisiones P1–P9 citadas por el código y el
  protocolo, pasa a `docs/designs/tider-diseno-piloto-revision.md`;
- `src/tider/lake/store.py`, `embed.py` y `schema.sql`, el servicio Postgres de
  `docker-compose.yml` y `console/resources/context/`, que ya no tenían quién los leyera;
- `tider.tools.default_registry()`, `FixtureRegistry`, `Alert`, `IncidentState` y las
  funciones de `tider/config.py` que solo leía el motor anterior;
- `examples/analyze.json` pasa a `docs/examples/analyze.json`.

Todo lo retirado sigue en el historial de git: el último commit que lo contiene es
`5dbef82`.

**Se conserva sin cambios:** `docs/runbooks/` y `eval/quality` (entradas congeladas del
benchmark), `eval/e5` (evaluación sintética del entregable E5 y sus registros) y
`src/tider/lake/ingest.py`, cuya huella figura en la captura de recuperación del
benchmark.

**Pendiente:** el extra opcional `pg` de `pyproject.toml` quedó sin código que lo use;
quitarlo requiere regenerar `uv.lock`.

## Mapa de migración

| Antes | Ahora |
|---|---|
| `agents/rca/app/main.py` | `console/api.py` + `console/service.py` |
| `app/config.py` y singleton | `console/settings.py` por aplicación |
| `app/schemas.py` | `console/models.py` |
| `app/engine.py` | `console/analysis.py` |
| `app/rca.py` | `console/baseline.py` |
| `app/evidence.py` | `console/providers/` + `resources/scenarios.json` |
| `app/context/` | `console/resources/context/` (retirado en D08) |
| `app/static/app.js` | `static/js/api.js`, `render.js`, `app.js` |
| `agents/rca/tests/` | `tests/console/` |
| Dos requirements y lock previo | `pyproject.toml` + `uv.lock` |
