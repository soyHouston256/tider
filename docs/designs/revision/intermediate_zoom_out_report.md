# Goldfish Review Report: Etapa 8 (Zoom Out intermedio)

**Target:** `/Users/maxhoustonramirezmartel/code/utec/5/integrador/project/code/tider/docs/designs/tider-diseno-piloto.md` (`1-727`)
**Modo:** REVIEW
**Estándar:** `/Users/maxhoustonramirezmartel/.claude/plugins/cache/egm/egm/0.1.1/resources/document_standards/zoom-out-standard.md`
**Informes previos considerados:** `revision/zoom_out_report.md`, `revision/comprehension_report.md`, `revision/critic_report.md`
**Restricción respetada:** el revisor no leyó nada bajo `ground_truth/` ni `ENTREGA_*`.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

**Resumen por severidad:** 1 Blocker, 9 Major y 2 Nit.

**Veredicto:** necesita revisión. El problema no es que falten piezas, sino que sobran. Varias mitigaciones propuestas en las etapas 5 a 7 duplican o agrandan maquinaria que deja de hacer falta si primero se recorta el alcance del objetivo.

## Qué agregaron las etapas previas

- **Comprehension (Etapa 6):** no agrega alcance. Casi todo son contradicciones y términos sin definir. Los hallazgos más útiles son el 1 (CUJ 2 contra el predicado), el 4 (falta un resumen de una línea por firma), el 5 (`Arista.estado` sin dominio), el 7 (historial y control sin definir) y el 9 ("falla confirmada", la anomalía y `t0` sin definir). Todos se resuelven con texto, sin componentes nuevos.
- **Critic (Etapa 7):** repite cinco hallazgos que ya estaban en la Etapa 5 (M1, M4, M6, M9 y M10). Lo que agrega se divide en dos grupos:
  - **Consistencia interna barata** (M5, M7, M8, M24, M25 y M26): hay que conservarla.
  - **Alcance documental y de pruebas nuevo** (M16, M17, M18, M21, M22, M23 y N9): es lo que ensancha el alcance.
- **Inventive Catalyst (Etapa 5):** es el que más ensancha el alcance. Propone:
  - un `BundleAdapter`;
  - un índice IP->entidad versionado en el tiempo;
  - conteos agregados por cubeta;
  - preagregación;
  - un sondeo de latencia propio;
  - estadística con bootstrap por clúster;
  - una métrica de víctimas;
  - namespaces paralelos.

## Prioritized Findings (Blockers -> Major -> Nits)

### Z1. ClusterIP sin registrar (B1): resolverlo con algo más chico - Severity: Blocker
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * líneas 179, 204, 480 y 487 del objetivo;
  * `zoom_out_report` B1;
  * `critic_report` M4.
* **Discrepancy Description:** el Blocker es real. Según RB-01 (líneas 45-55), los llamadores nombran a su destino como `ClusterIP:puerto`, y el puerto por sí solo es ambiguo:
  * 50051 lo usan payment y shipping;
  * 6379 lo usan redis-cart y el proxy.

  Hoy el registrador no guarda los Services, y el RBAC no da permiso sobre `services`. La mitigación del Catalyst pide un índice versionado en el tiempo, que combine ClusterIPs con IPs de pod y que usen cuatro componentes. Es más de lo necesario.
* **Rationale & Recommendation:** **shrink.**
  * Agregar `services` a la instantánea y a `deploy/reader-rbac.yaml`.
  * Construir una sola tabla `ClusterIP:puerto -> servicio` por ventana. No hace falta versionarla: el Service conserva su ClusterIP aunque tenga 0 réplicas (RB-01 l. 46).
  * Atribuir un error solo si coinciden la IP **y** el puerto. Si no se resuelve, el error no se atribuye a nadie y el resultado es `sin_datos`. Nunca atribuir solo por el puerto.
  * Las IPs de pod quedan como respaldo opcional fuera del MVP.
  * Agregar una prueba con fixture de PM-04 para la colisión en 50051.

### Z2. CUJ 2 contra "sano confirmado": basta con reformular - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * líneas 108-112 y 126 del objetivo;
  * Catalyst M8;
  * Critic M1 y M2;
  * Comprehension 1.
* **Discrepancy Description:** el Catalyst propone atribuir los errores por la tupla (llamador, dirección). El Critic agrega plantillas de ruido tomadas de las fichas y reglas para cadenas de error anidadas. Ninguna de las dos cosas hace falta: por la cláusula 3 (tráfico), redis-cart queda en `sin_datos` con `wrong_port` de todos modos.
* **Rationale & Recommendation:** **shrink.**
  * La cláusula 2 debe decir "ningún error *atribuido* a la entidad". Con la regla de Z1 alcanza.
  * Reemplazar "cero errores propios" por "sin anomalía respecto de la línea base previa a t0". Esa línea base ya está diseñada (l. 193).
  * El "Then" del CUJ 2 pasa a "redis-cart no aparece como causa (sano o sin datos)".
  * Falta verificar en una corrida real el formato del error de `wrong_port`.
  * **Drop/defer:** las plantillas de ruido en las fichas, porque acoplarían el estado al Lake, y el parseo general de cadenas anidadas.

### Z3. El objetivo empaqueta las etapas 1 y 2 del RFC sin un punto go/no-go - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * línea 6;
  * objetivos 7, 8 y 11;
  * §10;
  * ítems 23-27 y 37b;
  * `zoom_out_report` M1.
* **Discrepancy Description:** la Etapa 1 del RFC son "cambios mínimos para una evaluación válida" (RFC l. 728-736). Varias piezas del objetivo pertenecen en realidad a la Etapa 2 (l. 738-751):
  * el Lake por tipo;
  * el mapa;
  * los brazos del juez;
  * el chunking.

  VALIDACION_CODEX recomienda cerrar primero un flujo vertical, porque hay una sola persona trabajando (l. 332 y 335). Además, Comprehension y Critic agregan trabajo documental (M18, M21, M22 y M23) sobre secciones que primero deberían recortarse.
* **Rationale & Recommendation:** **keep, más estricto.** Declarar un MVP y poner un go/no-go explícito después de `--validate-signatures`, la matriz de confusión de firmas. El MVP contiene:
  * registrador, barrido y estado;
  * verificador con 4 firmas;
  * contrato v2;
  * Proponente determinista;
  * reglas fijas del juez;
  * aislamiento del ground truth;
  * traza, protocolo, runner y score.

  Lo demás pasa a un segundo corte (ver "Alcance mínimo coherente").

### Z4. Proponente con respaldo LLM y filtro de verbos: diferirlos, no endurecerlos - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * §7 (l. 259-265);
  * regla 4 del juez (l. 273);
  * ítem 19;
  * NFR l. 437;
  * Zoom Out M2;
  * Critic M15 y M24;
  * Comprehension 2 y 14.
* **Discrepancy Description:** las etapas previas proponen tres cosas sobre una pieza que el MVP no necesita:
  * ampliar la denylist o cambiarla por un allowlist;
  * fijar los reintentos;
  * definir el "runbook más cercano".

  Los pasos de solo lectura ya existen en cada runbook (RB-01 l. 88-110). Lo que sí bloquea el piloto es el defecto de la regla 4: rechazaría el `kubectl scale` de RB-01, y entonces el CUJ 1 no se podría pasar.
* **Rationale & Recommendation:**
  * **keep:** la regla 4 se aplica solo a `tipo = diagnostico_no_verificado`.
  * **shrink:** en el MVP, el Proponente es determinista:
    * con una firma CONFIRMADA y validada, devuelve la acción de catálogo;
    * en otro caso, devuelve los pasos de solo lectura del runbook con los parámetros rellenados, etiquetados como "sugerencia no verificada";
    * con razón `desconocida`, devuelve un paso genérico de lectura del namespace.
  * **defer:** el respaldo LLM. Si vuelve, debe hacerlo con un allowlist.

  Así quedan 2 roles LLM y 2 puntos de llamada, y Critic M24 se resuelve solo. **Esto se aparta de la decisión 4 y redefine qué califica κ, así que requiere el acuse del autor.**

### Z5. La comparación confirmatoria del juez no mide el problema raíz - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * objetivo 6;
  * l. 95-99;
  * §12 `judge_set.py`;
  * ítem 35;
  * Catalyst M10;
  * Critic M10.
* **Discrepancy Description:** el problema declarado (l. 34) ya lo cubren los umbrales de Wilson sobre la exactitud de la primera hipótesis. La prueba prerregistrada compara el juez contra "aprobar todo", y su resultado depende de la proporción de verdaderos y falsos y de la receta de mutaciones. Los arreglos propuestos agregan estadística a una pregunta secundaria:
  * Youden;
  * bootstrap por clúster;
  * un análisis de potencia de unos 92 pares.

  El RFC (l. 749) pide "otra familia solo si la métrica la justifica".
* **Rationale & Recommendation:** **shrink.**
  * El resultado principal es la exactitud con Wilson contra el umbral.
  * El juez se reporta de forma descriptiva: tasa de falsa aprobación y de falso rechazo con Wilson, separando candidatos naturales de fabricados.
  * Si se conserva una prueba confirmatoria, que sea McNemar solo sobre candidatos naturales.
  * **Drop:** Youden y el bootstrap por clúster.
  * **Keep:** el adaptador `OpenAILLM`, por la decisión 23.
  * **Defer:** el brazo del mismo proveedor.
  * Esto también requiere el acuse del autor (decisiones 8 y 23).

### Z6. Repeticiones y orden por LLM de firmas: costo fijo para un caso raro - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * l. 80;
  * regla 3 del juez;
  * ítem 33;
  * NFR;
  * Catalyst M9;
  * Critic M5 y M9.
* **Discrepancy Description:** con un solo experimento activo (l. 65), que se confirme más de una firma solo puede deberse a un defecto de firma. El caso conocido es `latency` con `REDIS_ADDR=chaosforge-proxy`. Aun así, el plan repite 3 veces todos los casos y agrega una regla de colapso y `justificacion_orden`.
* **Rationale & Recommendation:**
  * **keep:** el predicado de descarte de Critic M5 (redirección a un proxy alcanzable), como una línea en `catalog_v1.yaml`.
  * **shrink:** repetir solo los casos con más de una firma confirmada, con mayoría de 3 prerregistrada, y reportar qué fracción de casos llega a ese punto.
  * **defer:** el desempate determinista en tres niveles del Catalyst.

### Z7. Barrido muestreado: los conteos agregados completos son más de lo necesario - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * l. 48, 193, 197, 274 y 436;
  * Catalyst M11 y M12;
  * Critic M13.
* **Discrepancy Description:** un barrido muestreado no puede certificar "sano". Las mitigaciones propuestas resuelven eso con más maquinaria de la necesaria:
  * conteos por cubeta;
  * muestreo estratificado;
  * preagregación en el registrador.
* **Rationale & Recommendation:** **shrink.**
  * Hacer dos lecturas por servicio, cada una con su propia cuota:
    * `severity>=WARNING`, como indica RB-01 l. 34;
    * INFO aparte, solo para el conteo de tráfico K.
  * Un resultado `truncado` nunca da sano.
  * Reemplazar "completa" por "con cobertura declarada".
  * Contar cada traza de error como un solo evento (RB-01 l. 67).
  * **Drop/defer:** las cubetas agregadas, las métricas basadas en logs y la preagregación.

### Z8. Alcance especulativo dentro del propio objetivo - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * ítems 1, 3, 5, 12, 23, 26, 27 y 33-38;
  * l. 179 y 690;
  * §10.
* **Discrepancy Description:** varias piezas del objetivo no hacen falta para el piloto. Cada punto lleva su clasificación:
  1. **La nueva interfaz `EvidenceAdapter`:** duplica `EvidenceProvider` (`providers/__init__.py:9`) y `EvidenceSource` (`service.py:16`), y ECS está fuera de alcance. **Shrink:** conservar el modelo común (decisión 22), dejar `gke.py` como módulo concreto y extraer `EvidenceProvider` cuando exista un segundo adaptador.
  2. **El registrador continuo con 48 h y `spec_at()`:** **shrink** a uso solo de laboratorio y campaña, sin volver al estado actual, con el runner verificando que esté al día. **Drop:** la operación continua en producción.
  3. **Dos vías de acceso al Lake, chunking por sección, límites de 60 y 600, y `retrieval_check.py`:** **shrink** a front matter, un fragmento por documento y el manifiesto con hash. El runbook se lee desde `runbook_id`, sin `get()` en Chroma. **Defer:** el chunking por sección y `retrieval_check`; cuando vuelva, se construye sobre `score_retrieval`.
  4. **Seis firmas contra 4 en el objetivo 3:** **shrink** a 4. "Se cae al arrancar" y "sin memoria" quedan solo como razones del vocabulario.
  5. **Mapa con aristas por origen, lista de discrepancias, `flow.js` y `explanation.py`:** **shrink** a nodos coloreados por estado, borde según el rol y resaltado del enlace causa. **Defer:** lo demás.
  6. **Brazos exploratorios** (LLM directo, Lake con y sin postmortems, juez del mismo proveedor) y la fidelidad del replay con `BundleAdapter`: **defer.** El objetivo 10 se reduce a "re-puntuar desde las trazas". Si vuelven, deben reutilizar `FrozenTools` y `RecordedModel` (`eval/course_e5.py:46,80`).
  7. **Herramientas de evaluación nuevas:** **keep** la reutilización de `digest` (`eval/quality/data.py:19`), del sellado de `live.py`, de `score_causal` (`causal_evaluation.py:8`) y de `score_retrieval` (`eval/quality/score.py:38`).
  8. **`TIDER_PIPELINE`:** **keep** como mecanismo de vuelta atrás. Agregar un ítem posterior a la campaña que borre v1 y `catalog_diagnosis`.
* **Rationale & Recommendation:** cada punto suma superficie sin acercar el go/no-go del piloto. Aplicar la clasificación indicada en cada uno.

### Z9. Causa contra víctima: arreglar el contrato y el CUJ, diferir la métrica - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * l. 27, 120 (CUJ 1), 236 y 240;
  * Zoom Out M7;
  * Critic M3 y M7;
  * Comprehension 5.
* **Discrepancy Description:** hoy el contrato y el CUJ 1 mezclan causa y víctima. Las etapas previas proponen, además, una métrica de víctimas con parseo de cadenas anidadas.
* **Rationale & Recommendation:**
  * **keep:** las hipótesis contienen solo causas y las víctimas son `Nodo.rol_en_principal`. Así se evita el `firma_id` nulo de Critic M7.
  * **keep:** el rol se deriva de forma determinista con el grafo y la atribución de Z1: es víctima el llamador cuyos errores atribuidos empiezan en `t_inicio` o después.
  * **keep:** definir `Arista.estado` y cómo se aplica la regla 2 del juez a un enlace.
  * **keep:** corregir la l. 27 y el CUJ 1, porque checkoutservice no escribe errores propios (RB-01 l. 60).
  * **defer:** la métrica de precisión y recall de víctimas y el parseo general de cadenas. Declarar que los roles no se evalúan estadísticamente en esta iteración.

### Z10. Aislamiento del ground truth en su forma barata - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:**
  * objetivo 9;
  * §11;
  * Catalyst M13 y M14;
  * Critic M6 y M20.
* **Discrepancy Description:** el aislamiento es necesario, pero las mitigaciones propuestas incluyen piezas caras que no lo hacen más seguro, como el sondeo de latencia propio.
* **Rationale & Recommendation:** **shrink.**
  * Lista de campos permitidos en la instantánea, sin etiquetas ni anotaciones `chaosforge*`.
  * El barrido excluye los streams de logs de ChaosForge.
  * Una sola prueba que busque con grep el id del experimento y el nombre del mecanismo en un paquete congelado y en los prompts.
  * Prerregistrar si `REDIS_ADDR=chaosforge-proxy` cuenta como evidencia legítima.
  * Declarar que la latencia solo se mide en el laboratorio.
  * **Drop:** el sondeo de latencia propio de Tider.

### Z11. Agregados documentales de la Etapa 7 que se pueden achicar - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** Critic M16, M17, M18, M21, M22, M23, M27, N5 y N9; Catalyst N7.
* **Discrepancy Description:** varios agregados documentales y de pruebas suman trabajo sin cambiar el resultado del piloto.
* **Rationale & Recommendation:**
  * **M18:** **keep** la lista de parámetros que se fijan antes del hash: K, la proporción, N y la regla de colapso, el umbral de cobertura baja y el número de corridas de línea base. **Drop:** mover todas las decisiones resueltas a sus secciones.
  * **M21:** **shrink** a un H2 de riesgos con una columna de mitigación, que incluya B1, el registrador y la fuga. **Drop:** la columna de riesgo residual.
  * **M22:** **shrink** a una cláusula de trade-off en cada "Motivo". **Drop:** los enlaces con ancla obligatorios.
  * **M23:** **keep** solo la alternativa del registrador contra audit logs más kube-state-metrics, en un párrafo.
  * **M16:** **shrink** a delimitar la evidencia como no confiable en los prompts. **Defer:** la prueba adversarial.
  * **M17:** **shrink** a un presupuesto por etapa que sume menos de 120 s, o declarar que el p95 excluye la ronda 2, más una estimación de tokens. **Drop:** el desglose en dólares por brazo.
  * **N9:** **keep** el CUJ de latencia en un enlace. **Defer:** el CUJ de rechazo del juez.
  * **N5 y M27:** **shrink** a una frase ("el enum `fuente` se extiende por adaptador").
  * **Catalyst N7:** **drop** los namespaces paralelos. **Keep:** reportar por estrato de forma descriptiva (Critic M11).

### Z12. El plan cuenta corridas de historial que ya existen - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** l. 312, 614 (ítem 24) y 719 (paso 3).
* **Discrepancy Description:** PM-01 a PM-05 ya existen en `Context Lake/V3-piloto-online-boutique/postmortems/`, y RB-01 (l. 113) dice que se contrastó con ellas. Aun así, el plan y el costo de laboratorio cuentan "5 de historial". Además, `load_v3` no dice si carga los postmortems.
* **Rationale & Recommendation:**
  * Quitar esas corridas del costo y del paso 3.
  * Aclarar si `load_v3` carga los postmortems. Para el MVP alcanza con un fragmento por documento.

## Alcance mínimo coherente

**Qué tiene que cambiar en el objetivo:**
1. **B1:**
   * Services en la instantánea y en el RBAC.
   * Tabla `ClusterIP:puerto -> servicio` por ventana.
   * Atribución que exige IP y puerto. Lo que no se resuelve queda en `sin_datos`.
   * Prueba de la colisión en 50051.
2. **Predicado de sano:**
   * "sin errores atribuidos" y "sin anomalía respecto de la línea base";
   * el CUJ 2 espera "no causa (sano o sin datos)".
3. **Corte MVP con go/no-go** después de la matriz de firmas. El MVP incluye:
   * el registrador, solo de laboratorio, sin volver al estado actual y con frescura verificada por el runner;
   * el barrido con WARNING+ e INFO aparte, donde `truncado` nunca da sano;
   * 4 firmas, con el descarte del proxy y la precedencia escrita como lista;
   * el contrato v2: hipótesis solo de causa, víctimas como rol derivado y `Arista.estado` definido;
   * el Proponente determinista;
   * las reglas fijas del juez: la regla 4 solo para texto no verificado y la regla 5 que marca pero no rechaza;
   * el aislamiento del ground truth con campos permitidos y la prueba de grep.
4. **Evaluación:**
   * Wilson sobre la exactitud contra el umbral como resultado principal, reportado por estrato.
   * El juez de OpenAI se reporta de forma descriptiva; McNemar, si se conserva, solo sobre candidatos naturales.
   * Repeticiones solo en los casos con más de una firma confirmada.
   * Parámetros congelados antes del hash.
   * Reutilizar `digest`, `score_causal` y el sellado de `live.py`.
5. **Coherencia del texto:**
   * tabla de roles con 2 LLM y 2 puntos de llamada;
   * 4 firmas;
   * el objetivo 3 sin "prioridad entre firmas";
   * la l. 27 y el CUJ 1 sin errores propios de checkoutservice;
   * la etiqueta prerregistrada para el control de loadgenerator.

**Qué se difiere:**
* el respaldo LLM del Proponente y su filtro;
* el brazo del mismo proveedor y los brazos exploratorios;
* `BundleAdapter` y la fidelidad del replay;
* `retrieval_check.py`;
* el chunking por sección y `get()` en Chroma;
* las aristas por origen, las discrepancias en la UI y `explanation.py`;
* la métrica de víctimas y el parseo de cadenas anidadas;
* la prueba adversarial de inyección;
* el CUJ de rechazo del juez;
* el borrado de v1, para después de la campaña.

**Qué se elimina:**
* la interfaz `EvidenceAdapter`;
* las 2 firmas extra como predicados;
* el índice versionado con IPs de pod;
* los conteos por cubeta y la preagregación;
* el sondeo de latencia propio;
* Youden con bootstrap por clúster;
* los namespaces paralelos;
* la operación continua del registrador en producción;
* la columna de riesgo residual, los enlaces con ancla y mover todas las decisiones a sus secciones.

**Pendiente del autor:** Z4 y Z5 se apartan de decisiones aceptadas: la 4, y el carácter confirmatorio de las decisiones 8 y 23. El autor debe confirmarlas antes de editar el objetivo.
