# Medir la recuperación y el diagnóstico de Tider

Desde la raíz del repositorio, este comando recalcula cada acierto, contrasta los resultados con la referencia del 6 de noviembre y guarda el desglose por pregunta y ventana. Solo lee datos locales y ejecuta el control local de severidades. Un cambio en el informe devuelve un código de error.

```bash
.venv/bin/python -m eval.quality --verify --out out/quality-v1.json
```

El [protocolo](PROTOCOL.md) fija antes de la medición los pasajes pertinentes, las etiquetas de servicio y mecanismo, los registros exigidos y las métricas. El [manifiesto](manifest.json) verifica las huellas del material congelado. Las preguntas, ventanas y etiquetas están en archivos separados. El capturador del modelo recibe los registros de la ventana y un catálogo común.

**Para repetir las búsquedas con el modelo local de Chroma**, elige una ruta nueva. La primera ejecución de Chroma puede descargar los pesos de embeddings. El informe compara también las huellas de las capturas, por lo que permite detectar diferencias de versiones, orden o archivos del modelo.

```bash
.venv/bin/python -m eval.quality.retrieve --out out/mi-ranking.json
.venv/bin/python -m eval.quality --retrieval out/mi-ranking.json --out out/mi-reporte.json
```

**Para volver a investigar las ocho ventanas**, el comando siguiente usa el modelo y la credencial de Anthropic configurados, realiza llamadas facturables y exige un directorio nuevo. Carga una topología sintética y los cuatro runbooks, sin acceder al clúster. Se conserva un intento por ventana, incluidas las recuperaciones internas del motor. El tiempo y las respuestas pueden cambiar entre corridas.

```bash
.venv/bin/python -m eval.quality.live --out out/mi-corrida
.venv/bin/python -m eval.quality --runs out/mi-corrida --out out/mi-corrida-informe.json
```

El detalle incluye los fragmentos devueltos por cada buscador, los registros disponibles y citados por caso, la conclusión publicada, los errores y el consumo de tokens. Los archivos de sesión preservan las consultas y las respuestas emitidas. La puntuación de evidencia compara los registros exigidos con lo que la herramienta presentó en las consultas citadas. La calidad semántica de la explicación requiere revisión independiente. [Informe reproducible por caso](recordings/summary-v1.json)

La comparación posterior usa seis ventanas y 16 preguntas reservadas y se vuelve a puntuar sin coste con `eval/quality/followup/autoresearch.sh`. Incluye ambas versiones, sus incertidumbres y el control en el que el agente atribuyó una causa incorrecta. [Resultados comparados](followup/summary.json).
