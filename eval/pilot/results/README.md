# Resultados del piloto en el laboratorio

Salidas de `eval.pilot.runner --validate-signatures` con fallas reales: ChaosForge las inyectó en
la Online Boutique del laboratorio (GKE) y Tider analizó cada caso en modo reglas. Los archivos
son los que escribió el orquestador en `out/runs/`, copiados sin editar.

| Carpeta | Casos | Cuándo (hora de Lima) | Código |
|---|---|---|---|
| `validacion-entrega/` | V1, V2, V3 y V5, seguidos | 19/11/2026, 19:19–20:10 | `772b496` |
| `ensayo-validacion-8/` | V4 (saturación de CPU) | 19/11/2026, 18:32–18:45 | `b01d73f` |

Entre `b01d73f` y `772b496` solo cambia documentación. Después de `772b496` el código cambió en un
solo punto, la nota de fuentes de la consola (`api.py` y `app.js`); el pipeline es el mismo. Las
horas de las trazas están en UTC, por eso llevan fecha 20/11.

## Resultado

| Caso | Falla inyectada | ChaosForge | Firma confirmada por Tider | Víctimas | Cobertura | Análisis |
|---|---|---|---|---|---|---|
| V1 | `productcatalogservice` a 0 réplicas, 60 s | `completed` | `servicio-sin-instancias@productcatalogservice` | `frontend`, `recommendationservice` | 0,82 | 9,8 s |
| V2 | `cartservice` con Redis en el puerto 6380, 120 s | `effect_observed` | `configuracion-incorrecta@cartservice` | ninguna | 0,82 | 9,9 s |
| V3 | 300 ± 50 ms entre `cartservice` y Redis, 120 s | `effect_observed` | `dependencia-lenta@cartservice->redis-cart` | `cartservice` | 1,00 | 10,8 s |
| V5 | ninguna (control), 120 s | — | ninguna | — | 1,00 | 11,3 s |
| V4 | límite de CPU de `cartservice` a 50m, 120 s | `effect_not_observed` | `saturacion-cpu@cartservice` | `frontend` | 1,00 | 10,6 s |

- En los cuatro casos de `validacion-entrega` Tider confirmó la firma esperada y ninguna otra: de
  52 evaluaciones de firma por entidad, 3 quedaron confirmadas, 31 descartadas y 18 sin datos.
- En esos cuatro casos no falló ninguna fuente de evidencia. Cada análisis leyó entre 597 y 699
  señales (logs de Cloud Logging y medidas del observador) y no llamó a ningún modelo.
- En V3 la mediana de latencia hacia Redis pasó de unos 30 ms a 288–344 ms durante la inyección,
  y la de `/cart`, de 32 ms a 338–372 ms.
- `gate.json` da `go: false` porque falta V4. V4 queda `excluido` (`inyeccion_no_acreditada`):
  ChaosForge no llegó a medir el efecto dentro de su plazo de preparación. No cuenta como validado.

## Límites de esta evidencia

- Hay un caso por mecanismo. Sirve para comprobar que cada firma se confirma con su falla y no
  con las demás; no mide exactitud. La campaña de 70 casos del protocolo no se corrió.
- Solo se probó el modo reglas (`brazo: reglas`, `llamadas` vacío). Los modelos que figuran en
  `settings` son la configuración del entorno y no se usaron.
- El análisis es posterior al incidente y conoce su inicio: la solicitud va desde 5 min antes de
  lanzar la inyección hasta 5 min después de la restauración, y `t0` es el momento en que se
  lanza (`eval/pilot/protocol.yaml`). En operación ese dato saldría de la alerta. La hora de inicio
  que informa Tider se alinea con `t0`, así que no es una medición independiente. La solicitud no
  dice qué servicio ni qué mecanismo falló.
- En V2 la causa quedó identificada, pero 32 errores de `frontend` quedaron sin atribuir y no
  figura como víctima.
- También en V2, `cartservice` cumplió los dos obligatorios de `saturacion-cpu` al reiniciarse
  (throttling del pod nuevo y un tramo lento de `/cart` seguido de un hueco de datos). La firma
  quedó DESCARTADA porque faltó el corroborante, un cambio de límites.
- La cobertura de 0,82 en V1 y V2 significa que la lectura de logs de 2 de los 11 servicios de la
  tienda se truncó por cuota. El mínimo para no marcar el análisis como incompleto es 0,80.
- En el control (V5) hubo ruido de fondo: advertencias de `frontend` por anuncios que no llegaron
  a tiempo y del proxy por conexiones cerradas.
- En el laboratorio `cartservice` llega a Redis a través de `chaosforge-proxy`, que hace falta para
  inyectar latencia. Tider lo trata como componente auxiliar y lo lista en `discrepancias`.
- `scenario: redis_down` en `entradas.request` es el valor por defecto del esquema de solicitud
  (escenarios sintéticos de la demostración); el pipeline v2 no lo lee.

## Qué hay en cada carpeta

- `gate.json`: matriz de confusión y resultado por caso.
- `casos.jsonl`: experimento de ChaosForge, horas de inyección y restauración, y acreditación. El
  campo `trace` apunta a la carpeta original en `out/runs/`.
- `V*.json`: traza del caso. `entradas.evidencia_congelada` es la evidencia que leyó Tider;
  `corridas[].analysis.investigation.firmas`, el veredicto de cada firma; `corridas[].analysis`,
  el informe.
- `_spec/` y `protocol.lock`: la solicitud que recibió Tider y el hash del protocolo.
