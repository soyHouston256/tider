# Tider: primera lectura real y ajuste del baseline

Fecha: 24 de octubre de 2026, hora Lima.

## Resultado

Se verificó que las credenciales ADC del entorno de Tider existen y pueden
renovarse, sin imprimir tokens ni abrir archivos privados para inspección manual.
El conector realizó consultas de lectura a Cloud Logging del laboratorio
`tider-ops / chaosforge-lab / us-central1 / boutique`.

Se utilizó el experimento A ya existente. La consulta inicial estuvo acotada a
2026-10-25 00:47:24–00:48:24 UTC. La comprobación posterior por API y consola usó
24/10/2026 19:47–19:49, hora Lima, seleccionando frontend y Logs de GKE.
No se realizaron nuevas inyecciones, cambios cloud, despliegues, commits ni pushes.

## Cambios locales

- El adaptador Cloud Logging ahora combina error, message y msg, elimina valores
  duplicados y aplica el enmascarado. Prioriza el detalle de error ante el límite
  existente de 600 caracteres. Los mensajes largos todavía pueden truncarse.
- Antes, seleccionar solo message descartaba detalles de conexión rechazada
  presentes en error. Tras el ajuste, una consulta devolvió 98 señales, de las
  cuales 23 conservaban ese detalle.
- El baseline admite el patrón de fallo al recuperar el carrito mediante RPC,
  código Unavailable y conexión rechazada, conservando las restricciones de
  severidad y servicio emisor.
- La hipótesis del carrito indica inaccesibilidad desde el servicio que reporta
  el error; no afirma que los logs demuestren escalado a cero ni una causa física.

Archivos de código modificados:
- src/tider/console/providers/cloud_logging.py
- src/tider/console/baseline.py
- tests/console/test_console.py
- tests/console/test_rca.py

Se preservaron los cambios de documentación que ya existían en el repositorio.

## Validación

- Tras el ajuste del conector: 24 pruebas de consola aprobadas.
- Tras el ajuste del baseline: suite completa, 69 pruebas aprobadas.
- Ruff sobre archivos modificados y git diff --check: correctos.
- Controles negativos del patrón: operación de pago, severidad INFO, código
  distinto, ausencia de conexión rechazada y emisor fuera del conjunto permitido.
- API local contra logs reales: HTTP 200, 97 señales, componente cartservice,
  hipótesis de inaccesibilidad y puntuación heurística 0,7.
- El usuario ejecutó el análisis y confirmó que la consola muestra:
  «Cart Service no es accesible desde el servicio que reporta el error».

La consola quedó levantada localmente en http://127.0.0.1:8080, en observación,
con GCP habilitado y LLM desactivado. No asumir que el proceso seguirá activo en
otra sesión. Su historial es temporal y se reinició al recargar el servidor.

## Límites y siguiente paso

Este caso se usó para ajustar la regla: es validación de integración y regresión,
no una evaluación independiente ni evidencia de generalización. La puntuación
0,7 no es una probabilidad calibrada. No hubo uso de modelo externo ni evaluación
comparativa con LLM. Solo se consultaron logs, sin métricas ni trazas integradas.
La consulta devuelve hasta 100 entradas recientes; no representa necesariamente
toda la ventana solicitada.

Siguiente paso pendiente: conservar resultados reproducibles y comprobar el
baseline con otro caso independiente y controles de operación normal. Cualquier
nueva inyección la ejecuta el usuario. Proveedor y modelo LLM siguen pendientes.

El usuario pidió dejar este avance registrado y cerrar aquí, sin iniciar otro
experimento.
