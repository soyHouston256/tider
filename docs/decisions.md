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
documentación y diagramas. El seguimiento está en
[Pendiente: elección del proveedor LLM](roadmap.md#pendiente-elección-del-proveedor-llm).

## Mapa de migración

| Antes | Ahora |
|---|---|
| `agents/rca/app/main.py` | `console/api.py` + `console/service.py` |
| `app/config.py` y singleton | `console/settings.py` por aplicación |
| `app/schemas.py` | `console/models.py` |
| `app/engine.py` | `console/analysis.py` |
| `app/rca.py` | `console/baseline.py` |
| `app/evidence.py` | `console/providers/` + `resources/scenarios.json` |
| `app/context/` | `console/resources/context/` |
| `app/static/app.js` | `static/js/api.js`, `render.js`, `app.js` |
| `agents/rca/tests/` | `tests/console/` |
| Dos requirements y lock previo | `pyproject.toml` + `uv.lock` |
