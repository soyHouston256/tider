# Pruebas del agente

Ejecutar desde `project/tider`, después de `make setup`:

```bash
make test
make lint
```

La suite usa herramientas, clientes y respuestas simulados. No requiere GCP, AWS,
Kubernetes, claves de modelos ni un navegador abierto. Las salidas operativas de
prueba se escriben en directorios temporales de pytest.

## Cobertura

| Grupo | Qué comprueba |
|---|---|
| `tests/test_units.py` | Política, límites, herramientas, validación y almacenamiento |
| `tests/test_e2e.py` | Grafo, rondas de revisión, acciones propuestas, aprendizaje y escalamiento |
| `tests/test_api.py` | Autenticación y comportamiento de la API Alertmanager |
| `tests/test_observation.py` | Aislamiento de acciones para runbook, PR y escalamiento |
| `tests/console/test_console.py` | Cuatro escenarios, HTTP, archivos estáticos, filtro GCP, errores y enmascarado |
| `tests/console/test_rca.py` | Diagnóstico, servicio sin señales y ventana temporal |
| `tests/console/test_service.py` | Historial aislado, concurrencia y referencias de decisiones |

## Comprobación manual en la consola

1. Ejecutar `make run` y abrir http://localhost:8080.
2. Elegir **Redis no disponible**: identifica `redis-cart`, cuatro señales y una
   propuesta de revisión humana. Abrir **Decisiones y sustento**; los IDs enlazan a
   la tabla de evidencia. La verificación aparece omitida porque no hubo una acción.
3. Elegir **Cart Service sin endpoints**: identifica `cartservice`, con tres señales.
4. Elegir **Operación normal** y **Sin telemetría**: no identifica una causa raíz;
   el recorrido registra la segunda ronda y la solicitud de más evidencia.
5. Elegir una ejecución anterior en el historial y comprobar que recupera su
   resultado. **Descargar JSON** conserva auditoría y decisiones del mismo análisis.

El identificador del escenario selecciona datos de entrada; el diagnóstico se
obtiene del contenido de las señales. Una prueba sustituye la evidencia de un caso
para comprobar que el motor no usa su etiqueta como respuesta.

## API

Con el servidor abierto:

```bash
curl -fsS http://localhost:8080/health
curl -fsS http://localhost:8080/v1/lab/config
curl -fsS -H 'Content-Type: application/json' \
  --data-binary @examples/analyze.json http://localhost:8080/v1/incidents/analyze
```

El ejemplo tiene fechas fijas adecuadas para la simulación. Para GCP deben usarse
fechas del experimento y habilitar la fuente en el servidor.

## Evaluación del motor

```bash
.venv/bin/python eval/mock_local.py --out /tmp/tider-mock-evaluation
```

Ejecuta 30 combinaciones de seis escenarios y cinco condiciones de control.
El arnés con modelo externo está en `eval/harness.py`; su ejecución es independiente
de la suite local. Ver [engine.md](engine.md) y [roadmap.md](roadmap.md).

## Distribución

`uv build --wheel` empaqueta código y recursos de la consola. La imagen Docker
usa la misma configuración y lock. `docker compose --profile console config --quiet`
valida la configuración; para verificar la imagen y su arranque se necesita ejecutar
el build y comprobar `/health` en el contenedor.

## Verificación de la reorganización · 17/10/2026

- 63 pruebas de pytest aprobadas; lint y formato de 57 archivos Python correctos.
- 30/30 controles del arnés local aprobados; 0 acciones reales y 0 intentos externos.
- Paquete wheel probado fuera del repositorio: grafo, política, contexto, escenarios
  y archivos de la consola disponibles sin rutas al workspace.
- Imagen Docker construida; servidor, endpoint de análisis y recursos estáticos
  comprobados en un contenedor temporal con usuario sin privilegios.
- Cuatro escenarios comprobados en el navegador; 8 pasos en los casos con causa
  y 10 al requerir una segunda ronda. Historial y presentación sin errores de consola.

Estas comprobaciones se ejecutaron con evidencia y respuestas locales. Las pruebas
con telemetría del laboratorio y un modelo externo se describen en el roadmap.
