# Brief de concepto · Tider como asesor de incidentes (modo BRAINSTORM, ronda 2)

Estado: ronda 2 + decisiones del autor (2026-11-08; decisiones 21 y 22 el 2026-11-09)

* **Autor:** Max Houston Ramirez Martel
* **Fecha:** 2026-11-08
* **Ronda:** 2. Reemplaza al brief de la ronda 1. Evalúa la hipótesis v2, que integra las 16 decisiones de `_auditoria_consolidada.md` y los 6 roles de `roles_agentes.md`. Después de la revisión, el autor tomó las decisiones 17 (aislar el ground truth), 18 (alcance de la evaluación, opción c), 19 (cambios de redacción) y 20 (alcance del producto, opción a, SIBI en replay). El 2026-11-09 aceptó la 21 (firmas operativas y catálogo v1) y la 22 (modelo común de servicio e instancia). Esta versión las incorpora.
* **Vocabulario de estados (decisión 19):**
  * Componentes: **existe** (está en el código hoy) · **se construye** (entra en la etapa 1) · **plan** (etapa 2 o posterior).
  * Decisiones: **aceptada** · **propuesta** · **pendiente**.
  * Objeciones: **resuelta** · **parcial** · **abierta**.
  * Nodos del grafo (salida de Tider): falla confirmada · sano confirmado · sin datos.
* **Insumos:** `_auditoria_consolidada.md` (fuente principal), `roles_agentes.md`, `_contexto_motor.md`, `_contexto_consola_eval_docs.md`, `_contexto_chaosforge_lake.md` y `_transcripcion.md` (todos en esta carpeta), más el código de `tider/` y `chaosforge/`.
* **Rutas:** las citas `ruta:línea` son relativas a `/Users/maxhoustonramirezmartel/code/utec/5/integrador/project/code/`. Las citas `_archivo.md:línea` apuntan a los informes de esta carpeta. "Decisión N" significa la decisión N de `_auditoria_consolidada.md`.
* **Severidad:**
  * **Bloqueante:** impide entregar o invalida la evaluación.
  * **Mayor:** hay que resolverlo o declararlo en el informe.
  * **Menor:** detalle de redacción o de higiene.

## Estado de los revisores

| Revisor | Lente | Estado |
|---|---|---|
| `egm-design` | Arquitecto escéptico | completado |
| `egm-codebase-details` | Exactitud contra el código | completado |
| `egm-zoom-out` | Alcance y simplicidad | completado |
| `egm-comprehension` | Lector sin contexto | completado |
| `egm-implementation-readiness` | Preparación para implementar | completado |
| `egm-structural` | Estructura de documentos | completado |
| `egm-inventive-catalyst` | Contradicciones e invención | completado |

---

## 1. Resumen

**Visión del producto (decisión 20, aceptada).** Tider es un **asesor de incidentes para microservicios en contenedores orquestados**, agnóstico de nube. Kubernetes es la plataforma principal y AWS ECS es una extensión.

* **El conocimiento de cada aplicación vive en el Context Lake,** no en el código.
* **El acceso a cada nube y plataforma vive en adaptadores:** logs (Cloud Logging o CloudWatch) y plataforma (Kubernetes o ECS). El razonamiento trabaja sobre "servicio" e "instancia".
* **Piloto:** Online Boutique en GKE, porque es el entorno disponible. Ahí se hace la evaluación estadística.
* **Prueba de generalidad:** un incidente real pasado de **SIBI (AWS ECS Fargate, sin Kubernetes)** en **modo replay**: evidencia exportada y enmascarada en origen, un Context Lake propio de SIBI y sin acceso a producción. Queda **fuera de la estadística**.
* Autonomía: solo asesor (decisión 1).

El concepto v2 se sostiene y los siete revisores aceptan la dirección:

* un solo motor (el `AgenticEngine`);
* autonomía de solo asesor;
* evidencia como fuente de verdad y el Lake como mapa previo;
* catálogo cerrado con respaldo LLM limitado a diagnóstico;
* seis roles, dos de ellos LLM.

Las decisiones de la ronda 2 resuelven bien las contradicciones de concepto. El barrido fijo antes de la investigación separa en el tiempo la evidencia y el Lake. El reparto historial / no vistos / control ataca la fuga por postmortems. El chunking por tipo de documento une el fragmento con la pregunta que responde.

Los problemas que quedan son de otro tipo:

1. **Varias decisiones describen como existente algo que el código no tiene.** El contrato `EvidenceProvider` no es un puerto. El juez de otro modelo solo existe en el código que se archiva. El barrido no lee todo el namespace. No hay BM25 ni filtros por metadatos. Si el informe de la etapa 0 no separa lo que existe de lo que se construye o es plan, repite el error de la auditoría: la documentación describiría un sistema distinto del que se muestra. *Decisión 19: cada componente lleva la etiqueta existe / se construye / plan (tabla en la sección 5.2).*
2. **El diseño de evaluación tiene un efecto techo y factores confundidos.** Todo lo "no visto" es `scale_zero`. `scale_zero` emite un evento que lo delata. El filtro de caso válido se cumple siempre. Las consultas de Hit@k contienen el nombre del servicio que falló. Así, la McNemar del Lake, la tasa de falsa aprobación del juez y el Hit@k pueden salir sin poder estadístico o triviales. *Decisión 18: el informe acota la afirmación a lo que se evalúa y declara la extensión como siguiente paso (ver N2).*
3. **Objeciones de la ronda 1:** la decisión 17 aísla el ground truth (`/api/evidence`) y la decisión 19 quita "confianza" de la decisión 2. La decisión 21 da la definición operativa de "firma" (sección 2.7), y la decisión 22, el modelo común de servicio e instancia sobre el que se escriben las firmas (sección 2.8). Faltan implementarlas y validarlas.
4. **Archivar fuera de `tider/` rompe código.** La consola importa el grafo al arrancar, y el benchmark de chunking (p=0,016; medido el 6/11 con una versión anterior del buscador; debe volver a medirse con el código actual) lee `docs/runbooks`. *Decisión 19: se archiva dentro del repositorio. Los pasos previos de N4 siguen pendientes.*

La recomendación central se mantiene. La reunión es informativa, así que basta la etapa 0. Cada componente del informe lleva una etiqueta de estado. Los cambios de redacción sin código fueron aceptados por el autor (decisión 19) y este brief ya los aplica (sección 5.5).

---

## 2. Análisis

### 2.1 Estado de objeciones de la ronda 1

**Conteo de las 17 objeciones principales (B1–B5 y M1–M12), después de las decisiones 17–22:**

* **3 resueltas** (M2 en concepto; B2 y B1 por decisión, con implementación y validación pendientes)
* **10 parciales**
* **4 abiertas**

De los 6 menores: **2 parciales** y **4 abiertos**.

Antes de las decisiones del autor el conteo era 1 / 8 / 8, y en los menores 1 / 5. Cambian B2 (abierta → resuelta por decisión), B4 (abierta → parcial), M5 (abierta → parcial, decisión 20), m2 (abierto → parcial) y, con la decisión 21, B1 (abierta → resuelta por decisión). Ninguna objeción de la tabla trata el contrato servicio/instancia; la decisión 22 cierra ese pendiente de la sección 2.6.

| ID | Objeción (ronda 1) | Estado | Qué cambió y qué falta |
|---|---|---|---|
| B1 | "Firma" sin definición operativa | **Resuelta** (decisión 21; implementación y validación pendientes) | La decisión 21, aceptada el 2026-11-09, fija el esquema de firma (sección 2.7): veredicto CONFIRMADA / DESCARTADA / SIN_DATOS, salida como trío componente + t_inicio + razón, reglas de raíz frente a síntoma, ventana de recolección y juez por coincidencia exacta. Fija también el catálogo v1 (4 firmas a validar con ChaosForge y 2 declaradas). Las firmas se escriben sobre el modelo común de la decisión 22. Falta: los predicados concretos de K8s y ECS son inferencia y se validan inyectando y retirando cada falla; el enum `mechanism` sigue igual al del inyector (`tider/src/tider/console/agentic.py:36,108`) y no hay verificador de firmas en el código. |
| B2 | Evaluación circular y fuga de ground truth | **Resuelta** (decisión; implementación pendiente) | La decisión 17, aceptada, sirve `/api/evidence` y `/api/state` desde un proceso o puerto distinto del que lee Tider. Hoy siguen en el mismo puerto que `/api/observations` (`chaosforge/admin/server.py:51,69,78`): falta implementarlo y agregar una prueba de no acceso (etapa 1). La decisión 19 organiza el catálogo por modo de falla genérico de Kubernetes, con el mecanismo de ChaosForge solo como etiqueta de evaluación (N14). La decisión 13 cubre la fuga por postmortems. |
| B3 | Retirar el grafo rompe código | **Parcial** (peor de lo estimado) | Se decide conservar los módulos compartidos. La decisión 19 archiva dentro del repositorio. Pero `console/api.py:14` importa `LabEngine` al cargar, y `analysis.py:6-12` importa `tider.graph`, `tider.agents.deps`, `tider.decision.policy` y `tider.lake.store`. Archivar el grafo rompe el arranque de la consola incluso con `LLM_PROVIDER=anthropic`. El baseline de reglas de E5 es `console/baseline.py` (`eval/course_e5.py:18`) y sobrevive sin el grafo. |
| B4 | "Confianza" y "cobertura" sin definir | **Parcial** | La decisión 19 quita "confianza" de la decisión 2: las hipótesis se presentan por orden y cobertura. Falta una sola definición de cobertura, que hoy tiene dos (ver N13). El código mantiene `confidence=None` (`agentic.py:439`). |
| B5 | Diseño estadístico sin fijar | **Parcial** | Se agregan el reparto y el filtro de caso válido (decisión 15). La decisión 19 expresa el reparto como pares servicio×mecanismo y la decisión 18 acota la afirmación. Faltan la unidad y la etiqueta, la potencia, la p95 por caso y el congelamiento en `22698d1`. El filtro nuevo no filtra nada (ver N2). |
| M1 | "Sano confirmado" sin fuente | **Parcial** | La decisión 3 fija los tres estados. Pero el barrido de la decisión 9 solo lee errores y eventos, así que no puede producir evidencia positiva (ver N8). `service_state` solo da el estado actual (`investigation_tools.py:262`). |
| M2 | Estado y rol son dos ejes | **Resuelta** (concepto) | El Reportero entrega estado + rol causal por nodo. En código falta el campo `role`, y falta el procedimiento para etiquetar víctimas en el ground truth. |
| M3 | Circularidad del Lake | **Parcial** | Resuelta en el papel con la decisión 9. Abierta en el código: los logs se filtran por `k8s-pod/app` del catálogo confirmado (`cloud_logging.py:33-36`) y los eventos por una regex de nombres del catálogo (`kubernetes_events.py:19,28,42-44`). `chaosforge-proxy` nunca puede aparecer como discrepancia. |
| M4 | Sugerencia no verificada sin control | **Parcial** | `roles_agentes.md:49` lista los verbos prohibidos. Falta el esquema enumerado y la prueba. "Verificada" sigue siendo ambiguo, y el filtro choca con la acción del catálogo (ver N12). |
| M5 | Protocolo de κ | **Parcial** (no resuelta) | La decisión 5 lo dejaba pendiente. Con la decisión 20, la cláusula 11 de la Carta de Autorización SIBI nombra a Alberto y Jose como únicos validadores de etiquetas, y quedan como **candidatos** a evaluadores κ. Falta que acepten calificar los diagnósticos del piloto por separado y sin ponerse de acuerdo, fijar cuántos casos y el protocolo. Son integrantes del equipo, no evaluadores externos. La métrica de la decisión 4 que depende de κ sigue condicionada a la decisión 5. |
| M6 | Chunking sin decidir | **Parcial** | La decisión 12 fija la estrategia por tipo. Choca con los límites del Lake actual y su validación tiene fugas (ver N3 y N9). |
| M7 | Roles descritos de tres formas | **Parcial** | `roles_agentes.md` da una tabla única. Quedan contradicciones: el orden Proponente / Juez, el Cartógrafo antes del Recolector, 2 o 3 usos del LLM, y quién recolecta la evidencia adaptativa (ver N12). |
| M8 | Capas del blueprint y vocabulario del curso | **Abierta** | Ninguna decisión lo trata, y es el núcleo de la etapa 0. |
| M9 | El agente no deja traza | **Abierta** | El tracing sigue apagado (`console/__main__.py:22-23`). No se registran el modelo del juez, el SHA del prompt, los hashes del Lake ni las llamadas a `context_search`. Sin eso no se pueden calcular la métrica del juez ni la McNemar del Lake. |
| M10 | Cambio de esquema de salida | **Abierta** | No hay decisión sobre `ranked_hypotheses[]`. Puede quedar para la etapa 2. |
| M11 | Economía de la campaña | **Parcial** | `FrozenTools` existe (`eval/course_e5.py:115`). Pero el barrido invalida los fixtures, y la campaña creció (ver N15). |
| M12 | Cifras copiadas a mano | **Abierta** | Ninguna decisión lo trata. Las cifras van a divergir más cuando se retiren las pruebas del grafo. |
| — | **Menores** | | |
| m1 | Glosario | Abierto | Faltan Context Lake, ChaosForge, Online Boutique, GKE, RBAC, C09, E5, H6, IDs `S01…` y "etapa 0". |
| m2 | Nombre "catálogo" | Parcial | La decisión 19 fija "catálogo de modos de falla", organizado por modo de falla genérico de Kubernetes. Falta renombrar el "Catálogo confirmado" de la consola. Hasta ahora había tres formas: "catálogo de modos de falla" (decisión 4), "catálogo de fallas" (decisión 12) y "Catálogo confirmado", que en la consola es la topología. |
| m3 | Ejemplo concreto de discrepancia | Abierto | `chaosforge-proxy` no sirve como ejemplo hasta que se corrija M3. |
| m4 | Pasada terminológica OTel | Parcial | El archivo saca a `cart`/`valkey-cart` del informe. Pero el corpus del benchmark sigue siendo OTel, y `tider/src/tider/state.py` conserva `otel-demo` como valor por defecto. |
| m5 | Versión de Online Boutique | Abierto | |
| m6 | Línea base de reinicios de fondo | Abierto, agravado | currency (40) y payment (36) quedan en el historial que alimenta los postmortems. |

**Objeciones nuevas de la ronda 2 (sección 2.2) que tocan las decisiones 17–19.** Las que no aparecen aquí (N3, N5–N12, N15) siguen abiertas.

| ID | Objeción | Estado | Qué cambió y qué falta |
|---|---|---|---|
| N1 | La etapa 0 describe como hecho lo que es plan | **Parcial** | La decisión 19 adopta la etiqueta existe / se construye / plan, el vocabulario de estados único y la decisión 10 como "contrato a extraer". Falta llevar las etiquetas al informe y crear el registro único con "depende de" en `docs/decisions.md`. |
| N2 | Reparto con efecto techo de `scale_zero` | **Resuelta** (acotamiento de alcance) | La decisión 18 limita la afirmación a lo que se evalúa, reconoce que `scale_zero` es casi trivial con barrido de eventos y declara como siguiente paso extender las fallas sutiles a otros servicios. La decisión 19 expresa el reparto como pares servicio×mecanismo. El filtro de caso válido no vacío y la McNemar descriptiva con menos de 10 pares discordantes quedan como requisitos del plan de campaña. |
| N4 | Archivar fuera de `tider/` rompe código | **Parcial** | La decisión 19 archiva dentro del repositorio, con un puntero en `project/documentation/archivo/`. Faltan los pasos previos: cortar la importación de `LabEngine`, congelar el corpus del benchmark y mover las pruebas del grafo. |
| N13 | Colisiones de vocabulario | **Parcial** | La decisión 19 quita "confianza", fija "catálogo de modos de falla" y un vocabulario de estados único. Siguen cobertura, runbook, revisión, mapa, control y la numeración de decisiones. |
| N14 | Catálogo nombrado por el mecanismo del inyector | **Resuelta** (decisión) | La decisión 19 organiza el catálogo por modo de falla genérico de Kubernetes. El mecanismo de ChaosForge queda como etiqueta de evaluación. |

### 2.2 Objeciones nuevas de la ronda 2

#### Bloqueantes

**N1. La etapa 0 describiría como hecho lo que es plan.** (zoom-out, structural, codebase-details, comprehension, design)
* La decisión 7 dice que basta la etapa 0. Pero las decisiones 8, 9, 10, 12 y 16 describen piezas que no existen:
  * un juez de otro modelo en la consola;
  * un barrido de todo el namespace;
  * un puerto `EvidenceProvider`;
  * chunking por tipo con metadatos;
  * BM25;
  * un benchmark de 4 variantes.
* La decisión 10 dice que el puerto "ya existe con mock, cloud_logging y logging_mcp". Es falso:
  * `EvidenceProvider` es una clase concreta con `if` (`tider/src/tider/console/providers/__init__.py:9-28`) y solo devuelve señales de logs.
  * Solo la usa la ruta de reglas (`service.py:62-64`), que la decisión 6 retira.
  * El agente llama directo a `gcp_signals` y `gcp_events` (`investigation_tools.py:146,202`).
  * `logging_mcp` es un transporte dentro de `gcp_signals` (`cloud_logging.py:58-60`), no una implementación del proveedor.
  * Los eventos K8s salen de `logs/events` de Cloud Logging (`kubernetes_events.py:20-24`), que es propio de GCP. No hay una "capa K8s común a GKE, EKS y AKS".
* Las etiquetas de estado de las 16 decisiones son inconsistentes. Hay siete distintas (decidido, pendiente, en definición, propuesto, verificado, aceptado, propuesta de cierre) bajo el título "Decisiones tomadas". Además hay dependencias invertidas: la 15 está "aceptada" pero depende de la 13, que está "propuesta".
* **Requisito:**
  * Cada componente y cada decisión del informe lleva una etiqueta de estado.
  * La decisión 10 se reescribe como "contrato a extraer; hoy los eventos llegan vía Cloud Logging".
  * Las decisiones van a un registro único con un campo "depende de".
* **Estado tras la decisión 19:** parcial. Se adoptan las etiquetas existe / se construye / plan para componentes y aceptada / propuesta / pendiente para decisiones, y la decisión 10 pasa a "contrato a extraer". Falta el registro con "depende de".

**N2. El reparto confunde "no visto" con mecanismo, y `scale_zero` tiene efecto techo.** (los siete)
* `wrong_port`, `latency` y `cpu_limit` solo actúan sobre `cartservice` (`chaosforge/admin/faults.py:16`), y `cartservice` está en el historial. Todo lo no visto es `scale_zero`, y ningún mecanismo queda sin ver.
* La firma de `scale_zero` es igual en todos los servicios: `ScalingReplicaSet` a 0, más silencio. Un postmortem de cart×scale_zero enseña el patrón para todos los servicios, así que "no visto" solo mide novedad del nombre del servicio.
* El filtro de caso válido de la decisión 15 se cumple siempre, porque la propia inyección emite `ScalingReplicaSet`. Ese filtro usa la misma evidencia que lee Tider y selecciona los casos fáciles.
* Con techo en el top-1, la McNemar del Lake con o sin postmortems casi no tendrá pares discordantes. La McNemar exacta bilateral necesita al menos 6 pares discordantes en el mismo sentido para llegar a p<0,05.
* La decisión 13 define "visto" por el par servicio×mecanismo. La decisión 15 reparte solo por servicio.
* También quedan confundidos:
  * la posición en el grafo: los no vistos incluyen la raíz (`frontend`) y `redis-cart`, que está detrás de cart;
  * la visibilidad del síntoma: las sondas no ven email ni shipping;
  * la duración: `scale_zero` dura 30–120 s y los otros mecanismos 120–240 s (`faults.py:78`, `controller.py:99`).
* `redis-cart` no está realmente sin ver: los postmortems de cart con `wrong_port` llevan errores `redis-cart:6380`, y `frontend` aparece como víctima en casi todos.
* Los mecanismos distintos de `scale_zero` no están desplegados. `experiments.yaml` es opcional y solo habilita `wrong_port` (`chaosforge/k8s/experiments.yaml:1,45`). `latency` necesita `k8s/proxy.yaml`.
* **Requisito:**
  * Definir "visto" como "el par (servicio, mecanismo) tiene postmortem en la versión congelada del Lake" y publicar el reparto como tabla de pares.
  * Estratificar por mecanismo y por rol en el grafo. Si se quiere un mecanismo sin ver, reservar cart×{`latency`, `wrong_port`} sin postmortem.
  * El filtro de caso válido exige un síntoma distinto del evento de la inyección (errores en los llamadores dentro de la ventana), adjudicado por script antes de correr Tider.
  * Medir la ganancia del Lake donde no hay techo: el rol causa / víctima (patrón C09) o un brazo sin eventos.
  * Declarar la McNemar como descriptiva si hay menos de 10 pares discordantes.
* **Estado tras las decisiones 18 y 19: resuelta por acotamiento de alcance.**
  * El informe afirma solo esto para la iteración: "Tider localiza fallas de disponibilidad (`scale_zero`) en los 12 servicios; las fallas sutiles (`wrong_port`, `latency`, `cpu_limit`) solo se evaluaron sobre `cartservice`".
  * Se reconoce que, con barrido de eventos, `scale_zero` es casi trivial, porque `ScalingReplicaSet` nombra al servicio.
  * Extender las fallas sutiles a otros servicios se declara como siguiente paso de la campaña.
  * El reparto se publica como pares servicio×mecanismo (decisión 19).
  * Siguen como requisitos del plan de campaña, no como objeción: el filtro de caso válido con un síntoma distinto del evento de la inyección y la McNemar declarada descriptiva si hay pocos pares discordantes.

**N3. La validación del chunking (decisión 16) filtra la respuesta y ajusta sobre el conjunto de prueba.** (implementation-readiness, inventive-catalyst, design, zoom-out, codebase-details)
* Las señales crudas contienen el nombre del servicio: el pod, la etiqueta `k8s-pod/app` y `cartservice:7070` en los logs de los llamadores. Como la relevancia es "el documento del servicio que falló", BM25 acierta por coincidencia de cadena. Si el filtro por `servicio` toma su valor del ground truth, es una fuga directa.
* Elegir la variante con las corridas de evaluación y después reportar el diagnóstico sobre esas mismas corridas es ajustar sobre la prueba. Contradice la decisión 13.
* "El runbook del servicio que falló" no existe, porque la decisión 12 indexa los runbooks por modo de falla. Los no vistos no tienen postmortem.
* Las 4 variantes mezclan dos factores, el chunking y el recuperador.
* `context_search` limita k a 4 (`investigation_tools.py:158`). Con unos 25 documentos, Hit@4 tiene una línea base aleatoria alta.
* **Requisito:**
  * El generador de consultas es determinista y queda congelado. Mejor aún, usar las consultas reales del Investigador registradas en la traza.
  * Agregar una variante con los nombres enmascarados (`<SVC>`) y un baseline de coincidencia de cadena.
  * Relevancia por mecanismo o antecedente, definida por brazo y por tipo de documento.
  * Elegir la variante con el historial y reportarla con la evaluación.
  * Fijar un factor, o usar un diseño 2×2. Reportar Hit@1 y MRR con corrección de Holm.

**N4. Archivar fuera de `tider/` rompe la consola, las pruebas y el benchmark que justifica el chunking.** (structural, design, codebase-details)
* Arranque de la consola: ver B3 (`console/api.py:14`, `analysis.py:6-12`).
* `eval/quality/data.py:34-35` lee `docs/runbooks`, y `manifest.json:7-10` hashea esas rutas. `verify()` falla con FileNotFoundError, y el resultado Hit@4 15/16 vs 8/16 (p=0,016) deja de reproducirse. Ese resultado se midió el 6/11 con una versión anterior del buscador (el hash de `src/tider/console/context_lake.py` registrado en `eval/quality/recordings/retrieval-v1.json` ya no coincide con el actual); debe volver a medirse con el código actual.
* También dependen de `docs/` o del grafo:
  * pruebas: `tests/test_api.py:94-98`, `test_e2e.py:27,36,198,281`, `test_units.py:264-269`, `test_observation.py`, `tests/console/test_service.py` y `test_general_scope.py`;
  * evaluación y scripts: `eval/harness.py:26-32,83`, `eval/mock_local.py:146`, `scripts/record_fixture.py` y `scripts/render_diagrams.py`.
* Hay enlaces rotos en `README.md:93-94`, `docs/testing.md:64`, `docs/architecture.md:88` y `docs/decisions.md:103`.
* `project/documentation/archivo/` está en otro árbol, quizá fuera del control de versiones. El código del grafo, el ejecutor y el RBAC sigue en `tider/src`, sin documentación.
* Las rutas antiguas ingieren todo `tider/docs`, y un `.md` sin tipo se vuelve `runbook` (`lake/ingest.py:57`). Un informe nuevo dentro de `tider/docs` se ingeriría como runbook.
* **Requisito:**
  * Antes de mover nada:
    * cortar la importación de `LabEngine` en `console/api.py`;
    * congelar los runbooks OTel como entrada del benchmark en `eval/quality/corpus/`, con una nueva versión del manifiesto;
    * mover o retirar las pruebas del grafo.
  * Archivar dentro del repositorio (`tider/docs/archive/`, excluido del informe y de la ingesta), y dejar en `project/documentation/archivo/` solo un puntero.
  * El informe y el corpus del Lake viven en árboles separados.
* **Estado tras la decisión 19:** parcial. La ubicación queda fijada dentro del repositorio, con un puntero en `project/documentation/archivo/`, y reemplaza la ubicación de la decisión 6. Los pasos previos siguen pendientes.

#### Mayores

**N5. El juez de otra familia no se puede implementar hoy, y su métrica tiene un denominador muy chico.** (todos)
* La consola usa el mismo `llm` para el Investigador y el juez (`agentic.py:161,348`).
* `TIDER_JUDGE_MODEL` solo lo lee el webhook del núcleo que se archiva (`tider/src/tider/api.py:41-47`). `roles_agentes.md:71` lo cita como si aplicara a la consola.
* `llm_provider` solo admite `none` o `anthropic` (`console/settings.py:19`), y solo existe `AnthropicLLM` (`tider/src/tider/llm.py:47`).
* El timeout y la metadata solo se aplican a `AnthropicLLM` (`agentic.py:197-198,208`).
* El registro guarda `model: tider_model` y no guarda el modelo del juez (`agentic.py:446`).
* Mandar logs a otro proveedor es un tema de gobierno de datos (criterio C1 de la rúbrica).
* La métrica tiene problemas de diseño:
  * En E5 hubo 1 diagnóstico falso (C09), y con `scale_zero` habrá entre 2 y 5.
  * Un juez que rechaza todo tiene 0 falsas aprobaciones.
  * Cuando el juez rechaza, igual se devuelve el `component` del candidato (`agentic.py:414`), así que la aprobación se mide con `review_status == "passed"` (`:357`).
  * El brazo "sin juez" cambia también la trayectoria, porque el rechazo vuelve a `choose` (`agentic.py:390`).
* "Otra familia" aparece con cuatro fuerzas distintas: "idealmente otro modelo" (`roles_agentes.md:39`), "otro modelo" (decisión 8), "lo ideal es otra familia" (`roles_agentes.md:71`) y "de otra familia" (hipótesis v2).
* **Requisito:**
  * Agregar `judge_provider` y `judge_model` en la configuración de la consola, con un adaptador por proveedor y timeout uniforme. Empezar con otro modelo de Anthropic, que es un cambio de configuración, y pasar a otra familia solo si la métrica se puede medir.
  * Armar un conjunto de al menos 30 diagnósticos falsos mutados sobre ventanas congeladas: causa y víctima intercambiadas, mecanismo cambiado, citas irrelevantes, solo documentos.
  * Reportar falsa aprobación y falso rechazo de tres brazos pareados: sin juez, misma familia y otra familia.

**N6. El barrido no es "de todo el namespace" y comparte presupuesto.** (design, codebase-details, inventive-catalyst, implementation-readiness)
* El filtro por catálogo es el de M3.
* El barrido inicial que ya existe es una sola consulta global de errores (`agentic.py:382-398`):
  * tope de 200, del más nuevo al más viejo (`cloud_logging.py:74`);
  * el intercalado por servicio se hace después de truncar (`investigation_tools.py:204-222`);
  * `truncated` es global;
  * los eventos tienen tope de 100 en orden descendente (`kubernetes_events.py:61`).
* Un servicio ruidoso llena el tope, así que el "estado garantizado por nodo" no se cumple.
* El barrido comparte con el Investigador el presupuesto de 2000 registros, los 90 s y los 12 pasos (`settings.py:23-26`).
* Leer solo errores ya falló en el propio benchmark: 0/6 contra 6/6 con todas las severidades (`_contexto_consola_eval_docs.md:292`).
* Los eventos de la API de K8s caducan en unos 60 min, y la cuota de lectura de Cloud Logging (unas 60 llamadas/min, valor por defecto de GCP, sin verificar en este proyecto) limita las corridas en paralelo.
* La prueba citada en la decisión 9 está en `tests/console/test_agentic.py:144-154` y verifica que no se llame a `provider.load`, no que no haya precarga. Si el barrido se hace dentro del motor (rol Recolector), las pruebas siguen valiendo. Si se hace como precarga del proveedor, las dos se rompen.
* **Requisito:**
  * Cuota fija por servicio, con un flag `truncated` por nodo que lo fuerza a "sin datos".
  * Presupuesto de registros y de tiempo separado del Investigador.
  * Ventana fija, por ejemplo [t0−5 min, t0+W], más una ventana anterior a t0 como línea base de ruido.
  * Una muestra acotada de todas las severidades por servicio.
  * Una instantánea en t0, que es a la vez el fixture de replay.
  * El LLM recibe una tabla de 12 filas y pide las líneas crudas bajo demanda.

**N7. Fuga por fichas y postmortems que la decisión 13 no cubre.** (design, implementation-readiness, inventive-catalyst, comprehension)
* Las fichas de servicio incluyen "síntomas vistos desde los llamadores" (`_contexto_chaosforge_lake.md:164`). Si las fichas de los no vistos se escriben después de ver corridas, hay interpretación a posteriori.
* Con señales crudas, un postmortem de un caso visto repite casi literalmente la ventana de evaluación, y un fragmento de documento puede pasar por evidencia viva. Hoy el juez exige al menos una observación (`agentic.py:330-334`), pero una línea de log trivial más un postmortem pasan igual.
* "Postmortem sin interpretación a posteriori" es contradictorio, porque un postmortem lleva la causa confirmada. Además, aquí "postmortem" es un experimento inyectado, no un incidente real.
* **Requisito:**
  * Congelar las fichas (con hash) antes de cualquier corrida de evaluación. Las de los no vistos se escriben solo con la topología y conocimiento general.
  * Citas tipadas: la causa cita al menos una señal viva relevante y nunca solo un documento.
  * Postmortem = señales crudas + causa confirmada + acción, sin narrativa reconstruida. Una sección de "forma de señal" con el nombre enmascarado (`<SVC>`) y una sección propia del servicio.

**N8. El barrido no puede producir "sano confirmado" (decisión 3 frente a decisión 9).** (implementation-readiness, comprehension, inventive-catalyst, design)
* Con errores y eventos solo se puede llegar a "falla confirmada" o "sin datos".
* **Requisito:** un predicado positivo sobre la ventana:
  * `readyReplicas == spec.replicas > 0` y endpoints > 0, con instantánea fechada;
  * cero errores;
  * al menos K líneas que no son error;
  * ningún llamador con errores que nombren al servicio.
* Si no se construye, la entrega tiene dos estados y el riesgo queda declarado.

**N9. El chunking por tipo choca con los límites del Lake actual.** (design, codebase-details)
* `split_markdown(body, 900)` se aplica a todo (`console/context_lake.py:167`), así que un runbook completo o una ficha de 300–600 tokens se corta.
* El front matter se descarta (`:89-96`). Solo se guardan `doc_id`, `title`, `page`, `chunk` y `doc_type`, este último elegido por la extensión del archivo (`:179-185`).
* `search(query, k)` no acepta filtro `where` (`:205`).
* `MAX_DOCUMENTS=20` y `MAX_CHUNKS=300` (`:23-24`). 12 fichas, runbooks, postmortems, topología y catálogo superan 20 documentos.
* No hay BM25. El componente léxico es una compuerta ponderada por IDF sobre Chroma (`:48-80,205-216`). Por eso la variante "actual" ya es casi híbrida, y "solo léxica" y "solo semántica" son ablaciones de ella.
* `all-MiniLM-L6-v2` trunca la entrada a unos 256 word-pieces (es el valor por defecto conocido del modelo; no se verificó en el código).
* El Lake es efímero y vive en cada proceso, y su "revisión" es un contador que se reinicia (`:142,144,191`). Hoy no hay forma de congelarlo, como pide la decisión 13.
* **Requisito:**
  * Un chunker por tipo, con los metadatos persistidos y filtros.
  * Subir o rediseñar los límites.
  * Una versión congelada del Lake: manifiesto con hash por documento, modelo de embedding e índice.
  * Declarar el truncado del modelo de embedding.

**N10. El control `loadgenerator` choca con el catálogo.** (design, comprehension, inventive-catalyst)
* Escalar `loadgenerator` a cero es una inyección `scale_zero` real. El verificador de firmas la confirma con razón, y se contaría como falso positivo un acierto.
* **Requisito:** definir la etiqueta esperada antes de correr, por ejemplo `{loadgenerator, scale_zero, sin_impacto_en_tienda}`. La firma de un modo de falla de la tienda exige efecto en los llamadores. Llamarlo "caso de control negativo".

**N11. El replay entre brazos no funciona con el `FrozenTools` actual.** (design, codebase-details, implementation-readiness)
* Los brazos con y sin postmortems, y con y sin juez, hacen consultas adaptativas distintas. Un fixture que guarda la respuesta por consulta falla en el otro brazo.
* Los fixtures de `22698d1` no tienen las llamadas del barrido.
* El efecto del Lake depende de que el LLM llame a `context_search`, que es opcional (la topología igual entra en el prompt, `agentic.py:172`).
* **Requisito:**
  * Grabar por ventana un superconjunto (todas las severidades, todos los servicios, eventos del namespace) y filtrar en local.
  * Versionar los fixtures: con barrido y sin barrido.
  * Registrar por corrida las llamadas a `context_search` y los IDs recuperados. Sin eso, una McNemar nula no se distingue de "no consultó el Lake".

**N12. Los roles se contradicen en orden, número de usos del LLM y alcance del filtro.** (comprehension, structural, design, codebase-details)
* El brief de la ronda 1 (D1) pone el verificador del catálogo después de que el juez aprueba. `roles_agentes.md` §6 pone al Proponente antes del Juez, y el Juez revisa la firma.
* El flujo Cartógrafo → Recolector (§6) hace que el Lake vaya antes de la evidencia, y la entrada del Recolector es "Mapa previo + …". Eso reintroduce la circularidad que prohíben las decisiones 3 y 9.
* La decisión 8 dice 2 roles LLM. `roles_agentes.md:42` suma un respaldo LLM en el Proponente: 3 puntos de llamada, y el tercero sin modelo asignado.
* La decisión 9 dice que el Investigador profundiza con herramientas. El flujo devuelve "pide más evidencia" al Recolector, que es determinista.
* El filtro de verbos (`roles_agentes.md:49`) prohíbe `scale` en "la recomendación". Pero la acción de catálogo para `scale_zero` es restaurar las réplicas.
* La regla "el juez rechaza lo que solo se apoya en documentos" (decisión 12) falta en `roles_agentes.md` §5.
* **Requisito:**
  * Orden fijo: barrido (Recolector) en paralelo con el Cartógrafo o antes que él, y luego Investigador → Proponente → Juez → Reportero.
  * La re-investigación la pide el Juez al Investigador.
  * El filtro de verbos aplica solo al respaldo LLM. La acción del catálogo es texto para una persona.
  * Declarar "2 roles LLM y 3 puntos de llamada al LLM".

**N13. El vocabulario sigue con colisiones.** (comprehension, structural, zoom-out)
* **Confianza:** decisión 2 (ver B4).
* **Cobertura:** tiene dos definiciones. En la ronda 1 son los nodos con predicado evaluable / 12. En `roles_agentes.md:50` es "falló un conector o se llegó al tope".
* **Catálogo:** tres sentidos (m2).
* **Runbook:** dos sentidos. Los runbooks de remediación OTel que se archivan prescriben `scale` y `rollout`. Los nuevos del Lake son procedimientos de asesoría.
* **Revisión:** tres sentidos. La versión congelada del Lake, un campo de metadatos y la "Revisión de sustento" del juez en el diagrama.
* **Mapa:** tres sentidos. El mapa de servicios de la UI, el Lake como mapa previo y la salida del Cartógrafo.
* **Control:** choca con la matriz riesgo → control, con "controles deterministas" y con "controles negativos".
* **Numeración de decisiones:** hay tres esquemas que chocan. Las 16 de la auditoría, D1–D8 del brief y D01–D06 de `docs/decisions.md`. El "D5" del brief es chunking, y la "decisión 5" de la auditoría es κ.
* **Requisito:**
  * Glosario.
  * "Catálogo de modos de falla".
  * "Guía de diagnóstico y verificación" en lugar de "runbook" para los documentos nuevos.
  * "Versión congelada del Lake".
  * "Mapa previo" solo para el Lake y "mapa de servicios" para la UI.
  * "Caso de control negativo".
  * Un solo registro de decisiones con IDs únicos y una tabla de correspondencias.
* **Estado tras la decisión 19:** parcial. Se resuelven "confianza", "catálogo" y el vocabulario de estados. Quedan los demás términos y la numeración.

**N14. El catálogo vuelve a nombrarse por el mecanismo del inyector.** (design, inventive-catalyst, comprehension)
* La decisión 4 dice "uno por cada mecanismo de ChaosForge" y revierte el rechazo de la ronda 1. Es una hoja de respuestas con otro nombre.
* **Requisito:** cada entrada se nombra por un modo de falla genérico de K8s (sin réplicas disponibles, puerto o destino mal configurado, latencia de red, límite de CPU), y el mecanismo de ChaosForge queda como etiqueta de evaluación.
* **Estado tras la decisión 19:** resuelta en la decisión. Falta reflejarlo en el texto del catálogo y en el informe.

**N15. El alcance creció más allá de lo que pide una reunión informativa.** (zoom-out, design)
* Búsqueda híbrida con 4 variantes sobre un corpus de unos 25 documentos, cuando el léxico ya ganó (p=0,016; medido el 6/11 con una versión anterior del buscador; debe volver a medirse con el código actual). El patrón de acceso real es por clave: topología, fichas y catálogo.
* Campaña estimada (son estimaciones, no mediciones):
  * Historial, unas 10–24 inyecciones.
  * Evaluación, unas 33–65.
  * Controles, al menos el 20 %.
  * Total, entre 50 y 90 inyecciones en serie (`controller.py:50-51`), de 5 a 10 h de GKE.
  * Tokens, unos 20M en replays (US$20–65).
* Con unos 18 casos no vistos, el semiancho de Wilson es de unos ±20 pp.
* **Tamaño de muestra (cálculo de la validación externa).** McNemar exacto bilateral, α = 0,05, potencia 0,8; la unidad es la inyección independiente, no las repeticiones:
  * ganancia de 20 pp con 5 pp de pérdida: ~92 casos pareados;
  * ganancia de 15 pp con 5 pp de pérdida: ~168;
  * ganancia de 10 pp con 5 pp de pérdida: ~498 (no factible).
  * Semiancho de Wilson en el peor caso: n = 30, ±17 pp; n = 60, ±12 pp; n = 100, ±10 pp; n = 168, ±7,5 pp.
  * Cero falsas aprobaciones del juez: cota superior unilateral al 95% ≈ 9,5% con n = 30 y ≈ 4,9% con n = 60.
  * Conclusión: con la campaña factible (decenas de casos), la McNemar del Lake con y sin postmortems solo detectaría efectos grandes. Se declara así en el plan de campaña (Anexo A).
* Hay al menos 5 configuraciones (juez sí / no, familia, Lake ± postmortems, baseline de reglas). Hay que prerregistrar una sola comparación principal, y el resto es exploratorio.
* **Requisito:** en la etapa 0, esto entra como plan de una página, no como resultado.

#### Menores

* La decisión 10 tiene una errata: "decidido, se presenta…" y "la intención" en minúscula (`_auditoria_consolidada.md:80`). Agregar la frase "MCP se mantiene como transporte posible; la independencia la da el contrato de evidencia".
* Escalar `redis-cart` a cero borra los datos del carrito (`controller.py:11`), así que la línea base de las corridas siguientes cambia.
* `scale_zero` tiene precondiciones no declaradas: todas las réplicas listas, sin HPA y las sondas en 200 (`controller.py:105-111`).
* La decisión 16 deja k sin fijar y no dice si BM25 reemplaza al TF-IDF del benchmark.
* "Antecedente" (decisión 12) no está definido. Hay que decir que tiene su propio espacio de citas, separado de `S01…`.
* La McNemar del Lake no dice cuál es el resultado pareado (top-1 componente, o componente + mecanismo).
* `roles_agentes.md` §7 todavía pregunta si se fusionan Cartógrafo y Recolector. Fusionarlos deja 5 roles, contra los 6 fijados. La recomendación (zoom-out) es mantener 6 en el informe por claridad y declarar que dos son código.

### 2.3 Contradicciones internas entre las 16 decisiones

Las filas marcadas "Aceptada (decisión N)" quedaron cerradas por las decisiones del autor.

| Decisiones | Contradicción | Resolución propuesta |
|---|---|---|
| 2 frente a D3 (ronda 1) | La 2 promete "confianza" por hipótesis. La ronda 1 la había reemplazado por orden y cobertura. | Aceptada (decisión 19): "ordenadas, con evidencia, rol y cobertura". |
| 3 frente a 9 | La 9 garantiza un estado por nodo con errores y eventos, pero la 3 dice que sin logs no hay "sano". En el código, el barrido está limitado al catálogo del Lake. | La 9 garantiza "falla confirmada" o "sin datos". "Sano" requiere el predicado de N8. El barrido no filtra por catálogo. |
| 4 frente a 5 | La 4 mide la sugerencia LLM con κ, que la 5 pospone. | La métrica queda condicionada a la 5. |
| 4 frente a la ronda 1 | El catálogo vuelve a nombrarse por el mecanismo del inyector. | Aceptada (decisión 19): modo de falla genérico de Kubernetes (N14). |
| 4 frente a `roles_agentes.md` §5 | La acción del catálogo choca con el filtro de verbos. | El filtro aplica solo al respaldo LLM. |
| 6 frente a 10 | El único consumidor de `EvidenceProvider` es la ruta de reglas que se retira. | El contrato se extrae al nivel de `InvestigationTools`. |
| 6 frente a 8 | `TIDER_JUDGE_MODEL` vive en el código que se archiva. | Configuración `judge_model` en la consola. |
| 6 frente a 7 y 16 | La etapa 0 justifica el chunking con un benchmark cuyo corpus se archiva. | Congelar el corpus en `eval/quality/corpus/` antes de archivar. |
| 7 frente a 8, 9, 10, 12 y 16 | "Basta la etapa 0", pero esas decisiones describen comportamiento que no existe. | Aceptada (decisión 19): etiquetas existe / se construye / plan (N1). |
| 11 frente a 13 | Las fichas de los no vistos pueden llevar interpretación a posteriori. | Congelarlas con hash antes de las corridas (N7). |
| 12 frente a 13 | Un postmortem con señales crudas parece evidencia, y "sin interpretación a posteriori" contradice la causa confirmada. | Citas tipadas y definición de postmortem (N7). |
| 13 frente a 15 | La 13 define "visto" por servicio×mecanismo y la 15 reparte por servicio. | Aceptada (decisión 19): reparto como pares servicio×mecanismo (N2). |
| 13 frente a 16 | "La evaluación nunca alimenta el Lake", pero la 16 elige el chunking con corridas de evaluación. | Elegir con el historial (N3). |
| 14 frente a 15 | Lo no visto solo puede ser `scale_zero`, y el filtro de caso válido no filtra nada. | Aceptada (decisión 18): afirmación acotada y extensión como siguiente paso. El filtro de caso válido no vacío queda en el plan de campaña (N2). |
| 14 frente a 4 | El control `loadgenerator` confirma una firma real. | Etiqueta esperada (N10). |
| 15 frente a 13 | La 15 está "aceptada" y depende de la 13, que está "propuesta". | Registro con estado y "depende de" (N1). Sigue abierta. |
| 10 (interna) | "Decidido…" y "la propuesta es…" en el mismo ítem. | Aceptada (decisión 19): punto de extensión, "contrato a extraer". |
| 1 / 6 / hipótesis v2 | Tres ubicaciones para el archivo: `docs/archive/remediacion/`, "externo al informe" y `project/documentation/archivo/`. | Aceptada (decisión 19): dentro del repo, con un puntero en `project/documentation/archivo/` (N4). |

### 2.4 Contradicciones inventivas y resoluciones

**Ronda 1 (estado actualizado):**

| # | Contradicción | Estado en ronda 2 | Nota |
|---|---|---|---|
| C1 | Rigor de κ sin expertos | Parcial | La decisión 4 separa el oráculo de ChaosForge y κ. La 16 saca a los humanos del chunking. No se adoptó la gramática cerrada de pasos de diagnóstico. |
| C2 | Flexibilidad del LLM frente a seguridad del catálogo | Resuelta en principio | El rol Proponente aplica la extracción. Depende de B1. |
| C3 | Oráculo circular | Parcial | La decisión 17 aísla `/api/evidence` y la decisión 19 nombra el catálogo por modo de falla genérico de Kubernetes. Falta implementar el aislamiento. |
| C4 | El Lake sesga la evidencia | Resuelta en el papel | Decisión 9. En el código sigue el filtro por catálogo (M3). |
| C5 | Sin logs no significa sano | Parcial | N8. |
| C6 | Chunking con corpus mínimo | Resuelta | Decisión 12. Abre C14. |
| C7 | Potencia frente al costo de las inyecciones | Abierta | No hay decisión de grabar y reproducir, y ahora la necesitan tres métricas más. |
| C8 | Modo sin LLM | Abierta | C16 la cierra. |

**Ronda 2 (nuevas):**

| # | Contradicción | Resolución propuesta | Costo |
|---|---|---|---|
| C9 | Hay que cubrir los 12 nodos, pero los presupuestos de registros y de tiempo son fijos. | **Segmentación y acción previa.** Cuota por nodo y un resumen por nodo hecho en Python (conteo por severidad, plantillas de error deduplicadas, primera y última marca, eventos, réplicas y endpoints en t0). **Inversión:** el LLM pide las líneas crudas bajo demanda. **Convertir el daño en señal:** delta contra una ventana anterior a t0. | Código de agrupación. El resumen puede esconder matices. Doble consulta. |
| C10 | La portabilidad entre nubes choca con la retención de eventos (K8s caduca en unos 60 min). | Una instantánea en t0 que es a la vez evidencia, fixture de replay y cuarto adaptador del contrato. | Almacenamiento y versiones de los fixtures. |
| C11 | Los postmortems son útiles, pero filtran. | **Segmentación en dos capas:** forma de señal enmascarada (`<SVC>` + rol en el grafo) y sección propia del servicio. La McNemar tiene sentido en los no vistos. | Probar el regex de enmascarado y mantener dos secciones. |
| C12 | Lo no visto debe ser nuevo, pero solo existe `scale_zero`. La decisión 18 opta por acotar la afirmación; la estratificación queda como siguiente paso. | **Estratificación:** reparto por rol en el grafo y por visibilidad del síntoma; "visto" por par; cart×{`latency`, `wrong_port`} fuera del historial. Medir el Lake en el rol causal. | Habilitar los mecanismos en GKE. Celdas pequeñas. |
| C13 | Hit@k con señales crudas que nombran el servicio da un resultado trivial. | Relevancia por mecanismo o antecedente, ablación con nombres enmascarados, consultas solo con señales de víctimas y consultas reales de la traza. | Con solo `scale_zero` la métrica se satura. |
| C14 | Chunking por tipo frente a un corpus diminuto. | **Segmentar por patrón de acceso:** topología, fichas y catálogo se leen por clave, sin ranking. Solo los postmortems van por búsqueda híbrida, y el experimento se limita a ellos. | El resultado se ve menos impresionante. Hay que justificar la parte semántica o quitarla. |
| C15 | El juez de otra familia necesita diagnósticos falsos que casi no ocurren. | **Convertir el daño en señal:** pruebas de mutación del juez sobre ventanas congeladas. Tres brazos pareados. | Las mutaciones pueden ser más fáciles que los errores naturales: reportar ambos. Hace falta un segundo proveedor. |
| C16 | El barrido fijo vuelve imposible medir la parte adaptativa, y el modo sin LLM depende del grafo. | **Un brazo "solo barrido + verificador de firmas".** Es el modo sin LLM y el baseline a la vez. | El baseline será fuerte en `scale_zero`: estratificar. |
| C17 | La independencia de nube se afirma, pero solo se probó GKE. | Una suite de conformidad del contrato sobre mock, Cloud Logging, transporte MCP y el replay, con normalización de severidad fijada en el contrato. La afirmación pasa a ser "portable por contrato, verificado en 1 nube real". | No prueba la semántica de AWS, Azure, EKS ni AKS. |

### 2.5 Resultado Final Ideal (IFR, actualizado)

En t0, un barrido determinista deja una **ventana congelada por caso**. Esa ventana tiene:

* un resumen por nodo con cuota y delta contra la línea base;
* eventos, réplicas y endpoints;
* el estado de tres valores de cada nodo, derivado en Python.

La misma ventana es evidencia, fixture de replay y adaptador de prueba del contrato de evidencia.

Sobre esa ventana:

* Python confirma las firmas de evidencia, que exigen el efecto en los llamadores. Ese verificador es también el baseline sin LLM.
* El Investigador pide solo las líneas crudas que necesita.
* El Lake se lee por clave (topología, fichas, catálogo de modos de falla). Solo los postmortems, con el nombre enmascarado, se recuperan por búsqueda.
* El juez de otro modelo se audita contra diagnósticos falsos mutados y contra los errores naturales, comparado con "sin juez" y con un juez del mismo modelo.

La evaluación funciona sin humanos:

* el ground truth vive en otro proceso;
* el reparto se estratifica por par servicio×mecanismo y por rol en el grafo antes de congelarlo;
* la ganancia del Lake se mide en el rol causa / víctima;
* la recuperación se mide por mecanismo, con los nombres enmascarados.

Lo único humano que queda es κ sobre las sugerencias no verificadas, declarado pendiente. El informe describe exactamente ese sistema en las 5 capas del profesor, y cada pieza dice si existe, se construye o es plan.

### 2.6 Alcance del producto: acoplamientos, reglas de diseño y caso SIBI (decisión 20)

La visión es cualquier nube y cualquier aplicación en contenedores orquestados. La app real objetivo, SIBI, corre en AWS ECS con Fargate y sin Kubernetes, lo que choca con "siempre sobre Kubernetes". La decisión 20 lo resuelve con Kubernetes como plataforma principal, ECS como extensión y SIBI como caso de generalidad en replay.

#### Acoplamientos verificados en el código (rutas bajo `tider/src/tider/console/`)

* **Con la aplicación (Online Boutique):**
  * `providers/catalog.py`: el catálogo de servicios de la tienda.
  * `investigation_tools.py:272`: nombres de variables de entorno propias de la tienda (`REDIS_ADDR`, `PRODUCT_CATALOG_SERVICE_ADDR`).
  * `providers/operational_observer.py`.
  * `settings.py:17`: `gcp_namespace = "boutique"` por defecto.
  * `providers/mock.py`.
  * `analysis.py:108`: texto fijo "Análisis de evidencia en Online Boutique".
* **Con GCP:**
  * Logs: Cloud Logging.
  * Eventos K8s: se leen desde Cloud Logging (`logs/events`, `providers/kubernetes_events.py:23`), no desde la API de Kubernetes.
  * Métricas: Cloud Monitoring.
* **Sin acoplamiento:** `agentic.py` no tiene referencias a la aplicación.

#### Reglas de diseño

1. **El conocimiento de la aplicación vive solo en el Context Lake.** Nombres de servicios, dependencias, variables de entorno y textos de la app salen del código de la consola.
2. **El acceso a la nube y a la plataforma vive solo en adaptadores:** de logs (Cloud Logging, CloudWatch) y de plataforma (Kubernetes, ECS). Los eventos K8s se leen vía la API de Kubernetes, no vía Cloud Logging, para que la capa de plataforma no dependa de GCP.

Estado: plan, junto con el contrato de evidencia a extraer (decisión 10). El contrato servicio/instancia de plataforma queda definido en la decisión 22 (sección 2.8); su implementación en los adaptadores se construye.

#### Catálogo por modo de falla genérico, con firmas por plataforma

La decisión 20 extiende la decisión 19: cada modo de falla es genérico y tiene una firma distinta en cada plataforma, más la acción sugerida, cómo verificar y el riesgo. Solo se aplica si la evidencia confirma la firma. La definición operativa de firma y el catálogo v1 están en la sección 2.7 (decisión 21); la tabla de abajo es la versión de la decisión 20.

| Modo de falla | Firma en Kubernetes | Firma en ECS |
|---|---|---|
| Servicio sin instancias | `replicas=0`, evento ScalingReplicaSet | `desiredCount=0` o `runningCount=0` |
| Se cae al arrancar | CrashLoopBackOff | Task detenida con exit code ≠ 0 |
| Sin memoria | OOMKilled | `stoppedReason: OutOfMemoryError` |
| Configuración incorrecta | Variable de entorno cambiada en el Deployment | Nueva revisión de la task definition |

#### Caso SIBI en replay: restricciones de la Carta de Autorización

Base legal: la Carta de Autorización de Uso de Datos SIBI, firmada por la Gerente General el 11/10/2026 (`ENTREGA_E4_EQUIPO04_PARA_VALIDAR_20261015/`).

| Cláusula | Restricción para el replay |
|---|---|
| 2 | Finalidad exclusivamente académica: evaluación retrospectiva de incidentes pasados y validación del prototipo. No se entrena ni ajusta ningún modelo con datos de SIBI. |
| 3 | Fuentes autorizadas: logs y métricas de AWS CloudWatch en la ventana 14/04/2026–11/10/2026, más Sentry, GitHub, diagramas y registros de incidentes derivados. Los **eventos de servicio ECS y CloudTrail no están autorizados**. |
| 5 | Enmascarado y seudonimización en origen, custodiados por SIBI, antes de que los datos salgan. A la API del LLM solo llegan datos ya anonimizados. Acceso de solo lectura y limitado a las fuentes de la cláusula 3. |
| 6 | Las pruebas y la inyección de fallas se hacen en un entorno mock, nunca en producción de SIBI. La cláusula todavía nombra a **OTel Demo** como mock, pero el piloto usa Online Boutique: conviene una nota o adenda. |
| 10 | En entregables y presentaciones solo van resultados agregados o anonimizados. SIBI puede revisarlos antes de su entrega. |
| 11 | La autorización la da la Gerente General, no el autor. Las etiquetas de ground truth las validan exclusivamente Alberto y Jose. |

**Riesgos del replay:**

* **Puede no haber eventos ECS históricos.** La API de ECS solo conserva los últimos 100 eventos de servicio. Solo habría historial si SIBI los enviaba con EventBridge hacia CloudWatch Logs. Además, los eventos ECS y CloudTrail no están entre las fuentes autorizadas (cláusula 3). Si no existen o no se autorizan, el replay solo tendrá logs y métricas, y prueba el adaptador de logs, no el de plataforma. Las firmas ECS de la tabla quedarían sin probar.
* **κ:** Alberto y Jose (cláusula 11) son candidatos a evaluadores κ. La objeción M5 pasa a parcial, no resuelta.
* El replay es un caso único: demuestra generalidad, no da potencia estadística, y queda fuera de la estadística.

### 2.7 Firmas operativas (decisión 21, aceptada el 2026-11-09)

Fuente: `recomend/_bibliografia_firmas.md` (sección 9). Marcado de origen: **[LIT]** viene de la bibliografía, con su cita; **[INF]** es inferencia propia o conocimiento de plataforma que ningún PDF contiene. Las referencias completas están en la sección 6.

Estado del componente: **se construye** (etapa 1). Hoy no hay verificador de firmas en el código.

#### Esquema de una firma

Una firma es una regla determinista asociada a un modo de falla. Recoge evidencia, evalúa predicados y devuelve un veredicto.

| Pieza | Qué dice | Origen |
|---|---|---|
| Veredicto | Uno de tres: **CONFIRMADA** (se cumplen todos los predicados obligatorios, al menos un corroborante y ningún predicado de descarte), **DESCARTADA** (basta un predicado de descarte) o **SIN_DATOS** (falta la fuente para algún obligatorio, o el componente no tiene telemetría en la ventana). | La división en tres valores con semántica AND/OR es [INF]. Su contenido sigue a OpenRCA, que excluye los casos sin telemetría o sin anomalía en la raíz [LIT OpenRCA §2.4, A.5], y al handler incierto que no mitiga [LIT RCACopilot p.680]. |
| Precedencia del veredicto | 1) Falta la fuente de algún obligatorio → SIN_DATOS. 2) Se cumple algún descarte → DESCARTADA. 3) Todos los obligatorios y al menos un corroborante → CONFIRMADA. 4) Si se cumplen a la vez predicados de confirmación y de descarte → DESCARTADA con marca `conflicto`, reportada como hallazgo; nunca CONFIRMADA. | [INF] (`recomend/modelo_comun.md`) |
| Salida | Trío obligatorio **componente + t_inicio + razón**, con componente y razón tomados de un vocabulario cerrado. | [LIT OpenRCA §2.1, §2.3, A.7] |
| Firma como (variable, umbral) | Cada predicado es una señal con operador, umbral y persistencia; un punto aislado no basta. | [LIT CloudPD en Notaro p.81:32; OpenRCA §6] |
| Indexación y recolección | La firma se dispara por síntoma o alerta de entrada y recolecta evidencia con acciones deterministas en una ventana `t_alerta − 30 min .. t_alerta + 5 min`. | [LIT RCACopilot §4.1; OpenRCA A.5 para ±30 min]; el margen de +5 min es [INF] |
| Raíz frente a síntoma | La raíz tiene **anomalía propia** (no solo heredada) y **empieza antes** que los síntomas: `t_inicio(raíz) ≤ t_inicio(síntomas)`, con 1 min de tolerancia. Los llamadores afectados se marcan como víctimas en la propagación. | [LIT OpenRCA A.5; FChain en Notaro p.81:28; RCACopilot p.684; ITBench Fig. 18] |
| Cambio de configuración | Si un cambio de configuración precede al primer síntoma y explica el error, la causa es la configuración y no el síntoma (por ejemplo, el crash loop que provoca). | [INF], derivada del principio temporal de OpenRCA y FChain |
| Papel del LLM | El LLM **solo elige entre las firmas CONFIRMADAS** o responde **"ninguna / no visto"**. No puede confirmar lo que el evaluador determinista dejó en SIN_DATOS. | [INF], inspirada en la opción "Unseen incident" [LIT RCACopilot Fig. 9] |
| Reparación | Cada firma trae acciones predefinidas, con precondición `veredicto == CONFIRMADA`. Se verifica con la alerta despejada y estable tras una espera. | [LIT Samir en Notaro p.81:35; RCACopilot p.680; ITBench C.5.2 p.29] |

#### Reglas del juez

* **Diagnóstico correcto = coincidencia exacta** de componente y razón sobre el vocabulario cerrado, con t_inicio dentro de ±1 min [LIT OpenRCA A.7, §4.1]. La razón es siempre obligatoria [INF, por la lección de OpenRCA Fig. 7, donde un caso con la razón equivocada contó como correcto].
* **Diagnóstico y reparación se juzgan por separado.** Que la alerta se despeje no valida el diagnóstico [LIT ITBench p.31].
* **Sin BLEU ni ROUGE:** no se juzga por similitud textual, porque en Ahmed et al. la correlación de Pearson entre métricas léxicas y el juicio de los dueños de incidentes fue inconsistente (de −0,42 a +0,62) y los autores concluyen que "pueden no ser coherentes" con la percepción humana, con una muestra pequeña [LIT Ahmed §VI-A, p.10]. Por eso Tider no las usa como juez. Un juez LLM solo haría falta para el campo de texto libre `condicion` [LIT ITBench p.30, planeado].
* **Consistencia:** temperatura 0 y N repeticiones, reportando la variación [LIT ITBench Tabla 15; RCACopilot §5.6].

#### Catálogo v1

| Modo de falla | Mecanismo de ChaosForge (etiqueta de evaluación) | Estado | Antecedente en la literatura |
|---|---|---|---|
| Servicio sin instancias | `scale_zero` | A validar con ChaosForge | ITBench PodFailure / ServiceFailure; regla de nivel servicio de OpenRCA A.2 |
| Configuración incorrecta | `wrong_port` | A validar con ChaosForge | ITBench (misconfiguration, CorruptImage); RCACopilot InvalidJournaling; X-Ray en Notaro |
| Dependencia lenta | `latency` | A validar con ChaosForge | ITBench NetworkDelay; dependencia inalcanzable en RCACopilot y OpenRCA A.4 |
| Saturación de CPU | `cpu_limit` | A validar con ChaosForge | ITBench HighCPU / CPUStress; OpenRCA "CPU overload" |
| Se cae al arrancar | — (sin inyector) | Declarada, no validada | OpenRCA "process termination"; ITBench CorruptDeployment |
| Sin memoria | — (sin inyector) | Declarada, no validada | ITBench MemoryResourceLimit / MemoryLeak; OpenRCA familia "mem" |

* Las dos declaradas **no tienen reparación verificada**: el Proponente no puede presentarlas como reparación del catálogo.
* `wrong_port`, `latency` y `cpu_limit` solo actúan sobre `cartservice` (decisión 14), así que su validación queda limitada a ese servicio (decisión 18).
* **Los predicados concretos de cada plataforma** (por ejemplo `replicas == 0`, `OOMKilled`, `stoppedReason`, throttling de CPU) y sus umbrales **son [INF]**: la literatura no define predicados de Kubernetes ni de ECS [nota de la sección 9.3 de `_bibliografia_firmas.md`]. Se tratan como hipótesis a validar.

#### Método de validación

Sigue el método de ITBench: inyección reproducible con un rol de inyección y otro de retiro, y verificación de que la alerta se dispara antes de evaluar [LIT ITBench C.3.1 p.22, C.4.1 p.26]. La aplicación a Tider es [INF].

1. Por cada firma validable, **inyectar la falla con ChaosForge y después retirarla**.
2. Comprobar que **la firma correcta da CONFIRMADA** y que **todas las demás dan DESCARTADA o SIN_DATOS**. El resultado es una matriz de confusión entre firmas; se reportan precision y recall [LIT Notaro §3.2].
3. **Repetir con fuentes ocultas** (por ejemplo, sin eventos o sin trazas) para verificar que la firma degrada a SIN_DATOS en lugar de adivinar [LIT ITBench p.7, C.3.1].
4. Calibrar los umbrales con media ± 3σ sobre una línea base sin falla [LIT OpenRCA A.5].

### 2.8 Modelo común de servicio e instancia (decisión 22, aceptada el 2026-11-09)

Fuente: `recomend/modelo_comun.md`. Estado del componente: **se construye** (adaptadores de plataforma; hoy el código lee eventos de Kubernetes vía Cloud Logging).

Las firmas se escriben **una sola vez** contra este modelo, y cada adaptador traduce su plataforma a sus campos. El modelo tiene cinco piezas:

| Pieza | Kubernetes | ECS | Campos principales |
|---|---|---|---|
| Servicio | Deployment | Service | `nombre`, `ubicacion`, `instancias_deseadas` (`spec.replicas` / `desiredCount`), `instancias_listas` (`status.readyReplicas` / `runningCount` con health check OK), `endpoints_listos` (direcciones ready del EndpointSlice / targets healthy del target group), `version_config`, `dependencias` (del Context Lake, no de la plataforma) |
| Instancia | Pod | Task | `id`, `estado`, `motivo_fin` (`OOMKilled`, `Error` / `stoppedReason`), `codigo_salida`, `limites` |
| Cambio | Evento ScalingReplicaSet, nueva generación del Deployment | Evento de servicio, nueva revisión de la task definition | `tiempo`, `servicio`, `tipo` ∈ {escalado, config_cambiada, imagen_cambiada}, `antes`, `despues` |
| Evento normalizado | Eventos de Kubernetes | Eventos de servicio ECS | `tiempo`, `servicio`, `instancia?`, `tipo` ∈ {instancia_terminada, sin_capacidad, health_check_fallido, imagen_no_disponible, otro} |
| Señal | Logs y métricas (Cloud Logging, Monitoring) | Logs y métricas (CloudWatch) | Log: `severidad`, `mensaje`. Métrica: `nombre` ∈ {latencia_p95, latencia_dependencia_p95, tasa_error, cpu_throttling, memoria_uso}, `destino` (solo para la latencia hacia una dependencia), `valor` |

Reglas:

* **Texto original y fuente.** Toda observación conserva su texto original y su fuente, para que Tider la cite (`S01…`) y el juez compruebe que la cita dice lo que la hipótesis afirma.
* **Campo vacío = SIN_DATOS.** Si una plataforma no entrega un dato, el campo queda vacío y la firma que lo necesita responde SIN_DATOS. Nunca se inventa el dato. En el replay de SIBI, si no se guardaron los eventos de ECS, faltan Cambio y Evento, y las firmas que dependen de ellos responden SIN_DATOS.
* **`terminaciones_en_ventana` en lugar de reinicios.** En Kubernetes un pod caído se reinicia en el mismo lugar y suma `restartCount`; en ECS la task se reemplaza por otra con otro id y no hay contador. Por eso el modelo cuenta, por servicio, cuántas instancias terminaron con error dentro de la ventana. La firma "se cae al arrancar" se escribe con esa medida. Se calcula desde Eventos históricos (K8s: `Killing`, `BackOff`, `OOMKilling` y terminaciones; ECS: tasks `STOPPED` dentro de la retención), porque el estado de los pods es solo actual.
* **Precedencia del veredicto [INF].** SIN_DATOS si falta una fuente obligatoria; si no, DESCARTADA si se cumple algún descarte; si no, CONFIRMADA con todos los obligatorios y un corroborante. Confirmación y descarte a la vez → DESCARTADA con marca `conflicto`, reportada como hallazgo (ver 2.7).

Campos que usa cada firma del catálogo v1: servicio sin instancias (`instancias_deseadas`, `instancias_listas`, `endpoints_listos`, Cambio de escalado, errores en quien lo llama); configuración incorrecta (Cambio `config_cambiada` antes del síntoma, logs de error de conexión); dependencia lenta (`latencia_dependencia_p95` con `destino` = la dependencia, y `latencia_p95` propia, sin errores de conexión); saturación de CPU (`cpu_throttling` + `latencia_p95`); se cae al arrancar (`terminaciones_en_ventana`, `codigo_salida` ≠ 0); sin memoria (`motivo_fin` = OOM).

---

## 3. Objetivos y no objetivos

### Objetivos

1. Entregar los 4 puntos del asesor dentro de las 5 capas, en el formato 01–05 del ejemplo veterinario (`_transcripcion.md:104-185`). Cada componente lleva su estado: existe, se construye o plan (decisión 19).
2. Describir solo el `AgenticEngine`, con autonomía "Restringida" y las listas "decide solo" / "requiere humano" (decisiones 1 y 6).
3. Presentar los 6 roles en una tabla, con 2 roles LLM y 3 puntos de llamada al LLM, y un orden fijo (decisión 8, N12).
4. Hacer que la evidencia sea la fuente de verdad en el código: un barrido sin filtro de catálogo, con cuota por nodo, y el Lake solo como mapa previo (decisiones 3 y 9).
5. Tener un catálogo de modos de falla con nombres genéricos y una firma de evidencia determinista por entrada y por plataforma (Kubernetes, ECS; decisión 20). El respaldo LLM se limita a diagnóstico, con filtro de verbos (decisión 4, N14).
6. Justificar el chunking por tipo de documento y por patrón de acceso. La validación queda como plan, sin fugas (decisiones 12 y 16, N3).
7. Prerregistrar una evaluación válida: ground truth aislado (decisión 17), reparto por pares servicio×mecanismo (decisión 19), filtro de caso válido no vacío, controles negativos con etiqueta, una sola comparación principal y potencia declarada (decisiones 13–15).
8. Declarar la independencia de nube como punto de extensión con un contrato a extraer (decisión 10), con el conocimiento de la app solo en el Lake y el acceso a nube y plataforma solo en adaptadores. Probar la generalidad con un incidente pasado de SIBI (ECS Fargate) en replay, fuera de la estadística (decisión 20).
9. Afirmar solo lo que la evaluación cubre (decisión 18): "Tider localiza fallas de disponibilidad (`scale_zero`) en los 12 servicios; las fallas sutiles (`wrong_port`, `latency`, `cpu_limit`) solo se evaluaron sobre `cartservice`". El informe reconoce que `scale_zero` es casi trivial con barrido de eventos.

### No objetivos

* Remediación o ejecución de comandos en el clúster: queda para una iteración futura (decisión 1).
* Sistema multiagente o coordinador. Es un agente con varios roles.
* Un puntaje probabilístico calibrado. Las hipótesis se presentan por orden y cobertura (decisión 19).
* Fallas múltiples simultáneas: ChaosForge permite un solo experimento activo.
* Construir adaptadores para AWS o Azure en esta iteración (decisión 10). En particular, **ninguna conexión en vivo a AWS o Azure**: SIBI solo entra en replay (decisión 20).
* Plataformas sin contenedores orquestados (máquinas virtuales, Lambda, Cloud Run) (decisión 20).
* Correr la campaña antes de la reunión con el asesor (decisión 7).
* Un barrido de tamaños de chunk, o comparar más de dos recuperadores antes de tener un piloto que muestre fallos del léxico.
* Generalizar los mecanismos distintos de `scale_zero` más allá de `cartservice`. Se declara como siguiente paso de la campaña (decisión 18).
* Juez de otra familia antes de tener un conjunto de mutaciones que permita medirlo.

---

## 4. Alternativas evaluadas

| Alternativa | Rechazada por | Razón | Lo que se conserva |
|---|---|---|---|
| **Mapa de un solo culpable** | Autor | Esconde las víctimas y la incertidumbre. En C09 (etiqueta: desconocido) el agente señaló 3 veces a `frontend` como el componente con la única señal de error, aunque su texto admitía que no demostraba la causa, y el juez aprobó ese hallazgo. Es un error de abstención y localización frente a la etiqueta, no una afirmación explícita de causa raíz. | Hipótesis ordenadas con estado y rol por nodo. Se muestra el orden, no probabilidades (B4, M2). |
| **Reparaciones solo con el LLM** | Autor | Texto libre sin control. Puede proponer comandos que cambian el clúster y no tiene contra qué evaluarse. | El LLM queda como respaldo explícito, solo para diagnóstico, con filtro de verbos (decisión 4, M4). |
| **Conservar el grafo del núcleo como fase 2** | Autor | Otro dominio (OTel) y otra autonomía (tiene un ejecutor). Dos sistemas vuelven incoherente el informe. | Se archiva dentro del repositorio, excluido del informe. El baseline de reglas sale de `console/baseline.py` y del verificador de firmas (B3, C16). |
| **Lake como fuente de verdad** | Autor | El Lake no tiene síntomas observados. Si decide qué se consulta, vuelve circular la evidencia. | Mapa previo. Las discrepancias son hallazgos (decisión 3). |
| **Investigación sin barrido previo** | Autor | El LLM puede no consultar algunos nodos, y entonces no hay estado garantizado por nodo. La evidencia queda a merced del orden en que el LLM elige herramientas. | Investigación adaptativa después del barrido (decisión 9). Los revisores piden cuota por nodo y presupuesto propio (N6). |
| **MCP como capa de abstracción multi-nube** | Autor | MCP es un protocolo de transporte, no un contrato de dominio. No normaliza severidad, eventos ni estado entre nubes. | `logging_mcp` queda como transporte posible dentro de un adaptador. La independencia la da el contrato de evidencia, que hay que extraer (decisión 10, N1). |
| **Preguntas de Hit@k redactadas por el equipo** | Autor | El equipo conoce las respuestas, así que las preguntas salen sesgadas. Además no se parecen a lo que el Investigador envía de verdad. | Consultas generadas desde señales crudas (decisión 16). Los revisores advierten que esas señales nombran al servicio: enmascarar y usar las consultas de la traza (N3). |
| **Juez del mismo modelo** | Autor | Comparte los sesgos del Investigador. En C09 aprobó un hallazgo que señalaba a `frontend` cuando la etiqueta era desconocido (error de abstención, no de causa raíz explícita); el juez debe exigir más. | El juez del mismo modelo queda como brazo de comparación para medir si cambiar de modelo aporta (N5, C15). |
| Congelar el código y entregar solo documentos | Síntesis (parcial) | Deja la fuga de ground truth y la falta de firmas. | Se adopta como etapa 0, con etiquetas de estado (decisión 7). |
| Catálogo nombrado por el inyector (`scale_zero`…) | Design (rondas 1 y 2); autor (decisión 19) | Es una hoja de respuestas. La decisión 4 lo reintrodujo. | Nombres genéricos de K8s, con el mecanismo como etiqueta de evaluación (N14). |
| Confianza verbalizada por el LLM | Design, implementation-readiness; autor (decisión 19) | No se calibra con n≈30, y el juez tiene prohibido producirla. | Orden + cobertura. |
| Búsqueda híbrida con 4 variantes en la etapa 0 | Zoom-out, inventive-catalyst | Corpus de unos 25 documentos con acceso por clave. El léxico ya ganó (p=0,016; medido el 6/11 con una versión anterior del buscador; debe volver a medirse con el código actual). | Acceso por clave para topología, fichas y catálogo. Búsqueda solo para postmortems. Como mucho 2 variantes (C14). |
| Archivar en `project/documentation/archivo/` | Structural, design, codebase-details; autor (decisión 19) | Rompe el arranque de la consola, las pruebas y el benchmark, y saca la documentación del repositorio. | Archivo dentro de `tider/docs/archive/`, con un puntero afuera (N4). |
| Juez de otra familia directamente | Zoom-out, design | Requiere un adaptador nuevo y gobierno de datos, y no se puede medir sin mutaciones. | Primero otro modelo del mismo proveedor; otra familia si la métrica lo justifica (N5). |
| Estratificar el reparto en esta iteración para tener fallas sutiles no vistas | Autor (decisión 18) | Exige habilitar mecanismos en otros servicios y deja celdas pequeñas. | Afirmación acotada; la extensión queda como siguiente paso de la campaña (N2, C12). |
| Solo Kubernetes, SIBI fuera de alcance | Autor (decisión 20) | La app real objetivo, SIBI, corre en AWS ECS Fargate, sin Kubernetes. Limitarse a Kubernetes dejaría fuera el caso real. | Kubernetes como plataforma principal y piloto estadístico; ECS como extensión, probada con un incidente de SIBI en replay. |

---

## 5. Decisiones clave y etapas

### 5.1 Las 22 decisiones (registro único, con estado)

Estado de la decisión: **aceptada** · **propuesta** · **pendiente**. Estado del componente: **existe** · **se construye** (etapa 1) · **plan** (etapa 2 o posterior). "—" indica que la decisión no corresponde a un componente.

| # | Decisión | Estado | Componente | Capa del blueprint | Observación |
|---|---|---|---|---|---|
| 1 | Solo asesor; la remediación queda para el futuro | Aceptada | Existe (`escalate`, `executed=False`) | 04 | — |
| 2 | Hipótesis ordenadas: causa y víctimas, con evidencia, rol y cobertura | Aceptada | Plan (hoy una sola hipótesis) | 02 / 04 | Decisión 19: sin "confianza"; orden + cobertura. Falta una sola definición de cobertura (B4, N13). |
| 3 | Evidencia = verdad; Lake = mapa previo; 3 estados; discrepancia = hallazgo | Aceptada | Existe en parte (filtro por catálogo); el barrido sin filtro se construye | 03 | "Sano" requiere el predicado de N8. |
| 4 | Catálogo de modos de falla cerrado, por firma, + respaldo LLM de diagnóstico | Aceptada | Se construye (firmas de `scale_zero` y filtro de verbos) | 03 / 04 / 05 | Decisión 19: entradas por modo de falla genérico de Kubernetes (N14). La decisión 21 da la definición operativa de la firma (B1). Alcance del filtro (N12). |
| 5 | Evaluadores κ | Pendiente | — | 05 (limitación) | Declarada como limitación. Decisión 20: Alberto y Jose (cláusula 11) son candidatos; M5 pasa a parcial. |
| 6 | Un solo motor; el grafo se archiva | Aceptada | Se construye (la consola importa el grafo) | Fuera de alcance | Decisión 19: el archivo va dentro del repositorio. Pasos previos de N4. |
| 7 | Reunión informativa; basta la etapa 0 | Aceptada | — | — | Exige las etiquetas de estado (N1, decisión 19). |
| 8 | 6 roles, 2 LLM; juez de otro modelo, medido por falsa aprobación | Aceptada | Se construye (`judge_model`); otra familia: plan | 02 / 05 | Orden (N12), métrica (N5). |
| 9 | Barrido mínimo fijo + investigación adaptativa | Aceptada | Existe en parte (barrido global con tope); la cuota por nodo se construye | 03 Herramientas | Cuota, presupuesto y severidades (N6). |
| 10 | Independencia de nube: contrato a extraer; MCP es transporte | Aceptada (punto de extensión) | Plan (hoy `EvidenceProvider` es una clase concreta y los eventos K8s llegan por Cloud Logging) | 03 + "Puntos de extensión" | Redacción de la decisión 19. |
| 11 | Lake: documentos actuales + fichas + guías + postmortems | Aceptada | Plan | 03 Conocimiento | Congelar las fichas (N7). |
| 12 | Chunking por tipo + metadatos + búsqueda híbrida | Propuesta | Plan | 03 + Anexo B | Límites del Lake (N9), patrón de acceso (C14). |
| 13 | Protocolo contra la fuga por postmortems | Propuesta | Plan | Anexo A | "Visto" por par, citas tipadas (N2, N7). |
| 14 | Capacidad real de ChaosForge (hecho verificado el 2026-11-08) | Aceptada | Existe | 05 (limitaciones) | Mecanismos no desplegados, precondiciones. |
| 15 | Reparto historial / no vistos / control | Aceptada (depende de la 13, propuesta) | Plan | Anexo A | Decisión 19: se expresa como pares servicio×mecanismo. |
| 16 | Validación del chunking con Hit@k/MRR | Propuesta | Plan | Anexo B | Fugas y ajuste sobre la prueba (N3). |
| 17 | Aislar `/api/evidence` y `/api/state` en otro proceso o puerto | Aceptada | Se construye | 05 | Resuelve B2 en la decisión. Falta implementarlo y probar el no acceso. |
| 18 | Alcance de la evaluación (opción c): afirmación acotada + extensión como siguiente paso | Aceptada | — | 05 / Anexo A | Resuelve N2. Ver la nota de abajo. |
| 19 | Cambios de redacción de la ronda 2 | Aceptada | — | Todas | Aplicados en este brief (sección 5.5). |
| 20 | Alcance del producto (opción a): contenedores orquestados, Kubernetes principal y ECS como extensión; conocimiento de app en el Lake y nube/plataforma en adaptadores; SIBI en replay, fuera de la estadística | Aceptada | Plan (adaptadores de plataforma y de CloudWatch; hoy acoplado a Online Boutique y GCP) | 03 + "Puntos de extensión" / 05 | Base legal: Carta de Autorización SIBI (cláusulas 2, 3, 5, 6, 10, 11). Ver la sección 2.6. |
| 21 | Firmas operativas y catálogo v1: veredicto CONFIRMADA / DESCARTADA / SIN_DATOS; trío componente + t_inicio + razón; raíz con anomalía propia y anterior a los síntomas; cambio de configuración previo = causa; el LLM solo elige entre firmas confirmadas o "ninguna / no visto"; 4 firmas a validar con ChaosForge y 2 declaradas | Aceptada (2026-11-09) | Se construye | 03 / 04 / 05 | Resuelve B1 en la decisión. Los predicados concretos de K8s y ECS son inferencia y se validan inyectando y retirando la falla. Ver la sección 2.7. |
| 22 | Modelo común de servicio e instancia (Servicio, Instancia, Cambio, Evento, Señal), con texto original + fuente, SIN_DATOS ante campo vacío y `terminaciones_en_ventana` | Aceptada (2026-11-09) | Se construye | 03 + "Puntos de extensión" | Cierra el pendiente del contrato servicio/instancia de la decisión 20. Ver la sección 2.8. |

**Afirmación de la evaluación (decisión 18).** El informe afirma, para esta iteración: "Tider localiza fallas de disponibilidad (`scale_zero`) en los 12 servicios; las fallas sutiles (`wrong_port`, `latency`, `cpu_limit`) solo se evaluaron sobre `cartservice`".
* Se reconoce que, con barrido de eventos, `scale_zero` es casi trivial, porque `ScalingReplicaSet` nombra al servicio.
* Extender las fallas sutiles a otros servicios es el siguiente paso de la campaña.
* Nota de redacción: de los 12 Deployments, `loadgenerator` es caso de control negativo (N10). La frase tiene que precisar si cuenta 11 o 12 servicios.

### 5.2 Estado por componente (decisión 19)

| Componente | Estado | Detalle |
|---|---|---|
| `AgenticEngine` (consola) | Existe | Único motor descrito en el informe. |
| Grafo del núcleo (`LabEngine`) | Existe; se archiva (se construye) | La consola lo importa al arrancar (`console/api.py:14`). |
| Cartógrafo | Existe en parte | La topología entra en el prompt. |
| Recolector (barrido) | Existe en parte; se construye la cuota por nodo | Hoy es una consulta global con tope y filtro por catálogo. |
| Investigador | Existe | — |
| Proponente con catálogo de modos de falla | Se construye | Catálogo v1 (decisión 21): 4 firmas a validar con ChaosForge y 2 declaradas, sin reparación verificada. |
| Verificador de firmas (veredicto de tres valores) | Se construye | Decisión 21, sección 2.7. |
| Modelo común de servicio e instancia en los adaptadores | Se construye | Decisión 22, sección 2.8. |
| Respaldo LLM del Proponente | Se construye | Con filtro de verbos y su prueba. |
| Juez con el mismo modelo | Existe | — |
| Juez con otro modelo (`judge_model`) | Se construye | Otro modelo del mismo proveedor. |
| Juez de otra familia | Plan | Solo si la métrica con mutaciones lo justifica. |
| Reportero con estado + rol por nodo | Existe en parte; `ranked_hypotheses[]`: plan | — |
| Predicado de "sano confirmado" | Plan (sin decidir) | Ver N8. |
| Aislamiento del ground truth | Se construye | Decisión 17. |
| Traza por corrida | Se construye | M9. |
| Baseline sin LLM (barrido + verificador de firmas) | Se construye | `console/baseline.py` existe. |
| Contrato de evidencia | Plan | "Contrato a extraer" (decisión 10). |
| Lake actual (Chroma + compuerta léxica) | Existe | Límites de N9. |
| Lake V3, chunker por tipo, versión congelada | Plan | N9. |
| Benchmark de chunking existente (p=0,016; medido el 6/11 con una versión anterior del buscador; debe volver a medirse con el código actual) | Existe | Su corpus se congela antes de archivar (se construye). |
| Validación del chunking (decisión 16) | Plan | N3. |
| Replay con `FrozenTools` | Existe; superconjuntos por ventana: plan | N11. |

### 5.3 Los 6 roles (orden corregido)

| # | Rol | ¿LLM? | Estado | Nota de la ronda 2 |
|---|---|---|---|---|
| 1 | Cartógrafo | No | Existe en parte: la topología entra en el prompt | Corre en paralelo con el Recolector, no antes que él. |
| 2 | Recolector de evidencia (barrido) | No | Existe en parte: consulta global con tope | No recibe el mapa previo como filtro. Cuota por nodo (se construye). |
| 3 | Investigador | Sí | Existe | Recibe la tabla de 12 nodos y pide las líneas crudas. |
| 4 | Proponente de reparación | Catálogo: no. Respaldo: sí | Se construye | Tercer punto de llamada al LLM. El filtro de verbos aplica al respaldo. |
| 5 | Juez / guardián | Sí, otro modelo | Existe con el mismo modelo; otro modelo se construye | Corre después del Proponente. Pide la re-investigación al Investigador. Agrega la regla "no solo documentos". |
| 6 | Reportero | No | Existe en parte | Estado + rol por nodo, más las discrepancias. |

### 5.4 Mapa de documentos

* Se mantiene el mapa de la ronda 1, con estos cambios:
  * El archivo va dentro del repositorio, en `tider/docs/archive/remediacion/`, excluido del informe y de la ingesta, y con un puntero en `project/documentation/archivo/` (decisión 19; reemplaza la ubicación de la decisión 6).
  * Antes de mover nada, se hacen los pasos de N4.
* Todas las decisiones van a un único registro, `docs/decisions.md`, con IDs únicos, una tabla de correspondencias (auditoría 1–22 ↔ D01…) y las columnas estado y "depende de".
* Los documentos nuevos del Lake viven fuera de `tider/docs`, en `Context Lake/V3/{fichas,guias,postmortems,catalogo}/`. Llevan front matter con los metadatos de la decisión 12 y un manifiesto con hash. V1 queda marcado como reemplazado.
* El informe cita los artefactos generados (`summary.json`, commit) en lugar de copiar cifras (M12).

### 5.5 Cambios de redacción sin código (aceptados en la decisión 19, aplicados en este brief)

1. **Etiquetas por componente:** existe / se construye / plan (secciones 5.1 a 5.3).
2. **Decisión 2:** sin "confianza"; "ordenadas, con evidencia, rol y cobertura".
3. **Decisión 4:** catálogo organizado por modo de falla genérico de Kubernetes; el mecanismo de ChaosForge es solo etiqueta de evaluación.
4. **Decisión 10:** "contrato a extraer". `EvidenceProvider` es hoy una clase concreta, los eventos K8s llegan por Cloud Logging y MCP es transporte.
5. **Decisión 15:** el reparto se expresa como pares servicio×mecanismo. Reservar cart×{`latency`, `wrong_port`} sin postmortem no está decidido.
6. **Vocabulario de estados único** (ver el encabezado).
7. **Ubicación del archivo:** dentro del repositorio, con un puntero en `project/documentation/archivo/`.

La decisión 17 (aislamiento del ground truth), que esta sección pedía agregar, ya está aceptada.

### 5.6 Etapas

**Etapa 0: informe para la reunión (sin cambios de producto).**
* Blueprint 01–05 sobre el `AgenticEngine` actual. Cada pieza lleva su estado: existe / se construye / plan. Incluye "Fuera de alcance" y "Puntos de extensión".
* Tabla de los 6 roles y tabla de estado por componente (secciones 5.2 y 5.3).
* Chunking: estado actual, estrategia por tipo y por patrón de acceso, la justificación del benchmark existente (citado en `22698d1`) y la validación de la decisión 16 como plan corregido.
* Anexo A, estadística:
  * reanálisis por caso de E5 (Wilson, McNemar exacto, p95 por caso, potencia);
  * plan de campaña de una página, prerregistrado: unidad, etiqueta, filtro no vacío, reparto por pares, controles con etiqueta, una comparación principal y horas estimadas de GKE.
  * tamaño de muestra declarado (N15): con decenas de inyecciones independientes, la McNemar del Lake con y sin postmortems solo detecta efectos grandes (~92 pares para 20 pp, ~168 para 15 pp).
* Glosario y pasada terminológica.
* Limitaciones declaradas:
  * κ pendiente;
  * alcance de la evaluación (decisión 18): `scale_zero` en los servicios de la tienda, fallas sutiles solo sobre `cartservice`, y `scale_zero` casi trivial con barrido de eventos;
  * circularidad del oráculo;
  * `/api/evidence` en el mismo puerto que lee Tider, hasta implementar la decisión 17;
  * independencia de nube no probada.

**Etapa 1: cambios mínimos para una evaluación válida.**
* Cortar la dependencia de la consola con el grafo, congelar el corpus del benchmark y archivar (N4).
* Aislar el ground truth (decisión 17, aceptada), con una prueba de no acceso.
* Tabla determinista de firmas con fixtures, sobre el modelo común (decisiones 21 y 22). Validar las 4 firmas del catálogo v1 inyectando y retirando cada falla, y repetir con fuentes ocultas; las 2 declaradas quedan como "declaradas, no validadas" (B1).
* Barrido sin filtro de catálogo, con cuota por nodo y presupuesto propio (N6).
* Filtro de verbos en el respaldo LLM, con su prueba (M4).
* Traza por corrida: modelos del Investigador y del juez, SHA del prompt, versión del catálogo, IDs del Lake, llamadas a `context_search`, firma sí/no con sus IDs de evidencia y cobertura por nodo (M9).
* Verificador de firmas + barrido como baseline sin LLM (C16).
* Configuración `judge_model` en la consola, con otro modelo del mismo proveedor (N5).

**Etapa 2: Lake ampliado, mapa y campaña.**
* Chunker por tipo, metadatos persistidos, límites del Lake y versión congelada (N9).
* Fichas congeladas con hash, guías de diagnóstico y postmortems en dos capas (N7).
* `ranked_hypotheses[]` con `role`, estados por nodo y discrepancias, con `schema_version` y `component` como alias (M10).
* Campaña:
  * habilitar `wrong_port` y `latency` sobre `cartservice` (este último con el proxy);
  * siguiente paso declarado (decisión 18): extender las fallas sutiles a otros servicios;
  * grabar superconjuntos por ventana;
  * reparto por pares servicio×mecanismo;
  * controles negativos;
  * una comparación principal.
* Conjunto de mutaciones para el juez y tres brazos pareados. Otra familia solo si la métrica la justifica.
* Validación del chunking con consultas de la traza y nombres enmascarados.
* κ con evaluadores externos, si se consiguen.

**Pendientes abiertos:**
* evaluadores para κ (decisión 5);
* si "sano confirmado" entra con el predicado de N8 o la entrega queda en dos estados;
* si se mantiene la promesa de "≥5 tipos de fallo" de H6 o se reescribe (la decisión 18 acota la afirmación a `scale_zero` en todos los servicios y fallas sutiles solo en `cartservice`);
* si la frase de la decisión 18 cuenta 11 o 12 servicios (`loadgenerator` es control);
* qué proveedor usa el juez de otra familia y bajo qué política de datos;
* qué incidente pasado de SIBI se usa para el replay (dentro de 14/04/2026–11/10/2026 y con causa conocida) (decisión 20);
* si existen eventos de servicio ECS históricos (solo si se enviaban con EventBridge hacia CloudWatch Logs; la API conserva 100) y si se autorizan, porque la cláusula 3 no los incluye (decisión 20).

---

## 6. Referencias

Bibliografía usada para las firmas operativas (decisión 21). Los PDFs están en `project/investigacion/bibliografia/`; el análisis con citas por sección y página está en `recomend/_bibliografia_firmas.md`.

1. Xu, J. et al. *OpenRCA: Can Large Language Models Locate the Root Cause of Software Failures?* ICLR 2025. Archivo: `13411_OpenRCA_Can_Large_Langua.pdf`. Aporta el trío componente / t_inicio / razón, el vocabulario cerrado, el exact-match con ±1 min y el criterio de "sin datos".
2. Chen, Y. et al. *Automatic Root Cause Analysis via Large Language Models for Cloud Incidents* (RCACopilot). EuroSys '24, pp. 674–686. Archivo: `3627703.3629553.pdf`. Aporta los handlers deterministas por tipo de alerta y la opción "Unseen incident" del LLM.
3. Ahmed, T. et al. *Recommending Root-Cause and Mitigation Steps for Cloud Incidents using Large Language Models*. ICSE 2023 (arXiv 2301.03797). Archivo: `2301.03797v2.pdf`. Muestra que la correlación entre BLEU/ROUGE y el juicio de los dueños de incidentes es inconsistente (Pearson de −0,42 a +0,62, muestra pequeña; §VI-A, p.10).
4. Jha, S. et al. *ITBench: Evaluating AI Agents across Diverse Real-World IT Automation Tasks*. Preprint arXiv 2502.05352, 2025. Archivo: `2502.05352v1.pdf`. Aporta la inyección y retiro reproducibles, la verificación de la reparación con alerta despejada y estable, y el juicio separado de diagnóstico y reparación.
5. Notaro, P., Cardoso, J. y Gerndt, M. *A Survey of AIOps Methods for Failure Management*. ACM TIST 12(6), art. 81, 2021. Archivo: `3483424.pdf`. Aporta la terminología fault/error/failure, CloudPD (firma = variable + umbral) y FChain (orden temporal).
6. Prasad, P. y Rich, C. (Gartner). *Market Guide for AIOps Platforms*. G00340492, 2018. Archivo: `Market-Guide-for-AIOps-Platforms-Gartner-Reprint-1.pdf`. Visión de mercado: causa raíz accionable y topología imprescindible.
7. Faros AI. *AI Engineering Report 2026: The Acceleration Whiplash*. Informe de industria, 2026. Archivo: `AI_Engineering_Report_2026_The_Acceleration_Whiplash_Faros (1).pdf`. Solo motivación: más incidentes por cambio con alta adopción de IA.
