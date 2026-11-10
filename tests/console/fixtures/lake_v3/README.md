# Context Lake V3: piloto Online Boutique en GKE

Revisión 2 · 2026-11-09 · Proyecto `tider-ops`, clúster `chaosforge-lab`, región `us-central1`, namespace `boutique`. Online Boutique v0.10.4: la imagen validada por ChaosForge es la de cartservice, y para el resto de servicios se asume la misma versión.

Este paquete es el **mapa previo** que usa Tider para saber dónde buscar. No es un veredicto. La fuente de verdad son los logs, los eventos de Kubernetes y el estado observado (decisión 3).

## Qué hay
| Ruta | Contenido | Tipo de documento |
|---|---|---|
| `topologia.yaml` | 12 componentes, 16 aristas (from, to, protocolo, variable, valor) y discrepancias con V1, V2 y `catalog.py` | `topologia` |
| `fichas/*.md` | Una ficha por cada uno de los 11 servicios de la tienda, más `loadgenerator`, marcado como generador de tráfico | `ficha` |
| `runbooks/RB-0N-*.md` | Catálogo v1 de modos de falla. RB-01 a RB-04: a validar con ChaosForge. RB-05 y RB-06: declarados, no validados | `runbook` |
| `postmortems/PM-0N-*.md` | Los 5 postmortems del historial (`scale_zero` sobre cartservice, productcatalogservice, currencyservice, paymentservice y adservice). Escritos contra la revisión 1 (`revision_lake: V3-rev1-2026-11-09`) y congelados: no se editan en revisiones posteriores | `postmortem` |
| `postmortems/PLANTILLA.md` | Plantilla con las señales crudas separadas de la conclusión | `postmortem` (plantilla) |
| `postmortems/PENDIENTES.md` | Los 5 postmortems del historial: qué corrida ejecutar y qué exportar | No se carga en el índice |

## Unidad de fragmentación por tipo (decisión 12)
| Tipo | Unidad | Motivo |
|---|---|---|
| Topología | **No se fragmenta.** Se carga como grafo estructurado desde `topologia.yaml` | Las aristas son datos, no texto |
| Ficha | **Un fragmento por ficha** (300–600 palabras, plantilla fija) | Responde "¿qué es X y cómo se ve cuando falla?" |
| Runbook | **Procedimiento completo, sin cortar** | Un paso suelto fuera de contexto es peligroso |
| Postmortem | **Un fragmento por sección `##`**, con enlace al id del padre | Las señales crudas se recuperan por separado de la conclusión |
| Catálogo de fallas | Datos estructurados que apuntan al runbook por `id` (RB-0N) | Las firmas se evalúan de forma determinista |

La búsqueda es híbrida: léxica (BM25) más semántica, con filtros por metadatos.

## Metadatos comunes
Todo fragmento lleva `servicio`, `tipo_doc`, `mecanismo`, `fecha`, `revision` y `fuente`. Además lleva `plataforma: kubernetes` y `app: online-boutique`.
- Las fichas no declaran `mecanismo`. El cargador debe asignar `mecanismo: null`.
- Los runbooks usan `servicio: "*"` y añaden `id`, `modo_falla` y `estado_validacion`.
- Los postmortems añaden `corrida_chaosforge_id`, `revision_lake` y `conjunto: historial`.

## Marcas en el texto
- **[conocimiento público]:** dato de los manifiestos o del código público de microservices-demo. Los manifiestos no están en el repositorio (`fetch-boutique.sh` los clona en `vendor/`). Hay que validarlo contra el clúster.
- **[esperado, validar con ChaosForge]:** mensaje de log o síntoma esperable que todavía no se ha observado en una corrida. No es evidencia.
- **[observado en historial]:** patrón visto en las señales crudas de un postmortem del historial (PM-01 a PM-05), citado por id. Sirve para saber qué buscar; no es evidencia del incidente que se analiza.
- **[INF]** y **[LIT]:** inferencia propia y literatura, respectivamente, según `recomend/_bibliografia_firmas.md`.

## Reglas
1. **Un documento no confirma un diagnóstico.** Las fichas, los runbooks y los postmortems indican dónde buscar y qué firma evaluar. Una hipótesis que solo se apoye en documentos se rechaza (el Juez exige citas `S01…` de evidencia real).
   - Si el Lake y la evidencia no coinciden, se reporta como hallazgo.
   - La ausencia de logs no prueba que un servicio esté sano.
2. **Separación entre historial y no vistos (decisiones 13 y 15).**
   - Solo puede haber postmortems de cartservice, productcatalogservice, currencyservice, paymentservice y adservice, con mecanismo `scale_zero`, provenientes de corridas de **historial**.
   - Nunca debe haber postmortems de redis-cart, checkoutservice, shippingservice, emailservice, recommendationservice ni frontend.
   - Las fichas y los runbooks no mencionan resultados de experimentos concretos. Excepción desde la revisión 2: pueden citar formatos de mensaje y tiempos observados en los postmortems del **historial**, con la marca [observado en historial] y el id del PM. Nunca resultados de corridas de evaluación.
   - Las corridas de evaluación nunca se documentan en el Lake.
   - La revisión se congela antes de la campaña.
3. **Solo asesor.** Toda reparación está encabezada por "ACCIÓN HUMANA: Tider no ejecuta esto". Tider solo sugiere pasos de lectura.
   - RB-01 a RB-04: la acción de reparación solo se muestra cuando la firma está CONFIRMADA y el runbook fue validado con ChaosForge; mientras tanto se presenta como sugerencia no verificada.
   - RB-05 y RB-06 (declarados, no validados) no incluyen comandos de cambio: solo pasos de diagnóstico de lectura para que la persona decida, hasta que el modo de falla se valide con un inyector (decisión 21).

## Cómo cargarlo
1. Retirar de la interfaz de Tider los documentos de V1 y V2. V3 los reemplaza, y cargarlos juntos crea una falsa corroboración. Mover archivos locales no actualiza el índice en memoria del servidor.
2. Cargar `topologia.yaml` como grafo estructurado. Si el cargador actual no lo soporta, mantener el `.drawio` de V2 y usar este YAML como referencia para corregir `providers/catalog.py`.
3. Cargar `fichas/*.md` y `runbooks/*.md`. Cada archivo es un fragmento: hay que desactivar el corte por encabezado de 900 caracteres para estos tipos.
4. Cargar `postmortems/PM-*.md` solo cuando existan. No cargar `PLANTILLA.md` ni `PENDIENTES.md`.
5. Registrar la revisión cargada (Lake revisión 2: `revision: 2` en RB-01 y en la ficha de paymentservice; `revision: 1` en el resto) y verificarla con la pregunta: "¿Qué servicios dependen de productcatalogservice y qué operaciones de usuario se rompen si se cae?". Comprobar el contenido de los fragmentos recuperados.

## Historial de revisiones
### Revisión 1 → revisión 2 (2026-11-09)
Los 5 postmortems del historial se escribieron contra la revisión 1. Sus secciones "Brechas del Lake" y "Qué confundió" motivan estos cambios. Los postmortems no se modifican.

**`runbooks/RB-01-servicio-sin-instancias.md` (revision 2)**
- El corroborante de llamadores ya no espera `<svc>:<puerto>`: los errores nombran `IP-del-ClusterIP:puerto` (PM-01 a PM-05). Nueva sección "Cómo atribuir el IP:puerto": resolver con `kubectl -n boutique get svc -o wide`; puertos ambiguos 50051 (payment, shipping), 6379 (redis-cart, chaosforge-proxy) y 8080 de contenedor (frontend, email, recommendation) (PM-04).
- Formatos de error observados: Go `dial tcp …: connect: connection refused`, Python `ipv4:…: Failed to connect to remote host: Connection refused` que frontend recibe como `code = Unknown` (PM-02), variante `DeadlineExceeded` y severidad WARNING (PM-05).
- El llamador que registra puede no ser el dependiente directo: checkoutservice no registró líneas ≥ WARNING en ninguna corrida; su falla aparece anidada en el error de frontend (PM-01 a PM-04). Agrupar trazas multilínea antes de comparar volúmenes (PM-02).
- El primer error puede llegar segundos después del `Killing` (PM-03) o tarde por poco tráfico (PM-04).
- Nueva sección "Ruido que no es síntoma": líneas de apagado y arranque del propio servicio (PM-01, PM-03, PM-04, PM-05) y rechazo `visa_electron` como ruido de base.
- Nueva sección "Servicios con poco tráfico": pocas líneas ≠ sano; comprobar tráfico (`[PlaceOrder]`) (PM-04).
- Verificación de la recuperación: cola de errores de 47 a 89 s tras el escalado a 1; criterio de 2 min seguidos sin errores nuevos; no leer la cola como incidente nuevo (PM-01 a PM-05).
- Consultas de Cloud Logging: buscar por IP:puerto, no por nombre del servicio; consulta de tráfico de checkout.
- Nota de "Pendiente de validación": la firma se contrastó con PM-01 a PM-05; el escalado manual no se ejerció. `estado_validacion` no cambia.

**`fichas/paymentservice.md` (revision 2)** (PM-04; ruido de base en PM-01, PM-02, PM-05)
- El síntoma lo registra frontend (`failed to charge card … dial tcp <IP>:50051: connect: connection refused` en `POST /cart/checkout`), no checkoutservice. "Señales a revisar" corregido.
- Puerto 50051 compartido con shippingservice: atribuir por texto o por IP.
- Tráfico bajo (18 `[PlaceOrder]` en 2 min 27 s) y `[PlaceOrder]` sin `payment went through` como señal.
- Ruido de arranque (`DeprecationWarning`, severidad ERROR) y rechazo `visa_electron` (`Code(400)`) como no síntomas.
- Cola de recuperación (último error 54 s después del arranque del servidor).
- Supera las 600 palabras de la plantilla de ficha por las líneas de log textuales.

**`README.md`:** revisión 2, fila de postmortems, marca [observado en historial], excepción en la regla 2 y este historial.

### Pendiente para la revisión 3
Mismas brechas en documentos que esta revisión no toca:
- **`<svc>:<puerto>` en el texto del error** en las fichas de adservice (`adservice:9555`), cartservice (`cartservice:7070`), checkoutservice (`checkoutservice:5050`), emailservice (`emailservice:5000`), productcatalogservice (`productcatalogservice:3550`), recommendationservice (`recommendationservice:8080`), redis-cart (`cartservice:7070`) y shippingservice ("se lee por el nombre del host", `shippingservice:50051`). Deben decir IP del ClusterIP y remitir a RB-01.
- **Ruido de arranque/apagado con severidad ERROR:** ficha de currencyservice (`DeprecationWarning`, PM-03) y ficha de adservice (`*** shutting down gRPC ads server …`, `WARNING: … sun.misc.Unsafe …`, PM-05). Ambas dicen "Sin instancias, no hay logs" sin esa salvedad. Ficha de cartservice: `Error reading message.` / `System.IO.IOException` INFO al arrancar (PM-01).
- **checkoutservice no registra los errores de sus dependencias:** ficha de checkoutservice ("Logs de checkoutservice de severidad WARNING y ERROR, agrupados por la dependencia") y ficha de shippingservice ("Logs de error de frontend y checkoutservice"). Lo observado es que el error aparece en frontend (PM-01 a PM-04). Shipping y email no tienen postmortem: marcarlo como [INF] por analogía.
- **Ficha de frontend:** "Señal: logs `severity>=ERROR`" no ve los avisos WARNING de anuncios y recomendaciones (PM-02, PM-05).
- **Ficha de cartservice:** la caída afecta también `GET /` y `GET /product/*` (PM-01).
- **Ficha de productcatalogservice:** no escribe logs en sano; recommendationservice multiplica las líneas ERROR por traza; `/cart` puede dar 200 degradado (PM-02).
- **Ficha de currencyservice:** `POST /cart` no se ve afectado (PM-03).
- **Ficha de adservice:** `DeadlineExceeded` como variante del síntoma y como ruido de base (PM-05).
- **Todas las fichas:** la cola de errores tras la recuperación (PM-01 a PM-05).
- **RB-02 a RB-06:** revisar si asumen `<svc>:<puerto>` en el error (RB-02 cita `redis-cart:6380`).
- **`topologia.yaml`:** registrar los rangos de ClusterIP y de pod observados, y los puertos compartidos, tras validarlos con `kubectl -n boutique get svc -o wide` (D5).
- Fuera del Lake (no son brechas de documento): sondas de ChaosForge sin checkout ni anuncios; límite de 20000 entradas de `logs-boutique.json`; registrar `USERS` y `RATE`.
