# Revisión EGM consolidada: `tider-diseno-piloto.md`

**Objetivo revisado:** `tider/docs/designs/tider-diseno-piloto.md` (líneas 1-727).
**Informes consolidados:** Etapa 5 `zoom_out_report.md`, Etapa 6 `comprehension_report.md`, Etapa 7 `critic_report.md`, Etapa 8 `intermediate_zoom_out_report.md`, Etapa 9 `implementation_readiness_report.md`.
**Restricción:** no se leyó nada bajo `ground_truth/` ni `ENTREGA_*`. El documento de diseño no se editó.
**Verificación propia:** las líneas citadas se contrastaron con el documento. También se comprobaron en el código y en el Lake V3:
- `context_lake.py:144` usa `chromadb.EphemeralClient`, y los límites son las constantes `MAX_DOCUMENTS = 20` y `MAX_CHUNKS = 300` (`:23-24`);
- `chaosforge/admin/tests/test_open_panel.py:55` y `scripts/verify-admin.sh:12-15` esperan el túnel único `8092:8080` / `18080:8080`;
- la rama `archivo-grafo-antiguo` no existe; existe `origin/chore/archivar-grafo-remediacion`;
- `investigation_history_path` vale `""` por defecto (`settings.py:22`);
- RB-01 l. 46-55 y l. 60 dicen lo que citan las etapas: los errores nombran `ClusterIP:puerto`, y checkoutservice no escribe líneas propias ≥ WARNING;
- PM-01 a PM-05 ya existen en `Context Lake/V3-piloto-online-boutique/postmortems/`;
- RB-05 y RB-06 usan `estado_validacion: declarada, no validada`;
- `agentic.py:198` usa `isinstance(llm, AnthropicLLM)`.

---

## 1. Veredicto general

El diseño todavía no se puede implementar. Hay contradicciones internas que hacen inalcanzables dos CUJ:
- el CUJ 1 choca con la regla 4 del juez y con los errores propios de checkoutservice;
- el CUJ 2 choca con el predicado de "sano".

Tampoco están especificados los algoritmos centrales: la resolución de destinos, la anomalía, la tabla de verdad, la asignación de roles y la traza con replay. Además, el alcance junta las etapas 1 y 2 del RFC sin un punto go/no-go, y varias mitigaciones propuestas en las etapas 5 a 7 agrandarían el diseño todavía más. La ruta recomendada es arreglar los 11 bloqueantes con la versión más chica que propone la Etapa 8, y que el autor responda las 9 decisiones pendientes antes de editar el documento.

**Conteo final después de deduplicar entre etapas:** 154 hallazgos de origen se consolidan en **47 acciones**.

| Prioridad | Acciones |
| --- | --- |
| 🔴 Bloqueante | 11 (A01-A11) |
| 🟡 Mayor | 24 (A12-A35) |
| 🟢 Menor | 12 (A36-A47) |

Se descartan total o parcialmente 5 hallazgos de origen (ver la matriz, sección 6).

---

## 2. Acciones consolidadas

Cada acción indica:
- qué cambiar y en qué líneas;
- por qué;
- qué hallazgos cubre, con la notación `etapa·id`, por ejemplo `E5·B1` o `E7·M4`;
- la clasificación de alcance según la Etapa 8 (aplicar / diferir / eliminar), cuando corresponde.

### 🔴 Bloqueantes

#### A01. Resolver `ClusterIP:puerto` → servicio
- **Qué cambiar:**
  - l. 179 y 480: agregar `services` (ClusterIP y puertos) a la instantánea del registrador;
  - l. 487: agregar `services` al RBAC;
  - §3, l. 204: "errores que nombran un destino" pasa a "errores cuyo `IP:puerto` se resuelve contra la tabla de Services de la ventana";
  - ítem 7 o ítem 10: agregar `resolver_destino(ip, puerto, ventana) -> servicio | None`, con una tabla `ClusterIP:puerto -> servicio` por ventana. Se atribuye solo si coinciden la IP **y** el puerto, nunca solo por el puerto. Si no se resuelve, el error no se atribuye a nadie;
  - dar las expresiones regulares para los formatos de error de Go y de Python que cita RB-01;
  - ítem 14: agregar pruebas con fixtures de PM-04 para las colisiones en 50051 (payment/shipping) y en 6379 (redis-cart/proxy).
- **Por qué:** sin ClusterIPs no se pueden calcular la cláusula 2 del predicado de sano (l. 110), las aristas observadas (l. 204), las víctimas del CUJ 1 (l. 120) ni el corroborante de RB-01. Como el puerto solo es ambiguo, la atribución saldría mal en silencio.
- **Cubre:** E5·B1, E7·M4, E8·Z1, E9·B1.
- **Alcance:**
  - aplicar: la tabla por ventana, sin versionado, porque el Service conserva su ClusterIP aunque tenga 0 réplicas (RB-01 l. 46);
  - diferir: el respaldo por IP de pod vía EndpointSlices (E9·B1);
  - eliminar: el índice versionado en el tiempo que comparten cuatro componentes (E5·B1).

#### A02. Hacer coherentes el predicado "sano confirmado" y el CUJ 2
- **Qué cambiar:**
  - l. 110: "cero errores propios y ningún llamador con errores que lo nombren" pasa a "sin anomalía propia respecto de la línea base previa a t0 y ningún error **atribuido** (A01) a la entidad";
  - l. 111: definir "actividad normal" de forma genérica. Por ejemplo: línea de severidad < WARNING del servicio, o de un llamador cuyo destino se resuelve a él, que no coincide con ninguna plantilla de error;
  - l. 126: el "Then" del CUJ 2 pasa a "`redis-cart` no aparece como causa (sano o sin datos)";
  - l. 49: revisar el criterio en consecuencia;
  - ítems 7 y 9: agregar pruebas casi iguales: puerto correcto con el destino caído, y puerto equivocado con el destino sano.
- **Por qué:** con `wrong_port` los errores de cartservice nombran el puerto 6380 y no llega tráfico a redis-cart. Con las cláusulas 2 y 3 tal como están, redis-cart queda en `sin_datos` y el CUJ 2 no se puede cumplir. La l. 722 exige reproducir el CUJ, así que ninguna implementación pasa la aceptación. Además, "cero errores propios" no se cumple nunca en paymentservice, por el ruido recurrente que documentan RB-01 y PM-04.
- **Cubre:** E5·M8, E6·1, E7·M1, E7·M2 (ruido de línea base y atribución de tráfico), E8·Z2, E9·B4, E9·M5.
- **Alcance:**
  - aplicar: la redacción "atribuidos" y "sin anomalía", y la definición genérica de tráfico;
  - diferir: las plantillas de ruido por servicio en las fichas y el parseo general de cadenas anidadas (E7·M2), porque atarían el estado al Lake;
  - eliminar: la atribución por la tupla (llamador, dirección) (E5·M8) y la excepción "Cambio previo en el llamador" (E9·B4, E7·M1). La regla de A01 alcanza.
- **Requiere al autor:** pregunta P3.

#### A03. Definir "anomalía", "falla confirmada" y `t0`
- **Qué cambiar:**
  - §2, l. 193 y 197, e ítem 7, l. 494: especificar la función de anomalía. Debe dar la estadística (por ejemplo, el conteo de eventos de error en la ventana frente a la media ± 3σ de la ventana previa), el mínimo de eventos, las severidades que cuentan (≥ WARNING, según RB-01) y la deduplicación por plantilla;
  - agrupar cada traza multilínea como un solo evento (RB-01 l. 67);
  - excluir el ruido de ciclo de vida, es decir, las líneas de ERROR entre `Killing` y el log de arranque (PM-04);
  - definir `t0`: en la campaña es el instante de la inyección; en uso real es el inicio de la ventana que pide el operador. Decir cómo se relacionan;
  - l. 213: los candidatos del verificador son "servicios con anomalía según esta función".
- **Por qué:** la falla confirmada, el conjunto de candidatos del verificador y la cláusula 2 dependen de un término que no está definido. Dos implementadores darían resultados distintos.
- **Cubre:** E6·9, E7·M2 (términos sin definir), E7·M13 (agrupar trazas), E9·B2.

#### A04. Fijar el orden de cálculo y las dependencias entre fases
- **Qué cambiar:**
  - ítem 7, l. 495: sacar `estado_servicio()` de `sweep.py` y ponerla en un módulo propio, o en `signatures.py`, con la firma `estado_servicio(barrido, grafo, veredictos, k) -> dict[str, Nodo]`;
  - escribir el orden explícito: barrido → Cartógrafo → verificador → estado. Las pruebas de estado (ítem 9, l. 514-515) pasan a la Fase 2;
  - resolver la circularidad: el verificador toma sus candidatos de la función de anomalía (A03), no del estado;
  - Fases 2 y 3: mover los ítems 23-24 antes de la Fase 2, o hacer que las Fases 2-3 lean `topologia.yaml` y los runbooks directamente del disco detrás de una interfaz chica.
- **Por qué:** tal como está, `estado_servicio()` necesita el grafo (Fase 2) y las firmas (Fase 2) pero se construye en la Fase 1. El Cartógrafo y el Proponente necesitan el Lake v3, que recién se construye en la Fase 4. Eso rompe la regla de la l. 447 ("cada fase deja la suite en verde").
- **Cubre:** E9·B3, E9·M2.

#### A05. Especificar la tabla de verdad del verificador y el esquema de `catalog_v1.yaml`
- **Qué cambiar:**
  - §4, l. 214, e ítem 13, l. 540: reemplazar la flecha por una lista ordenada:
    1. si falta un campo obligatorio: SIN_DATOS;
    2. si no, y se cumple un descarte: DESCARTADA, con la marca `conflicto` si también se cumplen los obligatorios;
    3. si no, y se cumplen todos los obligatorios más al menos un corroborante: CONFIRMADA;
    4. en otro caso (hay datos, algún obligatorio es falso y no hay descarte): DESCARTADA.
  - ítem 12: agregar el esquema YAML con un ejemplo completo (RB-01). Debe incluir las claves, la lista de operadores, la unidad de `persistencia` y la forma de escribir alternativas OR, porque el obligatorio de RB-01 es una disyunción;
  - §4: agregar un resumen de una línea por firma, con lo que la confirma y lo que la descarta;
  - RB-04: agregar al modelo un campo de uso de CPU, o quitar ese predicado.
- **Por qué:** una implementación podría emitir CONFIRMADA más `conflicto`, lo que va contra la decisión 27.4. Además, el catálogo no se puede escribir sin el esquema, y el lector no puede comprobar los CUJ contra el verificador.
- **Cubre:** E6·4, E7·M8, E9·B5.

#### A06. Separar causa y víctima en el contrato y asignar los roles de forma determinista
- **Qué cambiar:**
  - §5, l. 230-241: las `Hipotesis` contienen solo causas (o `independiente`), y las víctimas se expresan como `Nodo.rol_en_principal`. Con eso se quita `victima` del enum `rol` de la hipótesis;
  - definir el dominio de `Arista.estado`, por ejemplo `falla | sano | sin_datos`, y cómo se aplica la regla 2 del juez (l. 271) cuando la entidad es un enlace;
  - ítem 10 o un ítem nuevo: agregar `asignar_roles(hipotesis, grafo, nodos)`. Es víctima un llamador aguas arriba de la causa cuyos errores atribuidos (A01) empiezan en `t_inicio` o después. Las víctimas anidadas en frontend se citan a partir de la línea de frontend;
  - l. 144 (Principio): agregar "roles causa/víctima" a lo que calcula el código;
  - l. 27: cambiar el ejemplo para que no nombre a checkoutservice como servicio que registra errores. Basarlo en PM-02;
  - l. 120 (CUJ 1): checkoutservice se cita mediante el error anidado que registra frontend (`failed to prepare order …`);
  - ítems 18 y 36: declarar que los roles no se evalúan estadísticamente en esta iteración.
- **Por qué:**
  - ningún componente tiene asignado el cálculo de `rol`, que es la promesa central del producto (l. 13);
  - con `firma_id` nulo solo para `desconocida`, una hipótesis `victima` no se puede expresar de forma válida;
  - el CUJ 1 pide citas de errores propios de checkoutservice, y esos errores no existen (RB-01 l. 60, verificado).
- **Cubre:** E5·M7, E6·5, E7·M3, E7·M7, E8·Z9, E9·B6 (roles), E9·M13 (regla 2 en enlaces).
- **Alcance:**
  - aplicar: el contrato, la función determinista, `Arista.estado` y la corrección del CUJ 1;
  - diferir: la métrica de precisión y recall de víctimas y el parseo general de cadenas anidadas.
- **Requiere al autor:** pregunta P8.

#### A07. Limitar la regla 4 del juez al texto no verificado
- **Qué cambiar:**
  - l. 273: "la recomendación de `tipo = diagnostico_no_verificado` pasó el filtro de verbos";
  - aplicar el mismo alcance en el ítem 19 (l. 581-582) y en el ítem 22.
- **Por qué:** la acción de catálogo validada de RB-01 es `kubectl … scale …`. Con la regla tal como está, el juez rechaza toda recomendación de catálogo, y el CUJ 1 no se puede cumplir. El RFC ya había marcado este defecto (N12).
- **Cubre:** E5·M2 (alcance del filtro), E8·Z4 (keep), E9·M12.

#### A08. Escribir el contenido del protocolo y la lista de parámetros que se fijan antes del hash
- **Qué cambiar:**
  - Open Questions (l. 73-75): reemplazar "Ninguna por ahora" por la lista de parámetros abiertos, cada uno con el plazo "antes del hash del protocolo":
    - K y sus corridas de calibración;
    - el número de corridas de línea base para la media ± 3σ;
    - la proporción de verdaderos y falsos;
    - N repeticiones y la regla de colapso (ver A21);
    - el umbral de "cobertura baja";
    - el criterio para pasar `validado: true` (ver A19);
    - aceptar o no n < 60.
  - l. 46: corregir la referencia ("ver Open Questions", aunque los umbrales están en "Preguntas resueltas");
  - ítem 33, l. 652-659: dar los valores concretos, o agregar un ítem previo "fijar el contenido del protocolo" con su responsable. Ese contenido incluye:
    - la tabla de pares servicio×mecanismo;
    - qué son los conjuntos historial, evaluación y control;
    - los criterios de admisión y exclusión, reportando cada caso excluido con su motivo;
    - la receta de mutaciones, con un solo nombre y las mismas cuatro transformaciones en l. 98, 306 y 668;
    - qué repetición alimenta el conjunto del juez;
    - el denominador de "afirmaciones incorrectas" (l. 103);
  - κ (objetivo 11, §12 l. 308, ítem 37):
    - quiénes son Alberto y José y por qué evalúan;
    - las 3 preguntas, escritas textualmente;
    - qué es "la variante" (el brazo);
    - cómo se muestrean los 30 casos;
    - el objetivo de κ y su intervalo;
  - l. 690: escribir textualmente "los 4 puntos del asesor académico".
- **Por qué:** el objetivo 11 y el CUJ 4 dependen de un protocolo cuyo contenido queda al criterio de quien lo implemente. El texto reconoce que la proporción de verdaderos y falsos "cambia el resultado" (l. 98) y la deja sin fijar. Una sección que dice "ninguna" pregunta abierta oculta siete parámetros sin decidir.
- **Cubre:** E5·M9 (regla de colapso), E6·7, E6·8, E7·M10 (fijar la proporción y la receta), E7·M18 (parte keep), E7·N11 (listas distintas), E7·N16, E7·N17, E8·Z11 (M18), E9·B7.
- **Alcance:**
  - aplicar: la lista de parámetros;
  - eliminar: mover todas las decisiones resueltas a sus secciones normativas (E7·M18).

#### A09. Agregar el ítem que construye la traza y la re-puntuación sin proveedores
- **Qué cambiar:**
  - agregar un ítem nuevo, por ejemplo `src/tider/console/trace.py`, con el esquema JSON de la traza de §12 (l. 301). Debe decir cómo se calcula el hash de los prompts y dónde se guardan las respuestas del modelo;
  - agregar una prueba que recalcule las métricas sin llamar a ningún proveedor;
  - objetivo 10 (l. 57) y CUJ 4 (l. 138): reducirlos a "re-puntuar desde las trazas";
  - ítem 34 (l. 664): decir qué significa "congela la ventana" en el MVP (guardar una copia de la evidencia leída) y que no se re-ejecutan brazos offline.
- **Por qué:** `score.py`, `retrieval_check.py` y el objetivo 10 dependen de una traza que ningún ítem construye. El replay de herramientas a demanda no está especificado.
- **Cubre:** E5·M15, E7·M19, E8·Z8.6, E9·B8.
- **Alcance:**
  - aplicar: la traza y la re-puntuación;
  - diferir: `BundleAdapter`, la fidelidad del replay de herramientas a demanda y la reutilización de `FrozenTools`/`RecordedModel` (cuando vuelvan los brazos exploratorios).

#### A10. Especificar el doble puerto de ChaosForge sin dejar su suite en rojo
- **Qué cambiar:**
  - ítems 28-31 (l. 633-645):
    - los valores por defecto de `--port` y `--admin-port`;
    - cómo se divide `make_handler`;
    - qué puerto usan las probes;
    - el arranque y el `stop()` de dos `ThreadingHTTPServer`;
  - agregar `admin/Dockerfile` como Modify, porque hoy expone solo 8080;
  - `abrir-panel.sh`:
    - la verificación de bind en 8092 y 8093;
    - cómo corren dos port-forward a la vez (hoy uno corre en primer plano);
    - qué imprime;
  - agregar como Modify `admin/tests/test_open_panel.py:35,55`, `scripts/verify-admin.sh:12-15` y `.github/workflows/deploy.yml:167`;
  - actualizar los documentos que citan 8092 como el panel: `README.md:82`, `admin/README.md:63`, `admin/DEPLOYMENT.md:88` y `admin/EXPERIMENTS.md:43`.
- **Por qué:** con el plan actual, `python3 -m unittest discover -s admin/tests -v` falla, lo que contradice la l. 447, y `verify-admin.sh` deja de leer `/api/state`. Ambas cosas están verificadas.
- **Cubre:** E9·B9, E9·B10.

#### A11. Definir cómo llega el Lake v3 a la consola en ejecución
- **Qué cambiar:**
  - ítem 24 (l. 613-614) y verificación, paso 1 (l. 716): elegir una de estas opciones y escribirla:
    - carga al iniciar la consola con un setting `LAKE_V3_PATH`;
    - un endpoint;
    - un cliente Chroma persistente con una ruta configurable;
  - quitar `tider-lake-load` como CLI independiente si se elige la primera opción.
- **Por qué:** `context_lake.py:144` usa `chromadb.EphemeralClient` (verificado). Una CLI separada indexa en su propia memoria y termina, así que la consola nunca ve los documentos.
- **Cubre:** E9·B11.

### 🟡 Mayores

#### A12. Declarar el MVP y el punto go/no-go
- **Qué cambiar:**
  - l. 6: el alcance pasa de "etapas 1 y 2 del RFC" a un MVP;
  - agregar al inicio del Implementation Plan (l. 445) el contenido del MVP:
    - registrador solo de laboratorio, barrido y estado;
    - verificador con 4 firmas;
    - contrato v2;
    - Proponente según P1;
    - reglas fijas del juez;
    - aislamiento del ground truth;
    - traza, protocolo, runner y puntuación;
  - agregar un go/no-go explícito después de `--validate-signatures` (l. 717);
  - marcar como segundo corte los ítems 26-27, 37b y los brazos exploratorios. El ítem 26 se reduce según A37;
  - l. 690: "justifica con datos" pasa a "aporta evidencia exploratoria";
  - agregar un responsable y horas por fase.
- **Por qué:** hay más de 41 cambios en dos repositorios y una sola persona trabajando (VALIDACION_CODEX l. 332 y 335). Los brazos exploratorios no tienen ítems que los construyan. El RFC separa la "Etapa 1: cambios mínimos para una evaluación válida".
- **Cubre:** E5·M1, E5·N1, E8·Z3, E9·M20.
- **Requiere al autor:** P5, P6, P7.

#### A13. Cerrar los canales de fuga del ground truth en su forma barata
- **Qué cambiar:**
  - l. 179 e ítem 5: el registrador guarda solo una lista de campos permitidos: réplicas, generación, hash del spec, `*_ADDR` y recursos. No guarda etiquetas ni anotaciones `chaosforge*`;
  - §2: el barrido excluye los streams de logs de ChaosForge;
  - ítem 32 (l. 647-648): alinear la prueba con el objetivo 9, extendiendo `tests/console/test_operational_observer.py` en lugar de crear un archivo duplicado (el rechazo de rutas ya se prueba ahí, verificado);
  - agregar una prueba que busque con grep el id del experimento y el nombre del mecanismo en una ventana congelada y en los prompts;
  - objetivo 9 (l. 56): limitarlo a lo que esas pruebas demuestran;
  - prerregistrar cómo se trata `REDIS_ADDR=chaosforge-proxy` (ver P9).
- **Por qué:** la prueba actual solo comprueba URLs configuradas. Quedan abiertos los eventos del namespace, los logs del controlador, las anotaciones persistidas por el registrador y la variable del proxy que el Cartógrafo reporta a propósito (l. 205).
- **Cubre:** E5·M14, E7·M6, E8·Z10, E9·M23.
- **Alcance:** aplicar la lista de campos permitidos, la exclusión de logs y la prueba de grep.

#### A14. Barrido con dos lecturas por servicio y cobertura declarada
- **Qué cambiar:**
  - l. 193 e ítem 3 (l. 465-467): por servicio, una lectura `severity>=WARNING` con su cuota y otra lectura INFO con su propia cuota, solo para el conteo de tráfico K;
  - fijar la cuota (hoy dice "por ejemplo, 40" en l. 193 y "40" en l. 436);
  - decir si se modifica `cloud_logging.py`, porque `max_records` es un límite total y no por servicio (`:50-53`). Decir también de dónde sale `texto_original` (el mensaje se reconstruye y los eventos se truncan a 800 caracteres) y cómo se mapea `sweep_timeout_seconds` al deadline del cliente;
  - l. 274: un servicio `truncado` nunca queda sano;
  - l. 19 y 48: "completa" pasa a "con cobertura declarada";
  - reconciliar la cuota con `agent_log_budget` (`settings.py:26`).
- **Por qué:** una muestra en orden temporal de 40 líneas se llena con INFO previo al incidente, y entonces puede certificar "cero errores" que nunca leyó. PM-02 registra 1937 líneas de ERROR de un solo servicio.
- **Cubre:** E5·M12, E7·M13, E8·Z7, E9·M4, E9·N15 (presupuesto).
- **Alcance:**
  - aplicar: las dos lecturas y la regla de `truncado`;
  - eliminar: los conteos por cubeta, el muestreo estratificado, las métricas basadas en logs y la preagregación en el registrador.

#### A15. Registrador: solo laboratorio, sin volver al estado actual, frescura verificada
- **Qué cambiar:**
  - l. 179: quitar "en uso real, de forma continua" y declarar fuera de alcance la operación en producción;
  - l. 191 y 493: quitar "(o el estado actual si no hay registrador)". Una ventana sin instantáneas da SIN_DATOS con `fuente_fallida = recorder`;
  - ítem 34: el runner verifica la frescura del registrador antes de cada inyección y excluye el caso si hay huecos. Es una regla de exclusión prerregistrada (A08);
  - ítem 5 (l. 477-482): especificar
    - el esquema SQLite;
    - cómo se calcula el hash del spec;
    - los tipos que devuelven `snapshots()` y `spec_at()`;
    - qué pasa si `kubectl` falla;
    - los settings de namespace, intervalo y retención;
    - cómo encuentra el barrido la base;
  - justificar los 10 s frente a una falla de 30-120 s y llevar las constantes al Implementation Plan;
  - Alternatives: agregar un párrafo que compare el registrador con audit logs de GKE más kube-state-metrics.
- **Por qué:** volver al estado actual reintroduce sin aviso la Alternativa F, que el autor rechazó. Una falla silenciosa del registrador mezcla tiempos en la campaña.
- **Cubre:** E5·M5, E5·N5 (constantes), E7·M14, E7·M23 (parte registrador), E8·Z8.2, E8·Z11 (M23), E9·M8, E9·N15 (settings del registrador).
- **Alcance:**
  - aplicar: uso solo de laboratorio, la frescura y el párrafo de la alternativa;
  - eliminar: la operación continua en producción.

#### A16. Completar el RBAC y el permiso de Monitoring
- **Qué cambiar:**
  - ítem 6 (l. 485-488):
    - nombrar la ServiceAccount o el sujeto;
    - dar los `apiGroups`: `""` para pods, services y events, `apps` para deployments, statefulsets y replicasets, y `discovery.k8s.io` para endpointslices;
    - agregar `services` (A01);
  - agregar un paso o script para el permiso IAM de Monitoring / Managed Prometheus (riesgo de l. 313).
- **Por qué:** sin el sujeto y sin los grupos, el manifiesto no se puede aplicar. Sin el permiso IAM, la firma de CPU queda en SIN_DATOS.
- **Cubre:** E9·M9.

#### A17. Proponente: una sola regla, una sola etiqueta, un solo reintento
- **Qué cambiar (según la respuesta a P1):**
  - **si se acepta P1:**
    - §7 (l. 261-265) e ítem 19 (l. 577-582): el Proponente es determinista;
    - con firma CONFIRMADA y runbook validado, devuelve la acción de catálogo;
    - en otro caso, devuelve los "Pasos de verificación" del runbook de la razón, con SVC, CLUSTER_IP y la ventana rellenados desde la evidencia y la etiqueta "sugerencia no verificada";
    - con `razon = desconocida`, devuelve un paso genérico de lectura del namespace;
    - en todos los casos, especificar la extracción de las secciones del runbook por encabezado;
    - quitar de la l. 437 "como máximo 2 llamadas";
  - **si no se acepta P1:**
    - escribir la condición completa;
    - fijar un solo reintento ("reintenta una vez") y qué recibe la segunda llamada, para resolver l. 265 contra l. 581;
    - definir "runbook más cercano";
    - reemplazar la lista de verbos prohibidos por una lista de comandos permitidos (`kubectl get|describe|logs|top`, `gcloud logging read`, …). Si se mantiene la lista de verbos prohibidos, al menos definir la regla de coincidencia por subcomando, para no rechazar `ScalingReplicaSet`, y probar la lista completa en el objetivo 5 (l. 52);
    - cambiar la etiqueta del ítem 19 a "determinista salvo la llamada LLM de respaldo".
- **Por qué:**
  - el módulo se llama "determinista" pero llama a un LLM;
  - el reintento aparece como 1 en l. 265 y como 2 en l. 581 y 437;
  - la lista de verbos prohibidos deja pasar `exec`, `label`, `create` y prosa en español;
  - los pasos de solo lectura ya existen en cada runbook (RB-01 l. 88-110).
- **Cubre:** E5·M2, E6·14, E7·M15, E7·M23 (allowlist), E8·Z4, E9·M11, E9·N18.
- **Alcance:** diferir el respaldo LLM y su filtro. Si vuelve, con lista de comandos permitidos.

#### A18. Tabla de roles y conteos de LLM coherentes
- **Qué cambiar:**
  - agregar bajo "Principio" (l. 142-144) una tabla con las columnas rol | módulo | ¿LLM? | puntos de llamada | máx. llamadas, que liste los seis roles con nombre: Recolector, Cartógrafo, Verificador, Investigador, Proponente, Juez. Decir si el Reportero y el Estado son roles o pasos;
  - corregir l. 69, 144 y 264 según P1: con P1 aceptada quedan 2 roles LLM y 2 puntos de llamada;
  - diagrama (l. 150-171):
    - el registrador aparece como fuente independiente, no a partir de `REQ`;
    - agregar las aristas del Lake hacia el Verificador, el Proponente y el Investigador;
    - poner el respaldo dentro del subgrafo LLM si se mantiene;
  - l. 282 y 629: el flujo incluye al Cartógrafo, con los nombres en mayúscula;
  - ítem 27: renombrar la etapa, porque `explanation.py:12,58-61` ya usa `verificador` para otra cosa;
  - ítem 18: extender el mapeo de etapas de `agentic.py:176-178`, que hoy daría KeyError con una etapa nueva.
- **Por qué:** el texto dice seis roles pero nombra siete, y no los lista. La l. 69 dice que dos roles usan LLM, la l. 144 dice "dos puntos" y la l. 264 dice "3 puntos de llamada".
- **Cubre:** E6·2, E7·M24, E7·N6, E9·M18.
- **Descarte parcial:** E7·M24 dice que las rondas del juez no coinciden. No es así: l. 170 y 276 dicen "una ronda más como máximo" y l. 437 dice "máximo 2 rondas"; 1 + 1 = 2.

#### A19. Cuatro firmas, criterio de validación y objetivo 3
- **Qué cambiar:**
  - objetivo 3 (l. 50): quitar "prioridad entre firmas", que la pregunta resuelta de la l. 80 y la Alternativa J eliminan;
  - ítem 12 (l. 533-535): el catálogo tiene las 4 firmas a validar, con nombre. "Se cae al arrancar" y "sin memoria" quedan solo como razones del vocabulario (l. 233-234), sin predicado, y apuntan a RB-05 y RB-06 como "declarada, no validada";
  - ítem 2 (l. 458): quitar los campos que solo usaban esas dos firmas (`terminaciones_en_ventana`);
  - l. 534: "las firmas que superen la validación pasan a `validado: true`";
  - definir el criterio de aprobación. Por ejemplo: CONFIRMADA en toda corrida de su mecanismo, y DESCARTADA o SIN_DATOS en la corrida sin falla. Definir también el número de corridas y su separación de los casos de evaluación;
  - l. 696: usar el valor exacto del Lake, `declarada, no validada`;
  - en §4, asociar cada RB a su modo de falla.
- **Por qué:** el texto dice 4 firmas en el objetivo 3 y 6 en el ítem 12, y la l. 534 asume que las 4 pasan la validación. Ninguna regla dice cuándo se pasa a `validado: true`.
- **Cubre:** E5·N3, E5·N4 (objetivo 3), E6·3, E6·18, E7·M7 (razones sin firma), E7·M25 (objetivo 3), E8·Z8.4, E9·M10, E9·N13.
- **Alcance:** eliminar las 2 firmas extra como predicados.

#### A20. Descarte de "configuración incorrecta" ante una redirección a un proxy que responde
- **Qué cambiar:**
  - ítem 12: agregar a "configuración incorrecta" un predicado de descarte: la variable `*_ADDR` apunta a un destino alcanzable que sigue respondiendo;
  - Objetivo 3 e ítem 14: agregar este caso como negativo cercano en la matriz de validación.
- **Por qué:** una inyección de latencia aparece como `REDIS_ADDR=chaosforge-proxy:6379`, que es un cambio de `*_ADDR` previo a los errores. Eso confirma las dos firmas y deja la decisión al orden del LLM.
- **Cubre:** E7·M5, E8·Z6 (keep).

#### A21. Orden de firmas por LLM: corregir el motivo, la regla 3 y las repeticiones
- **Qué cambiar:**
  - l. 374 (Alternativa J): corregir "resolución de 1 minuto", porque el registrador toma instantáneas cada 10 s y los logs tienen precisión menor a un segundo;
  - l. 272 (regla 3): verificar que el orden sea coherente con los `t_inicio` citados, no solo que cite uno;
  - l. 81, 101 y 659, según P4: repetir solo los casos con más de una firma CONFIRMADA, con mayoría de 3 prerregistrada (empate = error), y reportar la fracción de casos que llega a ese punto;
  - ítem 13 (l. 542): dar la regla de orden de `signatures.baseline()` para el modo sin LLM.
- **Por qué:** con un solo experimento activo (l. 65), varias firmas confirmadas solo aparecen por un defecto de firma, y A20 corrige el caso conocido. Repetir todos los casos tres veces es un costo fijo. Además, la regla de colapso no existe: VALIDACION_CODEX advierte que Wilson sobre medias fraccionarias no es válido.
- **Cubre:** E5·M9, E7·M9, E8·Z6, E9·B6 (orden del modo sin LLM).
- **Alcance:** diferir el desempate determinista en tres niveles (E5·M9).
- **Requiere al autor:** P4.

#### A22. Comparación del juez: medir con lo que no depende de la receta
- **Qué cambiar (según P2):**
  - l. 95-99, objetivo 6 (l. 53), §12 e ítem 36: el resultado principal es la exactitud de la primera hipótesis con Wilson contra el umbral;
  - el juez se reporta de forma descriptiva: tasa de falsa aprobación y de falso rechazo con Wilson, separando candidatos naturales y fabricados;
  - si se mantiene una prueba confirmatoria, McNemar exacto vía `paired()` solo sobre candidatos naturales;
  - definir el candidato como el diagnóstico de la primera ronda (l. 170);
  - l. 674, 678 y 693: escribir "McNemar exacto vía `paired()`".
- **Por qué:** frente a "aprobar todo", el resultado de McNemar depende de la proporción y de la receta de mutaciones que elige el equipo, y las mutaciones de un mismo caso no son independientes. El problema declarado (l. 34) ya lo cubren los umbrales de Wilson.
- **Cubre:** E5·M10, E7·M10 (independencia, candidato), E8·Z5, E9·M26.
- **Alcance:**
  - aplicar: el adaptador `OpenAILLM` (decisión 23);
  - diferir: el brazo del juez del mismo proveedor;
  - eliminar: Youden con bootstrap por clúster (E5·M10);
  - el análisis de potencia de unos 92 pares (E7·M10) se aplica solo si P2 mantiene la prueba confirmatoria.
- **Requiere al autor:** P2.

#### A23. Reportar por estrato y fijar la mezcla de casos
- **Qué cambiar:**
  - l. 101-106 e ítem 33: fijar en `protocol.yaml` los conteos por estrato (mecanismo);
  - reportar Wilson por estrato de forma descriptiva, además del agregado, con un mínimo por estrato;
  - l. 106: quitar la alternativa "o aceptar que…", que pasa a P5/A08.
- **Por qué:** con `scale_zero` en 11-12 servicios, el umbral agregado ≥ 70 % se puede cumplir casi solo con el caso trivial (decisión 18).
- **Cubre:** E5·N7, E7·M11, E8·Z11 (Catalyst N7).
- **Alcance:** eliminar los namespaces paralelos (E5·N7).

#### A24. Etiqueta prerregistrada para el control de loadgenerator (CUJ 3)
- **Qué cambiar:**
  - l. 128-132 e ítem 33: etiqueta esperada `{loadgenerator, servicio-sin-instancias, sin_impacto_en_tienda}`, puntuada aparte;
  - l. 202: decir cómo se clasifica loadgenerator (auxiliar o tienda). Mejor aún, marcar los auxiliares en `topologia.yaml` en lugar de usar patrones de nombre;
  - agregar a un ítem el mensaje "se detuvo la generación de tráfico".
- **Por qué:** escalar loadgenerator a cero confirma "servicio sin instancias" sobre él. El CUJ 3 no dice si eso es un acierto. Ningún ítem implementa el mensaje del CUJ 3.
- **Cubre:** E5·N4 (auxiliares por patrón), E5·N6, E6·6, E7·M12, E9·M27 (mensaje del CUJ 3).

#### A25. La latencia de dependencia es solo de laboratorio
- **Qué cambiar:**
  - l. 184 y 314: declarar que "dependencia lenta" se valida solo contra el observador del laboratorio y se excluye de las afirmaciones que se trasladan a SIBI;
  - decir dónde se toma el PING respecto del proxy;
  - ítem 3 e ítem 8: el observador actual devuelve `dependency_median_ms` de `GET /cart`, no un p95 con `destino` (`operational_observer.py:42,50-52`). Modificarlo y listarlo, o leer las filas crudas de `/api/observations`;
  - nombrar los settings de "si está configurado" y "si está habilitado";
  - l. 217: los umbrales se calibran solo con líneas base sin falla, no con parámetros del inyector;
  - agregar una frase que presente el observador de ChaosForge y el proxy de latencia.
- **Por qué:** el modelo pide un campo que la fuente no entrega. Además, usar umbrales del inyector muestra conformidad, no validez causal (VALIDACION_CODEX §5.4).
- **Cubre:** E5·M13, E6·10, E6·11, E7·M20, E8·Z10 (lab-only), E9·M7.
- **Alcance:** eliminar el sondeo de latencia propio de Tider.

#### A26. Presupuesto de latencia y de tokens
- **Qué cambiar:**
  - NFR l. 435-438: un presupuesto por etapa que sume menos de 120 s, o declarar que el p95 excluye la ronda 2;
  - una estimación de tokens por análisis y por campaña;
  - el valor de N;
  - decir si las repeticiones se corren en GKE o desde la ventana guardada.
- **Por qué:** el barrido (30 s) más el Investigador (90 s) ya suman los 120 s de la meta, antes del Proponente y del juez.
- **Cubre:** E5·M11, E7·M17, E8·Z11 (M17).
- **Alcance:**
  - aplicar: el presupuesto por etapa y los tokens;
  - eliminar: el desglose en dólares por brazo y la preagregación.

#### A27. Construir `eval/pilot` sobre `eval/quality`
- **Qué cambiar:**
  - ítems 33-38: congelar `protocol.yaml` con `digest()`/`verify()` (`eval/quality/data.py`);
  - sellar las corridas como `eval/quality/live.py:69-75`;
  - extender `score_causal()` (`causal_evaluation.py`) con la entidad enlace y el acierto parcial;
  - si vuelve `retrieval_check`, construirlo sobre `score_retrieval()` (`eval/quality/score.py:38`).
- **Por qué:** el plan vuelve a escribir el congelado, el sellado y la puntuación causal, que ya existen.
- **Cubre:** E5·M3, E8·Z8.7.

#### A28. Selección v1/v2, modo sin LLM y retiro de v1
- **Qué cambiar:**
  - ítem 21 (l. 589-590):
    - cómo elige `AnalysisService` según `pipeline`, porque hoy elige por `llm_provider` (`service.py:55`);
    - cómo recibe `LabEngine.analyze` el Barrido, el Grafo y los veredictos, si hoy recibe `list[Signal]`;
    - el adaptador mock de v2, que usan casi todas las pruebas;
  - nombrar `catalog_diagnosis.diagnose_catalog`, que corre en el modo por reglas cuando el Lake no está vacío (`analysis.py:59-66`);
  - usar un solo término, "modo sin LLM";
  - agregar un ítem posterior a la campaña que borre v1, `catalog.related_services` y `catalog_diagnosis`;
  - l. 439-441: decir si el código v1 puede leer registros v2 en una vuelta atrás.
- **Por qué:** el reemplazo de `baseline.diagnose` cubre solo una parte del camino por reglas. Mantener dos pipelines sin fecha de retiro duplica el código y las pruebas.
- **Cubre:** E5·M4, E5·N2, E7·N18, E8·Z8.8, E9·M17.
- **Alcance:**
  - aplicar: mantener `TIDER_PIPELINE` como vuelta atrás;
  - diferir: el borrado de v1 hasta después de la campaña.

#### A29. Tipos centrales, ids y nombres de campo
- **Qué cambiar:**
  - ítems 1-3, 10 y 13: dar los campos y tipos de `Evidencia`, `Barrido`, `Grafo` y `VeredictoFirma`;
  - l. 181, 227 y 459: un esquema de ids determinista y estable en el replay, por ejemplo `S0001` por corrida. `S##` no alcanza para 12×40 observaciones;
  - ítem 15 (l. 554): usar `recomendacion`, igual que el contrato de l. 246, o cambiar el contrato;
  - agregar `incompleto` a §5;
  - dar el `schema_version` por defecto de los registros v1, el tipo de `cobertura` y los valores de `rol_en_principal`;
  - agregar `respaldado: bool` y `motivo_rechazo`, que la métrica de "afirmaciones incorrectas" necesita.
- **Por qué:** sin estos tipos, cada módulo inventa su propia interfaz.
- **Cubre:** E6·15, E7·N7, E9·M3, E9·M14 (campos de salida), E9·M24.

#### A30. Interfaces del Investigador v2 y evidencia no confiable en los prompts
- **Qué cambiar:**
  - ítem 18 (l. 567-575):
    - el prompt v2 y cómo se serializan la tabla, el grafo y las firmas;
    - qué pasa con una salida inválida del LLM (reparar, reintentar o rechazar);
    - el esquema de entrada y salida del juez;
    - el estado final tras un rechazo en la última ronda;
  - ítem 20 (l. 584-587):
    - la nueva firma de `tools_factory` y de `InvestigationTools`, porque `investigation_tools.py:44-45` lanza un error sin catálogo confirmado;
    - el orden de construcción;
    - los tipos y el límite de `sweep_lines`;
    - si `context_search` pasa el filtro `where`;
  - Seguridad (l. 430-434): delimitar la evidencia en los prompts y tratarla como no confiable.
- **Por qué:** con el orden actual de `agentic.py:160`, v2 falla antes de tener el grafo. Las líneas de log pueden traer texto controlado por usuarios.
- **Cubre:** E7·M16, E8·Z11 (M16), E9·M14, E9·M16, E9·N17 (`sweep_lines`).
- **Alcance:**
  - aplicar: delimitar la evidencia;
  - diferir: la prueba adversarial de inyección.

#### A31. `OpenAILLM` encaja con `llm.py` y con `agentic.py`
- **Qué cambiar:**
  - ítem 16 (l. 558):
    - elegir entre Chat Completions y Responses API, y el método de salida estructurada;
    - el `judge_model` por defecto y la variable de entorno de la clave;
    - el tipo y el mensaje de la excepción;
  - alinear con `llm.py`: `timeout` es keyword-only, el Protocol exige `complete_text` y las claves de metadatos son `stop_reason/input_tokens/output_tokens`;
  - ítem 18: reemplazar las comprobaciones `isinstance(llm, AnthropicLLM)` (`agentic.py:197-198,208-209`, verificado en `:198`) y decir cómo se construye e inyecta el segundo cliente;
  - agregar una prueba de enmascarado para el juez de OpenAI (l. 433).
- **Por qué:** hoy un único `llm` sirve al Investigador y al juez, y el timeout y los metadatos solo se aplican a Anthropic.
- **Cubre:** E9·M15, E9·N14.

#### A32. Eventos sin lista de servicios
- **Qué cambiar:**
  - ítem 4 (l. 474): asignar el servicio comparando `involvedObject.name` contra el inventario de la plataforma, con el patrón de nombres de pod y ReplicaSet;
  - manejar `None` en `kubernetes_events.py:19`, `:41` y `:75`;
  - agregar una prueba.
- **Por qué:** "por prefijo" sin lista no tiene contra qué comparar, y `sorted(None)` lanza un error.
- **Cubre:** E9·M6.

#### A33. Alcance del cargador del Lake, límites y corridas de historial
- **Qué cambiar:**
  - ítem 24 (l. 613-614): listar los patrones de inclusión y exclusión (README, `postmortems/datos/**`, `correr_corridas.sh`, `corridas.log`);
  - decidir si se indexan PM-01 a PM-05, que ya existen. Para el MVP alcanza con un fragmento por documento;
  - decir dónde persiste la topología para `analyze_live`;
  - ítem 23: los límites se inyectan desde settings en `ContextLake.__init__` y en el mensaje de `:177`;
  - tratar el cambio de entrada a `extract_candidates`;
  - l. 312 y 718: quitar las "5 corridas de historial" del costo y del paso 3 de verificación, porque ya existen (verificado);
  - el runbook se lee por `runbook_id` desde el archivo, sin `get()` en Chroma.
- **Por qué:** el cargador no dice qué hace con la mitad de la carpeta, y el plan cuenta trabajo que ya está hecho.
- **Cubre:** E7·N9 (chunking de postmortems), E8·Z8.3, E8·Z12, E9·M19, E9·M21.
- **Alcance:**
  - aplicar: el front matter, un fragmento por documento y el manifiesto con hash;
  - diferir: el chunking por sección, `get()` en Chroma, el interruptor solo léxico y la relevancia de enlaces para `retrieval_check`.
- **Requiere al autor:** P6.

#### A34. Dependencias, puntos de entrada y comando de build
- **Qué cambiar:**
  - ítem 17 (l. 561-565): registrar `tider-lake-load` (o retirarlo, según A11) en `[project.scripts]`;
  - declarar la dependencia del parser YAML;
  - agregar `uv.lock` a la lista de archivos;
  - l. 711: un solo comando de build coherente con `scripts/setup.sh:8`, porque el comando actual omite `--extra gcp` y borra los extras del otro.
- **Por qué:** con el comando de build tal como está, se pierden extras según el orden en que se corra.
- **Cubre:** E9·M22.

#### A35. Plan de verificación ejecutable
- **Qué cambiar:**
  - l. 695: dar la ruta base absoluta de `Context Lake/V3-…`;
  - l. 714: nombrar el archivo de referencia y cómo se compara;
  - l. 718-720: escribir pasos en imperativo, con comandos;
  - l. 722: "la salida cumple el 'Then' de los CUJ 1-3 en la consola; el CUJ 4 se cumple con `eval.pilot.score`";
  - l. 617: escribir "los filtros funcionan" como aserción, por ejemplo: `search(where={'servicio': X})` devuelve solo fragmentos de X.
- **Por qué:** varios pasos no se pueden ejecutar ni comprobar tal como están escritos.
- **Cubre:** E9·M25 (l. 617), E9·M27.

### 🟢 Menores

#### A36. Sin interfaz `EvidenceAdapter` nueva
- **Qué cambiar:** ítems 1 y 3 (l. 451-471) y l. 181:
  - mantener el modelo común (decisión 22) y dejar `gke.py` como módulo concreto;
  - no crear `EvidenceAdapter` mientras existan `EvidenceSource` (`service.py:16`) y `EvidenceProvider` (`providers/__init__.py:9`);
  - reemplazar "no tiene nada propio de GCP" por "el enum `fuente` se extiende por adaptador".
- **Por qué:** con la interfaz nueva quedan tres abstracciones superpuestas, y el enum actual nombra fuentes de GCP.
- **Cubre:** E5·M6, E7·M27, E8·Z8.1, E8·Z11 (N5/M27).
- **Alcance:**
  - aplicar: la frase sobre el enum;
  - eliminar: la interfaz y el campo `proveedor`.

#### A37. Mapa reducido y objetivo 8 comprobable
- **Qué cambiar:**
  - ítem 26 (l. 619-626) y §9 (l. 282): nodos coloreados por estado, borde según el rol y resaltado del enlace causa;
  - objetivo 8 (l. 55): el criterio pasa a ser una clase CSS o un atributo por rol y estado, verificado por una prueba;
  - dar la paleta y la leyenda.
- **Por qué:** "se distinguen visualmente" no es comprobable (contradice l. 46).
- **Cubre:** E7·N12, E8·Z8.5, E9·N17 (colores).
- **Alcance:** diferir las aristas por origen, la lista de discrepancias en la UI y el ítem 27 (`explanation.py`).
- **Requiere al autor:** P7.

#### A38. Sección H2 "Riesgos y mitigaciones"
- **Qué cambiar:**
  - reemplazar el H3 de l. 310-315 por un H2 antes de NFR, con las columnas Riesgo | Impacto | Mitigación;
  - incluir A01, el registrador, la fuga del ground truth, el juez caído o con timeout, la falla al cargar Chroma o el Lake, un catálogo mal formado y la limitación de cuota de Cloud Logging.
- **Por qué:** hoy los riesgos no tienen mitigación ("hay que verificarlo") y están dispersos.
- **Cubre:** E7·M21, E8·Z11 (M21).
- **Alcance:** eliminar la columna de riesgo residual.

#### A39. "Motivo del rechazo" con su trade-off
- **Qué cambiar:**
  - l. 326-424: cada "Motivo" lleva una cláusula con el trade-off decisivo y pone al autor entre paréntesis;
  - F (l. 353) recibe su número de decisión;
  - L (l. 384) deja de ser circular;
  - aclarar "rechazada en la revisión y aceptada por el autor" (l. 385, 402);
  - opcional: dividir G, K, M, Q y R en sub-opciones.
- **Por qué:** hoy varios motivos solo repiten la opción elegida.
- **Cubre:** E7·M22, E7·N8, E8·Z11 (M22).
- **Alcance:** eliminar los enlaces con ancla obligatorios.

#### A40. Conteo de servicios
- **Qué cambiar:**
  - objetivo 1 (l. 48): "todos los Deployments y StatefulSets del namespace (12 de la tienda más los auxiliares presentes)", diciendo si loadgenerator cuenta;
  - NFR l. 436: el presupuesto se expresa por servicio;
  - l. 513: "los 12 servicios más los auxiliares presentes";
  - revisar "11 fichas" en la decisión 25 frente a las 12 del Lake.
- **Por qué:** el texto dice "12 servicios" mientras el inventario incluye auxiliares (l. 90).
- **Cubre:** E6·13, E7·M25 (objetivo 1), E9·M25 (l. 513).

#### A41. La regla 5 del juez marca, no rechaza
- **Qué cambiar:**
  - l. 269-274: separar las reglas que rechazan (1-4) de la que marca `incompleto` (5);
  - el umbral de "cobertura baja" se fija en A08;
  - poner las reglas fijas en un módulo chico, por ejemplo `judge_rules.py`, en lugar de dentro de `agentic.py`.
- **Por qué:** la l. 269 dice que todo incumplimiento rechaza, y la regla 5 no rechaza.
- **Cubre:** E5·N5 (módulo de reglas), E6·16, E7·M26, E9·M13 (umbral).

#### A42. Rama de trabajo real
- **Qué cambiar:**
  - l. 447: nombrar la base real (`main`) y el commit de partida;
  - quitar "una vez confirmada";
  - corregir el nombre viejo en `docs/decisions.md:107` y `docs/archive/INVENTARIO_ARCHIVADO.md:3`.
- **Por qué:** `archivo-grafo-antiguo` no existe; la rama se renombró a `chore/archivar-grafo-remediacion` (verificado).
- **Cubre:** E6·17, E9·M1.

#### A43. Glosa breve de términos en su primer uso
- **Qué cambiar:** agregar una línea de explicación, o un enlace, para cada uno de estos términos:
  - E5 y C09;
  - la rúbrica C1-C4 10/20;
  - OpenRCA A.5;
  - "cláusula 5";
  - [INF];
  - "el pitch";
  - "LLM directo";
  - el atlas de 13 páginas y "el ejecutor";
  - D08;
  - SIBI (l. 6);
  - "benchmark de recuperación";
  - MRR y k = 4;
  - historial y control (ver A08).
- **Por qué:** quien lee por primera vez no puede reconstruir esas referencias.
- **Cubre:** E6·12, E7·N10, E9·N6 ("el ejecutor"), E9·N12 (MRR).

#### A44. CUJ de latencia en un enlace
- **Qué cambiar:** agregar un CUJ 5 para `latency` → enlace `cartservice→redis-cart`, con la entidad enlace, el acierto parcial y SIN_DATOS fuera de ese enlace.
- **Por qué:** ningún CUJ cubre la entidad enlace, que define una clase entera de casos.
- **Cubre:** E7·N9 (CUJ de latencia), E8·Z11 (N9).
- **Alcance:** diferir el CUJ de rechazo del juez.

#### A45. Estructura y formato del documento
- **Qué cambiar:**
  - metadatos y encabezados en un solo idioma, salvo los que exija la plantilla (l. 3-7);
  - numerar todos los H3 del Technical Plan o ninguno, y seguir el orden del diagrama;
  - un solo estilo de lista en "Preguntas resueltas", con la l. 112 separada;
  - una línea en blanco antes de cada lista que sigue a un texto en negrita;
  - rutas relativas al repositorio en todo el documento;
  - renumerar el 37b;
  - mover a un registro de decisiones las notas "decidido al cerrar, 2026-11-09" (l. 263, 289, 684);
  - usar los campos "Tipo / alcance" y "Por qué" en todos los ítems, con una cláusula de motivo en cada "Por qué".
- **Por qué:** los saltos de formato rompen la exportación a PDF y dificultan la lectura.
- **Cubre:** E7·N1, E7·N2, E7·N3, E7·N4, E7·N5, E7·N13, E9·N1, E9·N2, E9·N11.

#### A46. Redacción y terminología
- **Qué cambiar:**
  - "mecanismo" solo para la etiqueta de ChaosForge y "razón" para la salida de Tider;
  - una sola etiqueta para "no verificada";
  - "congelar" se reemplaza por verbos concretos ("guarda una copia", "registra el hash");
  - los estados por su nombre ("queda en sin datos", no "sale sano"), y "+" se cambia por "y";
  - corregir el tiempo verbal de l. 475 y la concordancia de l. 466;
  - definir "negativo cercano" y "ejemplo de manual";
  - reescribir l. 572, 582 y 689;
  - dar el sujeto en l. 292 ("los límites de documentos y de fragmentos pasan de…");
  - agregar unidad y fecha a "(142)" y "(20)";
  - una sola política de anglicismos;
  - quitar las expresiones vagas de l. 6, 23, 42, 54, 106, 396, 412, 418 y 424. En l. 424, citar la decisión 18.
- **Por qué:** la terminología que cambia de un lugar a otro produce lecturas distintas de la misma regla.
- **Cubre:** E7·N11 (terminología), E7·N14, E7·N15, E9·N3, E9·N4, E9·N5, E9·N6 (tiempo verbal), E9·N7, E9·N8, E9·N9, E9·N10, E9·N12 (unidades).

#### A47. Rutas de pruebas y settings
- **Qué cambiar:**
  - l. 509, 541, 544, 592 y 616: rutas completas con `tests/console/`;
  - decir qué pasa con `test_topology_catalog.py`, que ya existe;
  - agregar pruebas para `baseline()`;
  - ítem 8: agregar límites `Field(ge/le)` como los existentes (`settings.py:18,23-26`).
- **Por qué:** con rutas incompletas no queda claro qué archivo crear o modificar, y los settings nuevos no tienen los límites que sí tienen los actuales.
- **Cubre:** E9·N15 (límites), E9·N16.

---

## 3. Alcance mínimo coherente

### Clasificación de lo que agregan el Catalyst (Etapa 5), el Critic (Etapa 7) y la Etapa 9

La clasificación sigue a `intermediate_zoom_out_report.md`. Solo se listan los agregados que ensanchan el alcance.

| Agregado propuesto | Origen | Clasificación | Acción |
| --- | --- | --- | --- |
| Índice IP→entidad versionado en el tiempo, con IPs de pod | E5·B1 | eliminar (se reemplaza por una tabla `ClusterIP:puerto` por ventana) | A01 |
| Respaldo por IP de pod vía EndpointSlices | E9·B1 | diferir | A01 |
| Atribución por la tupla (llamador, dirección) | E5·M8 | eliminar | A02 |
| Excepción "Cambio previo en el llamador" para la cláusula 2 | E7·M1, E9·B4 | eliminar | A02 |
| Plantillas de ruido por servicio en las fichas | E7·M2 | diferir | A02 |
| Clasificador de tráfico con marcadores por servicio en las fichas | E9·M5 | diferir (aplicar la definición genérica) | A02 |
| Parseo general de cadenas de error anidadas | E5·M7, E7·M2 | diferir | A02, A06 |
| Métrica de precisión y recall de víctimas | E5·M7 | diferir | A06 |
| Conteos agregados por cubeta, muestreo estratificado, métricas basadas en logs | E5·M12, E7·M13 | eliminar | A14 |
| Preagregación en el registrador | E5·M11 | eliminar | A14, A26 |
| Dos lecturas por servicio (WARNING+ e INFO) | E8·Z7 | aplicar | A14 |
| Heartbeat del registrador y frescura verificada por el runner | E5·M5, E7·M14 | aplicar | A15 |
| Operación continua del registrador en producción | diseño l. 179 | eliminar | A15 |
| Alternativa: audit logs más kube-state-metrics | E5·M5, E7·M23 | aplicar (un párrafo) | A15 |
| Alternativa: juez solo por reglas como baseline | E7·M23 | eliminar | — |
| `BundleAdapter` y fidelidad del replay | E5·M15, E7·M19 | diferir | A09 |
| Interfaz `EvidenceAdapter` | diseño ítems 1 y 3 | eliminar | A36 |
| Sondeo de latencia propio de Tider | E5·M13 | eliminar | A25 |
| Declarar la latencia solo de laboratorio | E5·M13, E7·M20 | aplicar | A25 |
| Desempate determinista en tres niveles | E5·M9 | diferir | A21 |
| Repetir solo los casos con más de una firma confirmada | E8·Z6 | aplicar (sujeto a P4) | A21 |
| Youden con bootstrap por clúster | E5·M10 | eliminar | A22 |
| Análisis de potencia (unos 92 pares) | E7·M10 | diferir (solo si P2 mantiene la prueba confirmatoria) | A22 |
| Namespaces paralelos | E5·N7 | eliminar | A23 |
| Reporte por estrato descriptivo | E5·N7, E7·M11 | aplicar | A23 |
| Lista de comandos permitidos para el Proponente | E5·M2, E7·M15 | diferir, junto con el respaldo LLM | A17 |
| Delimitar la evidencia en los prompts | E7·M16 | aplicar | A30 |
| Prueba adversarial de inyección | E7·M16 | diferir | A30 |
| Presupuesto por etapa y tokens | E5·M11, E7·M17 | aplicar | A26 |
| Desglose en dólares por brazo | E7·M17 | eliminar | A26 |
| H2 de riesgos con mitigación | E7·M21 | aplicar | A38 |
| Columna de riesgo residual | E7·M21 | eliminar | A38 |
| Cláusula de trade-off en cada "Motivo" | E7·M22 | aplicar | A39 |
| Enlaces con ancla obligatorios a la auditoría | E7·M22 | eliminar | A39 |
| Lista de parámetros que se fijan antes del hash | E7·M18 | aplicar | A08 |
| Mover todas las decisiones resueltas a sus secciones | E7·M18 | eliminar | A08 |
| CUJ 5 de latencia en un enlace | E7·N9 | aplicar | A44 |
| CUJ 6 de rechazo del juez | E7·N9 | diferir | A44 |
| Enum `fuente` con campo `proveedor` | E7·M27 | eliminar (alcanza una frase) | A36 |
| Lista de Referencias con enlaces | E7·N5 | diferir (aplicar solo rutas uniformes) | A45 |
| Borrar v1 y `catalog_diagnosis` | E5·M4, E5·N2 | diferir hasta después de la campaña | A28 |
| Interruptor de búsqueda solo léxica y relevancia de enlaces | E9·M19, E9·M21 | diferir, junto con `retrieval_check` | A33 |
| Ítems para los brazos exploratorios | E9·M20 | diferir (o sacarlos del alcance de forma explícita) | A12 |

### Qué cambiar en el documento (MVP)

1. Resolución `ClusterIP:puerto` con Services en la instantánea y en el RBAC (A01, A16).
2. El predicado de sano con "atribuidos" y "sin anomalía"; el CUJ 2 espera "no causa" (A02, A03).
3. Orden de cálculo y dependencias entre fases (A04).
4. Las 4 firmas con tabla de verdad, esquema, descarte por proxy y criterio de validación (A05, A19, A20).
5. Contrato v2 con hipótesis solo de causa, víctimas derivadas, `Arista.estado` definido, y CUJ 1 y l. 27 corregidos (A06, A29).
6. Proponente según P1; la regla 4 solo para texto no verificado y la regla 5 que marca (A07, A17, A41).
7. Barrido con WARNING+ e INFO aparte; `truncado` nunca da sano (A14).
8. Registrador solo de laboratorio, sin volver al estado actual, con frescura verificada (A15).
9. Aislamiento del ground truth con campos permitidos y prueba de grep (A13).
10. Protocolo con contenido y parámetros fijados antes del hash; estratos; control de loadgenerator (A08, A23, A24).
11. Exactitud con Wilson como resultado principal; el juez según P2 (A22).
12. Traza y re-puntuación sin proveedores, reutilizando `eval/quality` (A09, A27).
13. Doble puerto de ChaosForge con su suite en verde; Lake cargado en la consola (A10, A11).
14. Tabla de roles; conteos de LLM coherentes (A18).
15. MVP declarado con go/no-go después de `--validate-signatures` (A12).

### Qué se difiere

- El respaldo LLM del Proponente y su filtro (o su lista de comandos permitidos).
- El brazo del juez del mismo proveedor y los brazos exploratorios (Tider frente a LLM directo, Lake con y sin postmortems).
- `BundleAdapter`, la fidelidad del replay de herramientas y `FrozenTools`/`RecordedModel`.
- `retrieval_check.py` (ítem 37b), el interruptor solo léxico y la relevancia de enlaces.
- El chunking por sección y `get()` en Chroma.
- Las aristas por origen y las discrepancias en la UI; `explanation.py` (ítem 27).
- La métrica de víctimas y el parseo general de cadenas anidadas.
- Las plantillas de ruido y los marcadores de tráfico en las fichas.
- El respaldo por IP de pod.
- El desempate determinista en tres niveles.
- La prueba adversarial de inyección y el CUJ de rechazo del juez.
- El borrado de v1, para después de la campaña.

### Qué se elimina

- La interfaz `EvidenceAdapter` y el campo `proveedor`.
- Las 2 firmas extra como predicados, y `terminaciones_en_ventana`.
- El índice versionado con IPs de pod; la atribución por tupla.
- Los conteos por cubeta, el muestreo estratificado y la preagregación.
- El sondeo de latencia propio.
- Youden con bootstrap por clúster.
- Los namespaces paralelos.
- La operación continua del registrador en producción y la vuelta al estado actual.
- La columna de riesgo residual, los enlaces con ancla y mover todas las decisiones a sus secciones.
- El desglose en dólares por brazo.
- La alternativa "juez solo por reglas".
- Las "5 corridas de historial" del costo y del plan, porque ya existen.

---

## 4. Decisiones del autor pendientes

Cada pregunta se puede responder por separado. El orden sigue el impacto en las acciones bloqueantes.

### P1. ¿El Proponente pasa a ser determinista, sin respaldo LLM, en este piloto?
- **Qué contradice:** la decisión 4 (Alternativa N, l. 397: "el LLM solo como respaldo de diagnóstico, con filtro de verbos") y la decisión tomada al cerrar el 2026-11-09 (l. 263).
- **Opción:** con firma CONFIRMADA y runbook validado, la acción de catálogo. En otro caso, los "Pasos de verificación (SOLO LECTURA)" del runbook, con los parámetros rellenados desde la evidencia y la etiqueta "sugerencia no verificada". Con `desconocida`, un paso genérico de lectura. El respaldo LLM se difiere y, si vuelve, lo hace con una lista de comandos permitidos.
- **Contraargumento:**
  - se pierde la redacción adaptada a la evidencia del caso;
  - la decisión 4 preveía calificar con κ las sugerencias del LLM, y esto cambia qué evalúa κ;
  - los pasos genéricos pueden servir poco cuando la razón es `desconocida`, que es justo cuando más ayuda haría falta.
- **Recomendación:** aceptar. Los pasos de solo lectura ya existen en cada runbook. Quitar la llamada elimina un punto de LLM, un prompt, los reintentos y la superficie de inyección. También resuelve las contradicciones de conteo (A18) y de reintentos (A17). Si κ sobre sugerencias del LLM sigue importando, correr el respaldo LLM solo como brazo exploratorio sobre los 30 casos de κ.

### P2. ¿La comparación del juez de OpenAI deja de ser la prueba confirmatoria?
- **Qué contradice:** la pregunta resuelta de l. 95-99 ("única comparación prerregistrada"), el objetivo 6 (tres brazos) y las decisiones 8 y 23 (juez de otra familia, con medición). La Alternativa P deja el juez del mismo proveedor como brazo exploratorio.
- **Opción:**
  - el resultado principal es la exactitud de la primera hipótesis con Wilson contra el umbral;
  - el juez se reporta de forma descriptiva (FAR y FRR con Wilson, naturales y fabricados por separado);
  - si se conserva una prueba confirmatoria, es McNemar exacto solo sobre candidatos naturales;
  - el brazo del mismo proveedor se difiere;
  - el adaptador `OpenAILLM` se mantiene.
- **Contraargumento:**
  - la rúbrica y el pitch piden un resultado confirmatorio sobre el juez;
  - con candidatos naturales solamente, habrá pocos pares discordantes, y McNemar puede quedar sin potencia;
  - quitar el brazo del mismo proveedor deja sin medir el sesgo compartido que motivó la decisión 23.
- **Recomendación:** aceptar la versión intermedia. Exactitud con Wilson como resultado principal; McNemar exacto solo sobre naturales como confirmatoria secundaria, con su potencia declarada; el juez descriptivo sobre los fabricados. El motivo es que, frente a "aprobar todo", el resultado depende de la proporción y de la receta que elige el equipo (A22), y una prueba cuyo resultado se puede mover con un parámetro libre no sirve como confirmatoria.

### P3. ¿Se cambia el texto del predicado "sano confirmado" y el "Then" del CUJ 2?
- **Qué contradice:** la pregunta resuelta de l. 108-112 (cláusula 2: "cero errores propios y ningún llamador con errores que lo nombren") y la Alternativa M (l. 387-390), que el autor aceptó con esa redacción.
- **Opción:**
  - la cláusula 2 pasa a "sin anomalía propia respecto de la línea base y ningún error **atribuido** (IP y puerto) a la entidad";
  - el CUJ 2 espera "redis-cart no aparece como causa (sano o sin datos)".
- **Contraargumento:**
  - "sin anomalía" es más permisivo que "cero errores": un servicio con errores bajos pero constantes podría quedar sano;
  - el CUJ 2 pierde su promesa más fuerte, que redis-cart quede sano aunque lo nombren.
- **Recomendación:** aceptar. Con la redacción actual el CUJ 2 es inalcanzable y paymentservice nunca queda sano por su ruido conocido (RB-01, PM-04). Mantener intacta la cláusula 3 (tráfico ≥ K), que es la que impide el falso sano.

### P4. ¿Se repiten solo los casos con más de una firma confirmada, y qué regla de orden usa el modo sin LLM?
- **Qué contradice:** la pregunta resuelta de l. 80-83 ("hacen falta repeticiones por caso") y la Alternativa J (l. 372-375), que rechazó cualquier orden fijo.
- **Opción:**
  - repetir 3 veces solo los casos con más de una firma CONFIRMADA, con mayoría prerregistrada (empate = error), y reportar qué fracción llega a ese punto;
  - para `signatures.baseline()` (modo sin LLM), una regla fija, por ejemplo "Cambio previo sobre la entidad; si no hay, `t_inicio` más temprano";
  - corregir el motivo de la Alternativa J (la resolución no es de 1 minuto).
- **Contraargumento:**
  - no medir la variación del LLM en los casos con una sola firma oculta la variación en el texto y en los roles;
  - usar una regla fija en el modo sin LLM reintroduce parcialmente la alternativa rechazada.
- **Recomendación:** aceptar. Con un solo experimento activo, varias firmas confirmadas son un defecto de firma, no un caso normal (A20 corrige el caso conocido). El modo sin LLM necesita alguna regla para existir, y declararla como regla del baseline no obliga a usarla en el Investigador.

### P5. ¿Se recorta el alcance a un MVP con go/no-go después de la matriz de firmas?
- **Qué contradice:** la l. 6 ("etapas 1 y 2 del RFC… producto completo del piloto"), los objetivos 7, 8 y 10 completos, y la Alternativa Q, que dejaba Tider frente a LLM directo y Lake con y sin postmortems como brazos exploratorios dentro de este diseño.
- **Opción:** el MVP de A12. El go/no-go va después de `--validate-signatures`. Quedan para un segundo corte el mapa completo, los brazos exploratorios, `retrieval_check` y `explanation.py`.
- **Contraargumento:**
  - la entrega del curso puede pedir el producto completo y la comparación con LLM directo "que pide el pitch" (l. 412);
  - dividir en dos cortes puede dejar el segundo sin hacer.
- **Recomendación:** aceptar. Hay una sola persona trabajando (VALIDACION_CODEX l. 332 y 335) y más de 41 cambios en dos repositorios. Si la matriz de firmas falla, todo lo que viene después no sirve. Si el pitch exige la comparación con LLM directo, mantenerla como único brazo exploratorio del segundo corte.

### P6. ¿Se difieren la vía de búsqueda con filtros por tipo, el chunking por sección y `retrieval_check`?
- **Qué contradice:** la decisión 12 (objetivo 7: carga "como corresponde a cada tipo"), la decisión tomada al cerrar el 2026-11-09 sobre las dos vías (l. 289-291) y la decisión 16 junto con el ítem 37b (l. 683-690, "decidido al cerrar").
- **Opción:**
  - para el MVP, front matter, un fragmento por documento y el manifiesto con hash;
  - el runbook se lee por `runbook_id` desde el archivo;
  - `context_search` mantiene la búsqueda actual;
  - se difieren el chunking por `##`, `get()` en Chroma y `retrieval_check`.
- **Contraargumento:** `retrieval_check` responde a "uno de los 4 puntos del asesor" (l. 690, la estrategia de chunking). Diferirlo deja ese punto sin evidencia en esta entrega.
- **Recomendación:** diferir el chunking por sección y `get()`. Para `retrieval_check`, mantenerlo solo si el punto del asesor tiene fecha en esta entrega, construido sobre `score_retrieval` y como último ítem opcional. Si no, diferirlo.

### P7. ¿El mapa del MVP pinta solo nodos y el enlace causa, sin aristas por origen ni discrepancias?
- **Qué contradice:** la pregunta resuelta sobre la entidad (l. 87: "el mapa pinta aristas, no solo nodos") y el objetivo 8 ("muestra las discrepancias entre el Lake y la evidencia").
- **Opción:** nodos por estado, borde según el rol y resaltado del enlace causa. Las aristas por origen y la lista de discrepancias quedan para el segundo corte.
- **Contraargumento:** las discrepancias entre el Lake y la plataforma son una de las salidas visibles que justifican el inventario mixto (decisión del inventario, l. 89-93).
- **Recomendación:** aceptar, y resaltar el enlace causa, que es lo que exige la entidad enlace. Las discrepancias se pueden mostrar como texto en el informe, sin trabajo de UI.

### P8. ¿Los roles de causa y víctima los asigna código determinista?
- **Qué cambia:** no contradice una decisión numerada, pero cambia el Principio (l. 144), que hoy deja el rol implícitamente en manos del LLM, y requiere una decisión del autor para cerrar A06 (E9·B6).
- **Opción:** `asignar_roles()` determinista, con el grafo y la atribución de A01. El LLM solo explica. Las víctimas son `Nodo.rol_en_principal`, no hipótesis.
- **Contraargumento:** una regla fija puede fallar en cadenas raras, como un llamador indirecto o errores anidados en otro servicio. Además, quita al LLM la parte de juicio que el Principio le asigna.
- **Recomendación:** aceptar. Agregar una sub-decisión: el LLM puede proponer un cambio de rol solo con justificación, el juez lo valida, y la traza guarda los dos valores.

### P9. ¿`REDIS_ADDR=chaosforge-proxy:6379` cuenta como evidencia legítima o como huella de la inyección?
- **Qué cambia:** no contradice una decisión numerada, pero afecta la Alternativa K (l. 377-380: no meter artefactos del laboratorio en el producto) y el Cartógrafo, que reporta esa variable a propósito (l. 205).
- **Opción A:** evidencia legítima. Un operador real vería la redirección. Se combina con el descarte de A20.
- **Opción B:** huella excluida. Se ocultan los nombres `chaosforge*` en el spec antes de que lleguen al LLM.
- **Contraargumento de A:** el nombre del componente revela el mecanismo y facilita la respuesta en el caso de latencia.
- **Contraargumento de B:** se borra una señal que en producción sería real (una redirección a un intermediario), y la firma de latencia pierde contexto.
- **Recomendación:** opción A con el nombre neutralizado. La redirección cuenta como evidencia, pero el nombre se reemplaza por "componente auxiliar" antes de llegar al LLM y a la traza. Prerregistrarlo en el protocolo.

---

## 5. Orden sugerido de corrección

**Fase 0: decisiones del autor.** Responder P1 a P9. Sin P1, P3, P5 y P8 no se pueden escribir A02, A06, A12, A17 y A18.

**Fase 1: reglas centrales coherentes.** Los bloqueantes de contenido:
- A01 (ClusterIP);
- A02 y A03 (predicado, anomalía, `t0`);
- A05 (tabla de verdad);
- A06 (roles y contrato);
- A07 (regla 4);
- después, A19 y A20 (firmas y descarte por proxy), A18 (tabla de roles) y A41 (regla 5).

**Fase 2: recorte de alcance.**
- A12 (MVP y go/no-go);
- A14 (barrido);
- A15 (registrador);
- A17 (Proponente);
- A36 (sin `EvidenceAdapter`);
- A37 (mapa);
- A33 (Lake);
- aplicar la sección 3 completa.

**Fase 3: validez de la evaluación.**
- A08 (protocolo y Open Questions);
- A09 (traza);
- A13 (aislamiento);
- A21, A22 y A23 (repeticiones, juez, estratos);
- A24 (control);
- A25 (latencia solo de laboratorio);
- A26 (presupuesto);
- A27 (reuso de `eval/quality`).

**Fase 4: plan de implementación ejecutable.**
- A04 (orden de fases);
- A10 (ChaosForge);
- A11 (carga del Lake);
- A16 (RBAC);
- A28 (v1/v2);
- A29 (tipos);
- A30 (Investigador);
- A31 (OpenAI);
- A32 (eventos);
- A34 (build);
- A35 (verificación);
- A42 (rama);
- A47 (pruebas).

**Fase 5: texto y estructura.**
- A38 (riesgos);
- A39 (alternativas);
- A40 (conteos);
- A43 (glosas);
- A44 (CUJ 5);
- A45 y A46 (formato y redacción).

Después de la Fase 4 conviene correr de nuevo solo la Etapa 9 (implementation readiness) sobre el plan, antes de tocar el estilo.

---

## 6. Matriz de trazabilidad

Notación: E5 = `zoom_out_report.md`, E6 = `comprehension_report.md`, E7 = `critic_report.md`, E8 = `intermediate_zoom_out_report.md`, E9 = `implementation_readiness_report.md`.

### Etapa 5

| Hallazgo | Acción |
| --- | --- |
| E5·B1 | A01 |
| E5·M1 | A12 |
| E5·M2 | A07 (alcance del filtro), A17 |
| E5·M3 | A27 |
| E5·M4 | A28 |
| E5·M5 | A15 |
| E5·M6 | A36 |
| E5·M7 | A06 |
| E5·M8 | A02 |
| E5·M9 | A21, A08 (regla de colapso) |
| E5·M10 | A22 |
| E5·M11 | A26 |
| E5·M12 | A14 |
| E5·M13 | A25 |
| E5·M14 | A13 |
| E5·M15 | A09 |
| E5·N1 | A12 (diferido) |
| E5·N2 | A28 |
| E5·N3 | A19 |
| E5·N4 | A19 (objetivo 3), A24 (auxiliares en `topologia.yaml`) |
| E5·N5 | A15 (constantes), A41 (módulo de reglas) |
| E5·N6 | A24 |
| E5·N7 | A23 |

### Etapa 6

| Hallazgo | Acción |
| --- | --- |
| E6·1 | A02 |
| E6·2 | A18, A17 |
| E6·3 | A19 |
| E6·4 | A05 |
| E6·5 | A06 |
| E6·6 | A24 |
| E6·7 | A08, A43 |
| E6·8 | A08 |
| E6·9 | A03 |
| E6·10 | A25 |
| E6·11 | A25 |
| E6·12 | A43 |
| E6·13 | A40 |
| E6·14 | A17 |
| E6·15 | A29 |
| E6·16 | A41 |
| E6·17 | A42 |
| E6·18 | A19 |

### Etapa 7

| Hallazgo | Acción |
| --- | --- |
| E7·M1 | A02 (se aplica la redacción, no la excepción propuesta) |
| E7·M2 | A02, A03 (plantillas de ruido diferidas) |
| E7·M3 | A06 |
| E7·M4 | A01 |
| E7·M5 | A20 |
| E7·M6 | A13 |
| E7·M7 | A06, A19 |
| E7·M8 | A05 |
| E7·M9 | A21 |
| E7·M10 | A22, A08 |
| E7·M11 | A23 |
| E7·M12 | A24 |
| E7·M13 | A14, A03 |
| E7·M14 | A15 |
| E7·M15 | A17 |
| E7·M16 | A30 |
| E7·M17 | A26 |
| E7·M18 | A08 (la parte de mover decisiones se elimina) |
| E7·M19 | A09 |
| E7·M20 | A25 |
| E7·M21 | A38 |
| E7·M22 | A39 |
| E7·M23 | A15 (alternativa del registrador), A17 (allowlist, diferida). La alternativa "juez solo por reglas" se elimina por alcance (E8·Z11). |
| E7·M24 | A18. **Descartado en parte:** las rondas del juez sí coinciden (l. 170 y 276: "una más como máximo"; l. 437: "máximo 2 rondas"). |
| E7·M25 | A40 (objetivo 1), A19 (objetivo 3), A17 (objetivo 5) |
| E7·M26 | A41 |
| E7·M27 | A36 |
| E7·N1 | A45 |
| E7·N2 | A45 |
| E7·N3 | A45 |
| E7·N4 | A45 |
| E7·N5 | A45 (la lista de Referencias se difiere) |
| E7·N6 | A18 |
| E7·N7 | A29 |
| E7·N8 | A39 |
| E7·N9 | A44 (CUJ de latencia), A33 (chunking, diferido). **Descartado en parte:** `kappa_form.csv` (l. 308) y `kappa_form.py` (l. 680) no se contradicen; el script exporta el CSV (l. 681). |
| E7·N10 | A43 |
| E7·N11 | A46 (terminología), A08 (listas distintas de mutaciones) |
| E7·N12 | A37 |
| E7·N13 | A45 |
| E7·N14 | A46 |
| E7·N15 | A46 |
| E7·N16 | A08. **Descartado en parte:** "30 casos" no contradice "mínimo 20" de la decisión 24, porque 30 ≥ 20. |
| E7·N17 | A08 |
| E7·N18 | A28 |

### Etapa 8

| Hallazgo | Acción |
| --- | --- |
| E8·Z1 | A01 |
| E8·Z2 | A02 |
| E8·Z3 | A12 |
| E8·Z4 | A07, A17, P1 |
| E8·Z5 | A22, P2 |
| E8·Z6 | A20, A21, P4 |
| E8·Z7 | A14 |
| E8·Z8 | A36 (8.1), A15 (8.2), A33 (8.3), A19 (8.4), A37 (8.5), A09 (8.6), A27 (8.7), A28 (8.8) |
| E8·Z9 | A06, P8 |
| E8·Z10 | A13, A25, P9 |
| E8·Z11 | A08, A15, A23, A26, A30, A36, A38, A39, A44 |
| E8·Z12 | A33 (PM-01 a PM-05 verificados en el Lake V3) |

### Etapa 9

| Hallazgo | Acción |
| --- | --- |
| E9·B1 | A01 (el respaldo por IP de pod se difiere) |
| E9·B2 | A03 |
| E9·B3 | A04 |
| E9·B4 | A02 (se aplica la redacción de E8·Z2, no la excepción propuesta) |
| E9·B5 | A05 |
| E9·B6 | A06, A21 |
| E9·B7 | A08 |
| E9·B8 | A09 |
| E9·B9 | A10 (verificado) |
| E9·B10 | A10 |
| E9·B11 | A11 (verificado) |
| E9·M1 | A42 (verificado) |
| E9·M2 | A04 |
| E9·M3 | A29 |
| E9·M4 | A14 |
| E9·M5 | A02 (definición genérica; los marcadores en fichas se difieren) |
| E9·M6 | A32 |
| E9·M7 | A25 |
| E9·M8 | A15 |
| E9·M9 | A16 |
| E9·M10 | A19 |
| E9·M11 | A17 |
| E9·M12 | A07 |
| E9·M13 | A06 (regla 2 en enlaces), A41 (umbral) |
| E9·M14 | A30, A29 |
| E9·M15 | A31 |
| E9·M16 | A30 |
| E9·M17 | A28 |
| E9·M18 | A18 |
| E9·M19 | A33 |
| E9·M20 | A12 |
| E9·M21 | A33 |
| E9·M22 | A34 |
| E9·M23 | A13 (verificado: la prueba de rutas ya existe en `test_operational_observer.py:33`) |
| E9·M24 | A29 |
| E9·M25 | A35 (l. 617), A40 (l. 513) |
| E9·M26 | A22. Se baja de Mayor a parte de A22: es una corrección de una palabra. |
| E9·M27 | A35, A24 (mensaje del CUJ 3) |
| E9·N1 | A45 |
| E9·N2 | A45 |
| E9·N3 | A46 |
| E9·N4 | A46 |
| E9·N5 | A46 |
| E9·N6 | A46, A43 |
| E9·N7 | A46 |
| E9·N8 | A46 |
| E9·N9 | A46 |
| E9·N10 | A46 |
| E9·N11 | A45 |
| E9·N12 | A46, A43 |
| E9·N13 | A19 (verificado: RB-05 y RB-06 usan `declarada, no validada`) |
| E9·N14 | A31 |
| E9·N15 | A14, A15, A47 |
| E9·N16 | A47 |
| E9·N17 | A30 (`sweep_lines`), A33 (`manifest()`), A37 (colores) |
| E9·N18 | A17 |

**Resumen de descartes:**
- E7·M24, sub-punto de las rondas: las rondas del juez coinciden.
- E7·N9, sub-punto `.csv`/`.py`: no hay contradicción.
- E7·N16, sub-punto 30 contra 20: no hay conflicto.
- E7·M23, alternativa "juez solo por reglas": se elimina por alcance.
- E9·M26: se baja de prioridad y se absorbe en A22.

Ningún otro hallazgo de origen se descartó. Los hallazgos repetidos se fusionaron en la acción indicada.
