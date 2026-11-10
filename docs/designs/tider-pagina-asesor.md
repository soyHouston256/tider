# Tider · Estado y visión del producto

**Equipo 04 · Proyecto Integrador UTEC** · Max Houston Ramirez Martel · 9 de noviembre de 2026

**Leyenda:** ✅ existe · 🔧 se construye en esta iteración · 🗓 plan (siguiente etapa)

## Qué es

Tider es un **asesor de incidentes para microservicios en contenedores**, pensado para funcionar en cualquier nube. Kubernetes es la plataforma principal y AWS ECS es una extensión. Lee el conocimiento de la aplicación, los logs y los eventos de la plataforma, y muestra en un mapa de servicios **qué falló, qué servicios son solo víctimas y qué reparación se sugiere**. **No ejecuta nada:** una persona decide.

- **Piloto:** Online Boutique en GKE, con fallas inyectadas por ChaosForge, nuestro laboratorio.
- **Prueba de generalidad:** un incidente real y pasado de SIBI (AWS ECS Fargate), analizado en modo replay con datos enmascarados, sin acceso a producción. Lo cubre la carta de autorización de uso de datos de SIBI del 11/10/2026.

## Blueprint del agente

| Capa | Definición |
|---|---|
| **Communication** | No conversacional. Entra un incidente (servicio, ventana de tiempo, síntoma). Sale un mapa, un informe y un JSON. En español ✅ |
| **Context** | Dominio: operación de microservicios. Rol: asesor de diagnóstico. Objetivo: identificar el componente afectado y la siguiente comprobación para una persona ✅; ampliar a causa raíz (componente, inicio, razón) y reparación verificable 🔧 |
| **Environment · Knowledge** | Context Lake: catálogo confirmado de servicios y relaciones ✅ (carga de `topologia.yaml` 🔧), más fichas por servicio, runbooks y postmortems, con búsqueda por palabras y por significado 🔧 |
| **Environment · Tools** | Herramientas de solo lectura con argumentos validados (logs, eventos, estado) ✅. Barrido fijo previo de toda la aplicación 🔧. Adaptadores por nube: GCP ✅, CloudWatch y ECS 🗓 |
| **Environment · Memoria** | Corto plazo: el estado de la investigación ✅. Largo plazo: los postmortems en el Lake 🔧 |
| **Autonomy** | **Restringida:** diagnostica y recomienda, no ejecuta ✅. La remediación queda para una versión futura |
| **Criticality** | **Qué puede salir mal:** culpar a una víctima en lugar de la causa y recomendar una reparación equivocada con seguridad. **Cómo lo controlamos:** ver la sección de controles |

## Roles de agentes

Un rol usa LLM solo si necesita juicio. Lo que se puede calcular, lo hace código.

| Rol | LLM | Función |
|---|---|---|
| Cartógrafo | No | Arma, desde el Lake, el mapa previo de dónde mirar |
| Recolector | No | Hace el barrido de evidencia y marca cada servicio como falla, sano o sin datos 🔧 |
| Investigador | Sí | Investiga con herramientas y propone un componente con citas ✅. Ordenar hipótesis y separar causa de víctimas 🔧 |
| Proponente | Catálogo primero | Propone una reparación verificada, o una "sugerencia no verificada" 🔧 |
| Juez | Sí, otro modelo | Aplica reglas fijas y su propio juicio para aprobar, rechazar o pedir otra ronda (✅ existe hoy con el mismo modelo; 🔧 pasa a otro modelo) |
| Reportero | No | Genera el informe y marca un nodo en el mapa ✅. Mapa con estado y rol de cada servicio 🔧 |

## Controles

1. **La evidencia es la fuente de verdad.** El Lake solo orienta. Un documento por sí solo nunca confirma un diagnóstico.
2. **Firmas de falla con tres veredictos:** confirmada, descartada o sin datos. La causa es el componente que falla por sí mismo y antes que los demás (OpenRCA, ICLR 2025; RCACopilot, EuroSys 2024; ITBench, 2025) 🔧
3. **Catálogo v1:** 4 firmas que se validarán con inyección (servicio sin instancias, configuración incorrecta, dependencia lenta, saturación de CPU) y 2 declaradas sin validar 🔧
4. **Tider no ejecuta nada** ✅. **Filtro que impide recomendar comandos que modifiquen el sistema** 🔧 (hoy la recomendación es texto libre). Los datos sensibles se enmascaran ✅. A un LLM externo solo llegan datos de SIBI ya anonimizados.

## Chunking

Cada tipo de documento se fragmenta según la pregunta que responde:
- **Topología:** se guarda como grafo, sin fragmentar.
- **Fichas por servicio:** una ficha completa por fragmento.
- **Runbooks:** cada procedimiento entero, sin cortarlo.
- **Postmortems:** por sección, enlazada al documento completo.
- **Catálogo:** datos estructurados.

Una medición del 6/11, con una versión anterior del buscador, dio a la búsqueda por palabras 15/16 aciertos contra 8/16 de la semántica; debe repetirse con el código actual. La búsqueda será híbrida y se validará con Hit@k 🔧

## Evaluación

- **Ground truth:** ChaosForge registra la falla inyectada. Ese registro se aísla para que Tider no pueda leerlo 🔧
- **Reparto congelado** de los 11 servicios: 5 con postmortem, 6 nunca vistos y 1 de control, para medir falsas alarmas.
- **Pruebas:** exactitud con intervalo de Wilson; McNemar pareado para comparar el Lake con y sin postmortems; tasa de diagnósticos falsos que aprueba el juez; acuerdo entre dos evaluadores (κ) 🗓
- **Tamaño de muestra:** con decenas de casos (Wilson ±17 pp con n = 30), la McNemar solo detectaría efectos grandes; una ganancia de 20 pp pide ~92 casos pareados y una de 15 pp, ~168.
- **Lo que podremos afirmar:** Tider localiza fallas de disponibilidad en los servicios de la tienda. Las fallas sutiles solo se evalúan sobre `cartservice`.
- **Límite que reconocemos:** las fallas de disponibilidad son casi triviales, porque el evento de la plataforma nombra al servicio. La prueba exigente es separar la causa de las víctimas en las fallas sutiles.

## Siguientes pasos

1. Construir el barrido, el verificador de firmas, el catálogo v1, el juez con otro modelo y el aislamiento del ground truth.
2. Escribir las fichas, los runbooks y los postmortems, y ejecutar la campaña de evaluación.
3. Hacer el replay de SIBI y extender las fallas sutiles a otros servicios.
