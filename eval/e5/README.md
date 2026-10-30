# Evaluación E5 y taller del 31 de octubre de 2026

Este paquete compara el prototipo TiderOps v0 con tres referencias sobre **12 casos sintéticos escritos para esta evaluación**. No son incidentes nuevos de SIBI ni un benchmark independiente. El resultado evalúa el componente implicado o la abstención, no demuestra recuperación, reducción de MTTR ni causa raíz operativa.

## Ejecutar en el Mac del taller

Desde la raíz de este repositorio, con Python 3.12 y las dependencias de `uv.lock`:

```sh
uv sync --extra llm --extra dev --frozen
uv run python eval/course_e5.py --replay
uv run python eval/course_e5.py --summarize
```

En el Mac de Max ya está instalado el entorno; funcionan los mismos comandos reemplazando `uv run python` por `.venv/bin/python`. La reproducción utiliza respuestas registradas, valida los hashes de las solicitudes y vuelve a ejecutar el grafo y sus herramientas locales. **No vuelve a consultar el LLM**. La latencia de reproducción no sustituye la latencia de las llamadas originales.

Para iniciar la consola con la demostración sintética por reglas, sin nube:

```sh
EVIDENCE_MODE=mock LLM_PROVIDER=none TIDER_DRY_RUN=true TIDER_AUTONOMY=off .venv/bin/python -m tider.console --port 8765
```

Abrir `http://127.0.0.1:8765`, elegir un escenario y ejecutar la investigación. La consola entrega evidencia y una conclusión para revisión humana; no repara servicios. El modo de reglas funciona sin API. El agente nuevo en vivo necesita Internet y una clave configurada localmente.

Para una evaluación **nueva**, con llamadas pagadas al proveedor, guardar en otra carpeta; nunca sobrescribir la evidencia congelada:

```sh
uv run python eval/course_e5.py --live --out out/e5-nueva-ejecucion
```

No incluir `.env`, claves, kubeconfig ni telemetría empresarial en el repositorio o en el ZIP. No se requiere ChaosForge ni inyectar fallas para esta demo.

## Diseño congelado antes de medir

`manifest.json` contiene fecha de congelación, hashes, criterios y semillas. `cases.json` contiene únicamente entradas; `labels.json` contiene las etiquetas generadoras, que el evaluador nunca entrega al modelo. No se entrena ni ajusta ningún modelo o prompt con las salidas de esta corrida. Los autores conocían el código al construir los casos: existe sesgo de diseño y no se puede descartar contaminación del preentrenamiento sobre términos públicos de microservicios.

- Unidad: una ventana de incidente; decisión al final de esa ventana. Todas las señales son anteriores o iguales al corte.
- Segmentos: explícito, variaciones léxicas u otros servicios, evidencia insuficiente y estrés; 3 casos distintos por segmento.
- Referencias: abstenerse siempre; reglas actuales de la consola; un único LLM con catálogo y todos los logs. El proceso humano de SIBI todavía no está cronometrado y no se presenta como medido.
- Modelo v0: el `AgenticEngine` real de producción, con el mismo prompt y juez; solo se sustituye el proveedor de logs por fixtures congelados. Las herramientas de lectura y sus validaciones son las del producto. Catálogo fijo, sin RAG documental, sin web, sin GCP y sin escritura.
- El LLM simple y el agente tienen acceso al mismo conjunto de evidencia. El simple recibe los logs directamente; el agente debe recuperarlos. Es una comparación del costo de investigar, no un experimento que aísle solo el efecto del prompt.
- 3 repeticiones por caso y método estocástico; 1 por caso para referencias deterministas. Orden aleatorio con semilla 42. La API no ofrece aquí una semilla fijada; la temperatura se deja en su valor predeterminado como en producción. No se afirma determinismo de una nueva llamada.
- Presupuesto por investigación: 8 decisiones, 240 segundos y 100 registros; máximo 2.000 tokens de salida por llamada. La revisión del juez puede añadir llamadas. Límite global conservador de 700.000 tokens observados, comprobado entre casos.

## Métricas y límites de interpretación

Exactitud = media, entre los 12 casos, de la fracción de repeticiones cuyo componente o abstención coincide exactamente con la etiqueta. Un error de API cuenta como fallo, no como abstención correcta. Contrapeso = respuestas que afirman un componente incorrecto / todas las ejecuciones. También se reportan abstenciones, errores de API, tokens de entrada/salida, tiempo de pared, p95 y acciones ejecutadas.

El IC del 95% usa 5.000 remuestreos de **casos completos** (semilla 1011), manteniendo juntas sus repeticiones. La diferencia entre métodos es pareada por caso. No se trata a las 36 respuestas como 36 incidentes independientes. Los rangos de costo y latencia son mínimo–máximo observado, no intervalos de confianza. Los IC bootstrap [100%,100%] son degenerados por esta muestra pequeña y no demuestran exactitud perfecta en una población.

El puntaje heurístico 0,7 del agente no es una probabilidad calibrada. El juez LLM pertenece al sistema evaluado, no es la verdad de terreno. Las etiquetas son sintéticas y la puntuación es programática. La corrección semántica del texto, el sustento de citas y la seguridad de recomendaciones requieren revisión humana independiente; su κ todavía no está medido.

El vínculo con el negocio es una hipótesis: más localizaciones correctas podrían reducir el tiempo de búsqueda, pero esa reducción debe medirse con usuarios y casos reales autorizados. Una falsa atribución consume tiempo de guardia; una abstención demora la orientación pero conserva la revisión humana. No hay costos FP/FN observados en dinero ni mejora de MTTR validada.

## Decisión fijada antes de la corrida

Antes del 21/11: demo asistida solo si exactitud ≥80%, afirmaciones incorrectas ≤10%, p95 ≤120 segundos, cero acciones ejecutadas y reproducción local coincidente. Si no cumple, conservar una demo honesta y reducir el alcance. **Ningún resultado sintético habilita por sí solo un piloto real**: faltan etiquetas independientes, acceso autorizado, prueba con usuarios y alcance acordado con el asesor.

## Evidencia y responsables

`results/runs/` guarda cada respuesta y consumo, configuración, revisión Git y hashes de código. `results/results.csv`, `summary.json` y `replay_verification.json` permiten auditar resultados y repetirlos. Los hashes registrados son la autoridad cuando existen cambios locales todavía sin commit. Los costos monetarios se calculan posteriormente con una tarifa pública fechada; no son una factura.

Max mantiene código y reproducción. José revisa evaluación, discrepancias y errores. Alberto coordina datos y validación con usuarios. Esta distribución fue confirmada por Max el 29/10. Las firmas de los tres integrantes y la auditoría cruzada del taller se registrarán cuando ocurran; no se anticipan.

## Fuentes del curso

- [E5 y entrega en Canvas](https://utec.instructure.com/courses/25674/assignments/349676).
- [Taller y respuesta antes del viernes a mediodía](https://utec.instructure.com/courses/25674/announcements/208885).
- [Plantilla oficial y rúbrica P4](https://drive.google.com/drive/folders/15ontIGgu9CXvzkaXZFfFpiQpC9Joi18j).
- [Datos y datasheet E4](https://drive.google.com/drive/folders/1sbyN-sh3-S6EbViWtPdALM0Nqg3-etAc).
