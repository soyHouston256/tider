# Investigación adaptativa de Tider

Estado: corrección local del 31/10/2026, con 130 pruebas automatizadas y una validación acotada
de Haiku 5.5 sobre señales de GKE guardadas. La evaluación independiente con varios incidentes sigue pendiente.

## Qué cambia

Con `LLM_PROVIDER=anthropic`, la consola usa un grafo LangGraph que alterna selección de acción,
herramienta y revisión. El modelo recibe el síntoma del usuario, el entorno y la ventana; no recibe
la regla baseline ni el registro de fallas de ChaosForge. Puede consultar de nuevo, corregir su
hipótesis después de una revisión y terminar reconociendo información insuficiente.

La pantalla comienza en alcance general. Un síntoma como «se cayó el sistema, investiga» inicia
una consulta de errores en todos los servicios del catálogo confirmado, sin seleccionar cartservice
por defecto. El modelo recibe la topología compacta y un resumen por servicio antes de elegir
comprobaciones adicionales. La API usa alcance general si no se proporcionan servicio ni alcance;
los clientes anteriores que solo envían un servicio conservan el alcance enfocado.

Con `LLM_PROVIDER=none` se conserva el motor anterior. La opción de síntoma libre está desactivada
en ese modo para no aparentar que las reglas interpretan lenguaje natural.

## Activación

Instalar los extras `llm` y `gcp` del proyecto en el entorno de ejecución. Configurar de forma local
la clave `ANTHROPIC_API_KEY`, `TIDER_MODEL` con un modelo disponible en esa cuenta y
`LLM_PROVIDER=anthropic`. Nunca pegar credenciales en documentación, commits o consultas web.
`AGENT_MODEL_EFFORT` es opcional (`low`, `medium`, `high`) y solo debe configurarse en modelos
compatibles. La instalación local usa Haiku 5.5 con `low`; se verificó en el caso registrado, no
en un benchmark amplio. Menor esfuerzo puede reducir latencia y también capacidad, según la
[documentación de Anthropic](https://platform.claude.com/docs/en/build-with-claude/effort).

Los parámetros se leen del entorno del proceso; el punto de entrada de consola admite el archivo
de configuración según su opción de arranque. Reiniciar puede vaciar documentos y catálogo en memoria:
exportar/conservar los archivos de contexto antes de reiniciar y volver a confirmar si hace falta.

Para GCP: `EVIDENCE_MODE=gcp`, ADC de lectura y un catálogo confirmado.
Para Kubernetes: `AGENT_READER_KUBECONFIG` y `AGENT_KUBE_CONTEXT` explícitos, con identidad de
solo lectura para deployments, pods y endpointslices del namespace configurado. El servidor solo
construye comandos get; no registra herramientas de modificación ni cambia IAM.

## Herramientas

- `context_search`: búsqueda Chroma en los documentos del usuario, con referencias. Rechaza mezclar
  revisiones si cambia el Context Lake mientras investiga. Se guarda una copia documental por resultado.
- `service_catalog`: catálogo confirmado, relaciones y alias. No es un inventario vivo.
- `search_logs`: consultas nuevas, acotadas a servicios del catálogo y al intervalo autorizado;
  filtro literal opcional, errores prioritarios y páginas de grupos intercalados por servicio.
  Cada consulta lee hasta 200 registros por defecto (`limit` permite 1..500), dentro del presupuesto
  total. `truncated` e `incomplete` indican cobertura parcial, no ausencia de fallos. Una lectura
  interrumpida conserva los registros que ya recibió. Cada registro conserva su ID.
- `service_state`: estado actual de réplicas, pods y endpoints. Su timestamp no demuestra estado histórico.
- `service_metrics`: opcional (`AGENT_METRICS_ENABLED=true`), CPU y memoria de Cloud Monitoring.
  La asociación inicial usa prefijo del pod y se declara como tal; no prueba ownership. Muestras limitadas
  indican si queda otra página. No incluye todavía métricas de negocio, latencia o traces.
- `search_documentation`: opcional (`AGENT_WEB_ENABLED=true`, `TAVILY_API_KEY`), hasta dos consultas
  genéricas a documentación de Google Cloud, Kubernetes y gRPC. No acredita salud del entorno.
  Se rechazan identificadores del entorno, direcciones y patrones conocidos de credenciales. El
  enmascarado es defensivo, no una garantía de detección de cualquier dato privado.

## SDK o MCP

`AGENT_LOGGING_TRANSPORT=sdk` utiliza el conector existente. `mcp` utiliza exclusivamente
`list_log_entries` del endpoint fijo `https://logging.googleapis.com/mcp`, protocolo 2026-07-28.
La misma capa local construye y limita los filtros; el modelo no elige endpoints, proyectos ni
herramientas MCP arbitrarias. No hay fallback silencioso de MCP a SDK.

Se comprobó el esquema público `tools/list`; la llamada autenticada permanece pendiente de permisos
ADC/IAM adecuados y validación en el entorno. No ampliar permisos a administrador automáticamente.
Fuentes: [Google Logging MCP](https://docs.cloud.google.com/logging/docs/use-logging-mcp),
[Tavily Search](https://docs.tavily.com/documentation/api-reference/endpoint/search),
[Monitoring timeSeries](https://docs.cloud.google.com/monitoring/api/ref_v3/rest/v3/projects.timeSeries/list).

## Límites y trazabilidad

Por defecto: doce decisiones del investigador, noventa segundos, dos búsquedas externas y dos mil
registros consultados. Las llamadas a Anthropic reciben como timeout el tiempo restante, con máximo
25 segundos. Hay una sola recuperación por ejecución ante un error transitorio, con máximo 15
segundos y solo si quedan al menos diez. Se reserva tiempo para resumir y revisar lo encontrado.
El conector SDK agentic recalcula el timeout en cada página (máximo diez segundos por RPC y quince
por consulta), sin reintentos implícitos. Los timeouts no garantizan cancelación dura del transporte
o de la autenticación. Las herramientas opcionales conservan sus propios límites.
Los errores de herramientas no cuentan como telemetría. Un documento o una cita inventada no
pueden respaldar una conclusión. La revisión del LLM sigue siendo falible. El agente ya no asigna
0 ni 0.7: `confidence` y `workflow.verdict.confidence` son `null`. La UI muestra el estado de revisión.
Un hallazgo observado puede estar respaldado aunque su causa raíz siga sin determinarse.
`status=partial` conserva señales o un candidato sin revisión favorable; `review_status` distingue
revisión aprobada, rechazada, fallida o no ejecutada. `stop_reason` y `errors` separan presupuesto,
timeout, respuesta truncada, JSON/esquema inválido y error del proveedor. La puntuación del baseline
por reglas y los JSON históricos se conservan. El resultado se limita siempre a observación.

La ruta `POST /v1/incidents/investigate-stream` transmite eventos NDJSON de consultas completadas
y el resultado final. La UI muestra esos eventos sin la animación artificial de etapas. Si se corta
la conexión, el análisis puede seguir en el servidor; consultar historial antes de repetir.
El JSON exportado conserva consultas, resultados, candidato, catálogo, documentos, modelo y conteos.
No se registra cadena de pensamiento privada. `model_requests` guarda duración, límite, tokens y
stop reason de respuestas recibidas. Un timeout puede no devolver uso; no se calcula costo monetario.

El historial sigue en RAM por defecto. `INVESTIGATION_HISTORY_PATH=out/investigations.sqlite`
activa persistencia local del historial acotado. Incluye documentación y evidencia enmascarada:
proteger ese archivo. No persiste el Context Lake operativo ni implementa reanudación de un grafo
interrumpido. Las credenciales y claves no se incluyen en el resultado.

## Validación y siguiente prueba

Pruebas offline: elección condicionada por observaciones; nueva consulta tras rechazo del juez;
rechazo de citas inventadas y evidencia solo documental; presupuestos y páginas; cambio de revisión;
lectura Kubernetes acotada; paginación MCP con página vacía; streaming; restauración de historial.
Estas pruebas verifican infraestructura y control del agente, no calidad de un modelo real.

Evaluación pendiente: incidentes independientes de ChaosForge, sin revelar al agente el componente
interrumpido. Comparar reglas/agente sobre componente, causa respaldada, abstención, citas,
consultas y duración. Incluir entorno sano, evidencia ausente, recuperación antes de consultar,
documentación contradictoria y fallas en servicios no usados para ajustar alias.

Subagentes y remediación autónoma quedan fuera de esta primera versión, conforme al plan por fases.

## Primera prueba del modelo real

Haiku 5.5 completó una investigación aislada del escenario sintético de Redis: cinco consultas y
una revisión final (siete llamadas al modelo). Identificó redis-cart como componente implicado,
sin afirmar una causa raíz no demostrada. Dos consultas quedaron fuera del alcance del fixture;
el reporte reconoció esos vacíos y que el catálogo de esa prueba estaba pendiente.
Consumo observado: 22 119 tokens de entrada y 5 707 de salida. Esto verifica integración y
comportamiento inicial, no exactitud en incidentes reales ni evaluación independiente amplia.
Resultado local de aquella prueba: out/haiku-smoke-test.json.

## Reproducción del incidente del 31 de octubre

La ejecución original guardó 290 señales, un candidato sobre Redis, un fallo de revisión ocultado
y un cierre por presupuesto a los 90,5 segundos. Su excepción original no se registró y no puede
recuperarse. Una repetición aislada del juez respondió correctamente; otra validación reprodujo
un `APITimeoutError` del investigador, ahora conservado como error técnico con las señales intactas.

Con el fix y esfuerzo `low`, el síntoma original en alcance general completó una validación en
18,7 segundos, con dos consultas sobre la muestra guardada y tres llamadas reales a Anthropic.
El hallazgo señaló fallos de cartservice al acceder a Redis y propagación a frontend, sin afirmar
la causa del corte. Es una observación de una ejecución, no un SLA ni una medición de exactitud.
El archivo guardado solo contiene las señales que recuperó el análisis enfocado original; no
representa una consulta nueva y completa de todos los servicios. El historial de ChaosForge se
contrastó por separado como referencia de la prueba y no se entregó al investigador.
