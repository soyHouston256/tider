# Estado del agente · 17/10/2026

## Disponible localmente

- Consola web en `/`, Swagger en `/docs` y API de diagnóstico.
- Un único motor agéntico (`src/tider/console/agentic.py`), solo asesor: investiga,
  contrasta la evidencia con un juez y propone; no ejecuta cambios.
- Modo por reglas como línea base sin LLM: investigador → juez → decisor → reporte.
- Cuatro escenarios sintéticos de Online Boutique.
- El grafo anterior con ejecutor (dominio OpenTelemetry Demo) está archivado desde el
  09/11/2026: [archivo de remediación](archive/remediacion/README.md).
- Resultados con evidencia, auditoría, descarga JSON e historial de 50 ejecuciones.
- Modo observación: la consola no tiene ruta de ejecución.
- Conector Cloud Logging limitado a `tider-ops / chaosforge-lab / boutique`, preparado
  para credenciales ADC. Pruebas automáticas con cliente simulado.
- Adaptador opcional con Anthropic para el motor agéntico, activación explícita.
- Arranque nativo y configuración Docker de la misma consola.

## Pendiente: elección del proveedor LLM

Registrado el 20/10/2026. Anthropic se conserva como integración opcional
provisional; el proveedor y el modelo definitivos pueden cambiar. La consola
mantiene `LLM_PROVIDER=none` como valor predeterminado.

- [ ] Confirmar proveedor y modelo antes de la evaluación con un modelo real.
- [ ] Al decidirlo, revisar el adaptador en `src/tider/llm.py`, su selección en
  `src/tider/console/analysis.py`, la configuración en `src/tider/console/settings.py`
  y `.env.example`, las dependencias y las pruebas correspondientes.
- [ ] Actualizar conjuntamente el README, las guías y el blueprint vigente
  `docs/designs/tider-blueprint.drawio` en las capas que mencionen al proveedor.
  El atlas anterior (`docs/archive/remediacion/atlas/`) está archivado y no se actualiza.

Cerrar este pendiente cuando la elección quede registrada y código, configuración
y diagramas identifiquen al mismo proveedor y modelo.

## Continuación

1. Consultar una ventana conocida del laboratorio GKE y contrastar los logs con la consola GCP.
2. Incorporar métricas y trazas reales de Cloud Monitoring y Cloud Trace.
3. Registrar baseline, falla y recuperación de `cartservice` desde ChaosForge;
   separar la etiqueta verdadera de la evidencia que consume el agente.
4. Evaluar el modelo real frente al baseline: causa identificada, tiempo de
   diagnóstico, evidencia citada y costos observados.
5. Completar conectores y persistencia antes de desplegar el agente en GKE.

El laboratorio ChaosForge ya cuenta con despliegue documentado. El agente se prueba
localmente; no necesita recrear ese laboratorio ni ejecutar el Terraform anterior.
La evaluación de agentes amplía el trabajo técnico sin cambiar los resultados
históricos ni las hipótesis del entregable E4.
