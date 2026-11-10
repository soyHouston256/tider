# Tider: propuesta para validar con el equipo

**Autor:** Max Houston Ramirez Martel · **Fecha:** 2026-11-08
**Documento completo (RFC):** `tider/docs/designs/tider-asesor-incidentes.md`

Antes de seguir con el diseño y el código, necesito que revisen esta propuesta. Al final hay 6 preguntas concretas. Respondan cada una con: de acuerdo, en desacuerdo (y por qué) o no sé.

---

## 1. Qué es Tider

Tider es un **asesor de incidentes para microservicios en contenedores**, pensado para funcionar en cualquier nube. Kubernetes es la plataforma principal y AWS ECS es una extensión. Lee lo que sabemos de la aplicación (Context Lake), los logs y los eventos de la plataforma, y muestra en el **mapa de servicios** qué falló y cómo repararlo.

- **El conocimiento de cada aplicación vive en el Context Lake,** no en el código.
- **El acceso a cada nube y plataforma vive en adaptadores:** logs (Cloud Logging o CloudWatch) y plataforma (Kubernetes o ECS).
- **Piloto:** Online Boutique en GKE, porque es el entorno que tenemos disponible. Ahí se hace la evaluación estadística.
- **Prueba de generalidad:** un incidente pasado y real de **SIBI (AWS ECS Fargate)** en **modo replay**: evidencia exportada y enmascarada, sin acceso a producción.

**Solo recomienda: no ejecuta nada.** Una persona decide y aplica la reparación. La remediación automática queda para una iteración futura.

## 2. Qué cambia respecto a lo que tenemos hoy

- **Un solo motor.** Hoy hay dos. Nos quedamos con el motor agéntico de la consola, que es el que trabaja sobre Online Boutique y ya es solo asesor. El grafo antiguo (OpenTelemetry Demo, con ejecutor) se archiva dentro del repositorio y sale del informe.
- **La evidencia manda.** Los logs, eventos y estado observado son la fuente de verdad. El Context Lake solo indica dónde mirar. Si el documento y la evidencia no coinciden, se muestra como hallazgo.
- **Primero un barrido fijo y después la investigación.** Primero Python lee eventos de todo el namespace y logs de todos los servicios. Después el agente profundiza donde haga falta.
- **Varias hipótesis en el mapa, no un solo culpable.** Se muestra la causa probable y las víctimas, ordenadas, con su evidencia y su cobertura. Cada servicio queda marcado como **falla confirmada**, **sano confirmado** o **sin datos**.

## 3. Roles de agentes

| Rol | ¿Usa LLM? | Qué hace |
|---|---|---|
| 1. Cartógrafo | No | Lee el Context Lake y arma el mapa previo de dónde mirar |
| 2. Recolector de evidencia | No | Hace el barrido de logs y eventos y marca el estado de cada servicio |
| 3. Investigador | **Sí** | Ordena las hipótesis y separa la causa de las víctimas, citando la evidencia |
| 4. Proponente de reparación | Catálogo primero; LLM solo si no hay coincidencia | Propone una reparación verificada o una "sugerencia no verificada" |
| 5. Juez | **Sí, con otro modelo de otra familia** + reglas fijas | Aprueba, rechaza o pide una ronda más (máximo 1) |
| 6. Reportero | No | Genera el mapa y el informe |

Criterio: un rol usa LLM solo si necesita juicio. Lo que se puede calcular, lo hace Python.

## 4. Reparaciones

- **Catálogo cerrado por modo de falla genérico.** Cada modo tiene una firma distinta en cada plataforma, más la acción sugerida, cómo verificar y el riesgo. Solo se aplica si la evidencia confirma la firma.

| Modo de falla | Firma en Kubernetes | Firma en ECS |
|---|---|---|
| Servicio sin instancias | `replicas=0`, evento ScalingReplicaSet | `desiredCount=0` o `runningCount=0` |
| Se cae al arrancar | CrashLoopBackOff | Task detenida con exit code ≠ 0 |
| Sin memoria | OOMKilled | `stoppedReason: OutOfMemoryError` |
| Configuración incorrecta | Variable de entorno cambiada en el Deployment | Nueva revisión de la task definition |

- **Sin coincidencia en el catálogo,** el LLM propone solo pasos de diagnóstico, marcados como "sugerencia no verificada". Nunca propone comandos que modifiquen el clúster.

### Cómo funciona una firma

Una firma es una regla que da una de tres respuestas:

- **Confirmada:** se ven todas las señales obligatorias, más un síntoma que lo corrobora.
- **Descartada:** basta una señal que la contradiga.
- **Sin datos:** falta la fuente para revisar alguna señal obligatoria.

Orden de precedencia (inferencia nuestra, no de la literatura): primero "sin datos" si falta una fuente obligatoria; después "descartada" si se cumple alguna señal de descarte; solo entonces "confirmada". Si una firma cumple a la vez señales de confirmación y de descarte, queda **descartada con marca de conflicto** y se reporta como hallazgo: nunca confirmada.

Lo que tomamos de la literatura (OpenRCA, RCACopilot, ITBench):

- La causa raíz es un trío: **componente + momento de inicio + razón**.
- **La causa es el componente que falla por sí mismo y antes que los demás.** Los que fallan después son víctimas.
- **Si un cambio de configuración ocurre antes del síntoma, la causa es esa configuración.**
- **El LLM solo elige entre firmas ya confirmadas, o responde "ninguna / caso no visto".** No puede confirmar algo que las reglas dejaron en "sin datos".

**Catálogo v1:**

- **A validar con ChaosForge (tienen inyector):** servicio sin instancias, configuración incorrecta, dependencia lenta y saturación de CPU. Todavía no están validadas. Cada una se probará inyectando la falla y comprobando que su firma da "confirmada" y que las demás dan "descartada" o "sin datos".
- **Declaradas, pero no validadas:** se cae al arrancar y sin memoria. No tenemos inyector para ellas, así que no tienen reparación verificada.

Las reglas concretas de cada plataforma (por ejemplo, "OOMKilled") no vienen de la bibliografía: son conocimiento de plataforma, y por eso se validan con inyección.

### Modelo común para Kubernetes y ECS

Las firmas se escriben una sola vez sobre un vocabulario propio de Tider. Cada adaptador traduce su plataforma a ese vocabulario.

| Pieza | Kubernetes | ECS |
|---|---|---|
| Servicio | Deployment | Service |
| Instancia | Pod | Task |
| Cambio (escalado, config, imagen) | ScalingReplicaSet, nueva generación | Evento de servicio, nueva revisión de la task definition |
| Evento | Eventos de Kubernetes | Eventos de servicio ECS |
| Señal (logs y métricas) | Cloud Logging o Monitoring | CloudWatch |

- Si la plataforma no entrega un dato, la firma responde "sin datos". Nunca se inventa.
- Toda observación guarda su texto original y su fuente, para que se pueda citar.
- Un pod de Kubernetes que se cae se reinicia en el mismo lugar, mientras que en ECS la task se reemplaza por otra. Por eso medimos **terminaciones con error por servicio**, no reinicios por instancia. Se cuentan desde los eventos históricos (K8s: `Killing`, `BackOff`, `OOMKilling`; ECS: tasks `STOPPED` dentro de la retención), porque el estado de los pods solo muestra el presente.
- Campos añadidos: `endpoints_listos` (K8s: direcciones listas del EndpointSlice; ECS: targets sanos del target group), que usa "servicio sin instancias", y la métrica `latencia_dependencia_p95` con su `destino`, que usa "dependencia lenta" junto a la `latencia_p95` propia.

## 5. Context Lake y chunking

Contenido: los documentos actuales más **fichas por servicio**, **runbooks** y **postmortems**. Los tres los escribimos nosotros a partir de los experimentos de ChaosForge.

| Tipo de documento | Cómo se guarda |
|---|---|
| Topología (quién depende de quién) | Como grafo, sin fragmentar |
| Ficha de servicio | 1 ficha = 1 fragmento, con plantilla fija |
| Runbook | Procedimiento completo, nunca cortado |
| Postmortem | Por sección, enlazado al documento completo |
| Catálogo de fallas | Datos estructurados, se buscan por clave |

Búsqueda **híbrida**: por palabras (BM25) y por significado, con filtros por servicio y tipo. Un documento por sí solo **no alcanza** para confirmar un diagnóstico: siempre hace falta evidencia.

## 6. Evaluación

- **Ground truth:** ChaosForge registra qué falla se inyectó. Ese registro se servirá aparte, para que Tider no pueda leerlo.
- **Reparto congelado de los 11 servicios** (más `loadgenerator` como control):
  - **Con postmortem:** cartservice, productcatalogservice, currencyservice, paymentservice, adservice.
  - **Sin postmortem (no vistos):** redis-cart, checkoutservice, shippingservice, emailservice, recommendationservice, frontend.
  - **Control:** loadgenerator y corridas sin falla, para medir falsas alarmas.
- **Pruebas:**
  - Exactitud con intervalo de Wilson.
  - McNemar pareado: Lake con postmortems contra Lake sin postmortems.
  - Tasa de diagnósticos falsos que aprueba el juez.
  - Hit@k para el chunking.
- **Tamaño de muestra** (McNemar exacto bilateral, α = 0,05, potencia 0,8; la unidad es la inyección independiente, no la repetición):
  - Para detectar una ganancia de 20 pp con 5 pp de pérdida hacen falta ~92 casos pareados; 15 pp, ~168; 10 pp, ~498 (no factible).
  - Semiancho de Wilson en el peor caso: n = 30, ±17 pp; n = 60, ±12 pp; n = 100, ±10 pp; n = 168, ±7,5 pp.
  - Si el juez no aprueba ningún diagnóstico falso, la cota superior unilateral al 95% es ≈ 9,5% con n = 30 y ≈ 4,9% con n = 60.
  - Conclusión: con la campaña factible (decenas de casos), la McNemar del Lake con y sin postmortems solo detectaría efectos grandes. Lo declaramos así.
- **Lo que podemos afirmar en esta iteración:** Tider localiza fallas de disponibilidad (`scale_zero`) en los servicios de la tienda. Las fallas sutiles (`wrong_port`, `latency`, `cpu_limit`) solo se evalúan sobre `cartservice`. Extenderlas a otros servicios es el siguiente paso.
- **Límite que reconocemos:** con `scale_zero`, el evento de Kubernetes nombra al servicio caído, así que el diagnóstico es casi trivial. La prueba difícil (causa contra víctimas) depende de las fallas sutiles.
- **Caso SIBI (replay).** Es un caso de generalidad y no entra en la estadística.
  - Se elige un incidente pasado dentro de la ventana autorizada de CloudWatch (14/04/2026–11/10/2026).
  - La custodia de SIBI lo exporta ya enmascarado, antes de que salga.
  - Tider lo analiza con un Context Lake propio de SIBI.
  - Base legal: la Carta de Autorización de Uso de Datos SIBI, firmada por la Gerente General el 11/10/2026 (cláusulas 2 y 6: validación retrospectiva, nunca en producción).
  - Por la cláusula 5, a la API del LLM solo llegan datos ya anonimizados.
  - Por la cláusula 11, las etiquetas de ground truth las validan Alberto y Jose.

## 7. Qué queda fuera de esta iteración

- Ejecutar reparaciones.
- Conexión en vivo con AWS o Azure. SIBI solo entra en replay. Los adaptadores en vivo quedan como punto de extensión, a partir de un contrato de evidencia que hay que extraer.
- Plataformas sin contenedores orquestados (máquinas virtuales, Lambda, Cloud Run).
- Pasar las herramientas a MCP: MCP sería solo una forma de transporte dentro de un adaptador.
- Fallas sutiles en servicios distintos de `cartservice`.

## 8. Preguntas para el equipo

1. **¿Están de acuerdo con que Tider sea solo asesor** y con archivar el grafo antiguo y el ejecutor?
2. **¿Están de acuerdo con los 6 roles** y con que solo el Investigador y el Juez usen LLM?
3. **¿Qué modelo usamos para el Juez?** Tiene que ser de otra familia que el del Investigador.
4. **¿Están de acuerdo con el catálogo v1 y el modelo común (sección 4)?** Son 4 firmas que validaremos con ChaosForge y 2 declaradas sin inyector.
5. **Evaluadores expertos.** La carta de SIBI (cláusula 11) ya nombra a **Alberto y Jose** como validadores de etiquetas. ¿Aceptan también calificar los diagnósticos del piloto por separado y sin ponerse de acuerdo, para medir κ? ¿Cuántos casos pueden calificar?
6. **¿Quién escribe qué?** Las 11 fichas de servicio, los runbooks y los postmortems de los 5 servicios con historial. Los postmortems deben registrar las señales tal como aparecieron, sin la conclusión escrita a posteriori.

7. **¿Qué incidente pasado de SIBI usamos para el replay?** Tiene que estar entre el 14/04/2026 y el 11/10/2026, y tener causa conocida. Sirve como candidato cualquiera de la tabla derivada de incidentes de soporte.
8. **¿SIBI guardaba los eventos de servicio de ECS?** Por ejemplo, con EventBridge hacia CloudWatch Logs. La API de ECS solo conserva los últimos 100. Si no se guardaban, el replay solo tendrá logs y métricas, y prueba el adaptador de logs, no el de plataforma.

**Plazo sugerido para responder:** ____
