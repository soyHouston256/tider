# Investigación adaptativa de Tider

Estado: implementación local con pruebas offline y una prueba de Haiku 5.5 real sobre evidencia simulada. Evaluación con telemetría real pendiente.

## Qué cambia

Con `LLM_PROVIDER=anthropic`, la consola usa un grafo LangGraph que alterna selección de acción,
herramienta y revisión. El modelo recibe el síntoma del usuario, el entorno y la ventana; no recibe
la regla baseline ni el registro de fallas de ChaosForge. Puede consultar de nuevo, corregir su
hipótesis después de una revisión y terminar reconociendo información insuficiente.

Con `LLM_PROVIDER=none` se conserva el motor anterior. La opción de síntoma libre está desactivada
en ese modo para no aparentar que las reglas interpretan lenguaje natural.

## Activación

Instalar los extras `llm` y `gcp` del proyecto en el entorno de ejecución. Configurar de forma local
la clave `ANTHROPIC_API_KEY`, `TIDER_MODEL` con un modelo disponible en esa cuenta y
`LLM_PROVIDER=anthropic`. Nunca pegar credenciales en documentación, commits o consultas web.
No se eligió un modelo ni se ejecutó inferencia pagada durante esta implementación.

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
  filtro literal opcional, errores prioritarios y páginas de grupos. Cada registro conserva su ID.
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

Por defecto: doce decisiones del investigador, noventa segundos comprobados entre acciones,
dos búsquedas externas y dos mil registros consultados. Una llamada ya iniciada puede superar
el presupuesto temporal hasta su propio timeout; no es cancelación dura del proveedor.
Los errores de herramientas no cuentan como telemetría. Un documento o una cita inventada no
pueden respaldar una conclusión. La revisión del LLM sigue siendo falible; 0.7 es una puntuación
heurística, no probabilidad calibrada. El resultado se limita siempre a observación.

La ruta `POST /v1/incidents/investigate-stream` transmite eventos NDJSON de consultas completadas
y el resultado final. La UI muestra esos eventos sin la animación artificial de etapas. Si se corta
la conexión, el análisis puede seguir en el servidor; consultar historial antes de repetir.
El JSON exportado conserva consultas, resultados, candidato, catálogo, documentos, modelo y conteos.
No se registra cadena de pensamiento privada. Tokens/costo monetario todavía no se contabilizan.

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
Resultado local: out/haiku-smoke-test.json. La consola habitual sigue en modo reglas.
