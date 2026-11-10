---
id: PM-01
servicio: cartservice
tipo_doc: postmortem
mecanismo: scale_zero
plataforma: kubernetes
app: online-boutique
fecha: 2026-11-09
corrida_chaosforge_id: d7db0523-07da-4883-95a6-95c195644553
revision_lake: V3-rev1-2026-11-09
revision: 1
fuente: "datos/PM-01/corrida.yaml; datos/PM-01/eventos-k8s.json; datos/PM-01/logs-warning-o-mas.json; datos/PM-01/logs-boutique.json (truncado a 20000 entradas); datos/PM-01/estado-final.txt; datos/PM-01/observaciones.json (no disponible); postmortems/corridas.log"
conjunto: historial
---
# PM-01 · cartservice · scale_zero

> **REGLA (decisión 13).**
> - Las señales se pegan **tal cual** aparecieron: líneas de log y eventos con su timestamp, sin editar, resumir ni traducir. Se permite omitir líneas repetidas dejando una nota de omisión con el conteo y el rango de tiempo; nunca se edita una línea.
> - Lo que se pega aquí no se interpreta. La interpretación (resumen, línea de tiempo razonada, causa raíz, lecciones) va **separada y al final**.
> - Si una fuente no tenía datos en la ventana, se escribe `SIN_DATOS` y se indica la fuente. No se rellena.
>
> Este documento es un **antecedente, no evidencia**: no confirma por sí mismo un diagnóstico futuro (decisión 12).
>
> **Sin culpables (blameless):** se describen sistemas, señales y decisiones, nunca personas.
>
> **Fragmentación:** se divide por sección (`## …`) y cada fragmento enlaza a este id.

## Metadatos
| Campo | Valor |
|---|---|
| id | PM-01 |
| servicio | cartservice |
| mecanismo | scale_zero (parámetros: replicas=0, duración=120 s; después se restaura a 1 réplica) |
| fecha | 2026-11-09 |
| corrida ChaosForge id | `d7db0523-07da-4883-95a6-95c195644553` |
| revisión Lake | V3-rev1-2026-11-09 (README: "Revisión 1 · 2026-11-09") |
| ventana exportada | 2026-11-09T22:36:04Z – 2026-11-09T22:49:05Z (desde 5 min antes de la inyección hasta 5 min después de la recuperación; `datos/PM-01/corrida.yaml`) |
| periodo de falla (para conteos) | 2026-11-09T22:41:04Z – 2026-11-09T22:44:05Z (inicio y "Restaurado" en `postmortems/corridas.log`) |
| tráfico | loadgenerator réplicas=1 (`loadgenerator listo: [1]` en `corridas.log`); `USERS` y `RATE`: no registrado |
| exportado por / fecha | script `postmortems/correr_corridas.sh` / 2026-11-09T22:52:10Z |

## Señales observadas (crudas, copiadas tal cual: líneas de log y eventos con timestamp)
Formato de cada línea de log: `timestamp  severity  servicio/pod  mensaje`. Cuando el log es JSON (frontend), el mensaje se muestra como `message | error=… | http.req.method=… | http.req.path=…`, con los valores de cada campo copiados tal cual.

### Eventos de Kubernetes (namespace boutique)
```text
2026-11-09T22:41:06Z  Normal  ScalingReplicaSet  Deployment/cartservice  Scaled down replica set cartservice-696588d894 from 1 to 0
2026-11-09T22:41:06Z  Normal  SuccessfulDelete  ReplicaSet/cartservice-696588d894  Deleted pod: cartservice-696588d894-nrw4s
2026-11-09T22:41:06Z  Normal  Killing  Pod/cartservice-696588d894-nrw4s  Stopping container server
2026-11-09T22:41:08Z  Warning  Unhealthy  Pod/cartservice-696588d894-nrw4s  Readiness probe failed: timeout: failed to connect service "10.48.1.168:7070" within 1s: context deadline exceeded
2026-11-09T22:43:07Z  Normal  ScalingReplicaSet  Deployment/cartservice  Scaled up replica set cartservice-696588d894 from 0 to 1
2026-11-09T22:43:07Z  Normal  SuccessfulCreate  ReplicaSet/cartservice-696588d894  Created pod: cartservice-696588d894-shbh2
2026-11-09T22:43:07Z  Normal  Scheduled  Pod/cartservice-696588d894-shbh2  Successfully assigned boutique/cartservice-696588d894-shbh2 to gk3-chaosforge-lab-nap-9wa8vr0j-68bc90b0-vp9l
2026-11-09T22:43:08Z  Normal  Pulled  Pod/cartservice-696588d894-shbh2  Container image "us-central1-docker.pkg.dev/google-samples/microservices-demo/cartservice:v0.10.4" already present on machine and can be accessed by the pod
2026-11-09T22:43:08Z  Normal  Created  Pod/cartservice-696588d894-shbh2  Container created
2026-11-09T22:43:09Z  Normal  Started  Pod/cartservice-696588d894-shbh2  Container started
2026-11-09T22:43:28Z  Warning  Unhealthy  Pod/cartservice-696588d894-shbh2  Liveness probe failed: timeout: health rpc did not complete within 1s
```
(11 eventos en `datos/PM-01/eventos-k8s.json`; todos pegados.)
### Logs del servicio objetivo
Severidad ≥ WARNING (`datos/PM-01/logs-warning-o-mas.json`): `SIN_DATOS (0 entradas en la ventana)`.
Todas las severidades (`datos/PM-01/logs-boutique.json`, truncado; extracto desde 2026-11-09T22:40:49Z hasta 2026-11-09T22:44:15Z, deduplicado por patrón):
```text
2026-11-09T22:40:50.123684583Z  INFO  cartservice/cartservice-696588d894-nrw4s  GetCartAsync called with userId=a6c22194-4aad-4a27-b24a-a7ddaa6fcf3c
  (38 líneas más con el mismo patrón en ese pod entre 2026-11-09T22:40:50.123684583Z y 2026-11-09T22:41:06.135749245Z omitida(s); solo cambian ids/números)
2026-11-09T22:40:52.644350915Z  INFO  cartservice/cartservice-696588d894-nrw4s  AddItemAsync called with userId=af67ffed-5182-4c86-b002-fd4298945530, productId=2ZYFJ3GM2N, quantity=7
  (3 líneas más con el mismo patrón en ese pod entre 2026-11-09T22:40:52.644350915Z y 2026-11-09T22:41:06.176073953Z omitida(s); solo cambian ids/números)
2026-11-09T22:40:55.453318728Z  INFO  cartservice/cartservice-696588d894-nrw4s  Checking CartService Health
  (2 líneas más con el mismo patrón en ese pod entre 2026-11-09T22:40:55.453318728Z y 2026-11-09T22:41:05.452385321Z omitida(s); solo cambian ids/números)
2026-11-09T22:40:59.418477864Z  INFO  cartservice/cartservice-696588d894-nrw4s  EmptyCartAsync called with userId=317debae-da1f-4d5e-b026-38fc23f44d49
2026-11-09T22:41:06.157169624Z  INFO  cartservice/cartservice-696588d894-nrw4s  info: Microsoft.Hosting.Lifetime[0]
2026-11-09T22:41:06.157235974Z  INFO  cartservice/cartservice-696588d894-nrw4s        Application is shutting down...
2026-11-09T22:43:14.664224151Z  INFO  cartservice/cartservice-696588d894-shbh2  info: Microsoft.Hosting.Lifetime[14]
  (3 líneas más con el mismo patrón en ese pod entre 2026-11-09T22:43:14.664224151Z y 2026-11-09T22:43:14.670488800Z omitida(s); solo cambian ids/números)
2026-11-09T22:43:14.664375651Z  INFO  cartservice/cartservice-696588d894-shbh2        Now listening on: http://[::]:7070
2026-11-09T22:43:14.667225250Z  INFO  cartservice/cartservice-696588d894-shbh2        Application started. Press Ctrl+C to shut down.
2026-11-09T22:43:14.670483280Z  INFO  cartservice/cartservice-696588d894-shbh2        Hosting environment: Production
2026-11-09T22:43:14.670494630Z  INFO  cartservice/cartservice-696588d894-shbh2        Content root path: /app
2026-11-09T22:43:29.578970712Z  INFO  cartservice/cartservice-696588d894-shbh2  info: Grpc.AspNetCore.Server.ServerCallHandler[14]
  (1 línea más con el mismo patrón en ese pod entre 2026-11-09T22:43:29.578970712Z y 2026-11-09T22:43:29.661128806Z omitida(s); solo cambian ids/números)
2026-11-09T22:43:29.579053432Z  INFO  cartservice/cartservice-696588d894-shbh2        Error reading message.
2026-11-09T22:43:29.579059512Z  INFO  cartservice/cartservice-696588d894-shbh2        System.IO.IOException: The client reset the request stream.
         at Microsoft.AspNetCore.Server.Kestrel.Core.Internal.Http.HttpRequestPipeReader.ReadAsync(CancellationToken cancellationToken)
         at Grpc.AspNetCore.Server.Internal.PipeExtensions.ReadSingleMessageAsync[T](PipeReader input, HttpContextServerCallContext serverCallContext, Func`2 deserializer)
  (1 línea más con el mismo patrón en ese pod entre 2026-11-09T22:43:29.579059512Z y 2026-11-09T22:43:29.661225956Z omitida(s); solo cambian ids/números)
2026-11-09T22:43:29.661217226Z  INFO  cartservice/cartservice-696588d894-shbh2        Service method 'Check' canceled.
2026-11-09T22:43:30.372609679Z  INFO  cartservice/cartservice-696588d894-shbh2  Checking CartService Health
  (8 líneas más con el mismo patrón en ese pod entre 2026-11-09T22:43:30.372609679Z y 2026-11-09T22:44:09.878995605Z omitida(s); solo cambian ids/números)
2026-11-09T22:43:37.334932352Z  INFO  cartservice/cartservice-696588d894-shbh2  GetCartAsync called with userId=9b3f54e2-64fe-41e2-8adf-06d95414fb88
  (57 líneas más con el mismo patrón en ese pod entre 2026-11-09T22:43:37.334932352Z y 2026-11-09T22:44:15.885383192Z omitida(s); solo cambian ids/números)
2026-11-09T22:43:39.169883450Z  INFO  cartservice/cartservice-696588d894-shbh2  EmptyCartAsync called with userId=9b3f54e2-64fe-41e2-8adf-06d95414fb88
  (8 líneas más con el mismo patrón en ese pod entre 2026-11-09T22:43:39.169883450Z y 2026-11-09T22:44:15.926211959Z omitida(s); solo cambian ids/números)
2026-11-09T22:43:56.335536832Z  INFO  cartservice/cartservice-696588d894-shbh2  AddItemAsync called with userId=2563a63f-4328-4ca2-98ed-def8d2a061a3, productId=LS4PSXUNUM, quantity=6
  (6 líneas más con el mismo patrón en ese pod entre 2026-11-09T22:43:56.335536832Z y 2026-11-09T22:44:15.774354229Z omitida(s); solo cambian ids/números)
```
(146 líneas del objetivo en el extracto; 1243 en todo `logs-boutique.json`.)
### Logs de llamadores y otros servicios del namespace (severity ≥ WARNING)
```text
2026-11-09T22:41:06.240622949Z  ERROR  frontend/frontend-84fc9dbb74-rqz7c  request error | error=could not retrieve cart: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 10.49.8.13:7070: connect: connection refused" | http.req.method=GET | http.req.path=/cart
  (114 líneas más con el mismo patrón en frontend entre 2026-11-09T22:41:06.240622949Z y 2026-11-09T22:43:53.572114886Z omitida(s); solo cambian ids/números; ver datos/PM-01/logs-warning-o-mas.json)
2026-11-09T22:41:06.469373503Z  ERROR  frontend/frontend-84fc9dbb74-rqz7c  request error | error=could not retrieve cart: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 10.49.8.13:7070: connect: connection refused" | http.req.method=GET | http.req.path=/
  (128 líneas más con el mismo patrón en frontend entre 2026-11-09T22:41:06.469373503Z y 2026-11-09T22:43:53.560889697Z omitida(s); solo cambian ids/números; ver datos/PM-01/logs-warning-o-mas.json)
2026-11-09T22:41:07.568793490Z  ERROR  frontend/frontend-84fc9dbb74-rqz7c  request error | error=could not retrieve cart: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 10.49.8.13:7070: connect: connection refused" | http.req.method=GET | http.req.path=/product/L9ECAV7KIM
  (226 líneas más con el mismo patrón en frontend entre 2026-11-09T22:41:07.568793490Z y 2026-11-09T22:43:53.453924644Z omitida(s); solo cambian ids/números; ver datos/PM-01/logs-warning-o-mas.json)
2026-11-09T22:41:07.862995740Z  ERROR  frontend/frontend-84fc9dbb74-rqz7c  request error | error=failed to add to cart: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 10.49.8.13:7070: connect: connection refused" | http.req.method=POST | http.req.path=/cart
  (47 líneas más con el mismo patrón en frontend entre 2026-11-09T22:41:07.862995740Z y 2026-11-09T22:43:52.453195140Z omitida(s); solo cambian ids/números; ver datos/PM-01/logs-warning-o-mas.json)
2026-11-09T22:41:41.779293900Z  ERROR  frontend/frontend-84fc9dbb74-rqz7c  request error | error=failed to complete the order: rpc error: code = Internal desc = cart failure: failed to get user cart during checkout: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 10.49.8.13:7070: connect: connection refused" | http.req.method=POST | http.req.path=/cart/checkout
  (10 líneas más con el mismo patrón en frontend entre 2026-11-09T22:41:41.779293900Z y 2026-11-09T22:43:26.830949766Z omitida(s); solo cambian ids/números; ver datos/PM-01/logs-warning-o-mas.json)
2026-11-09T22:46:42.326955753Z  ERROR  paymentservice/paymentservice-7987f697ff-82492  UnacceptedCreditCard [Error]: Sorry, we cannot process visa_electron credit cards. Only VISA or MasterCard is accepted.
2026-11-09T22:46:42.329188133Z  ERROR  frontend/frontend-84fc9dbb74-rqz7c  request error | error=failed to complete the order: rpc error: code = Internal desc = failed to charge card: could not charge the card: rpc error: code = Code(400) desc = Sorry, we cannot process visa_electron credit cards. Only VISA or MasterCard is accepted. | http.req.method=POST | http.req.path=/cart/checkout
  (11 líneas más de marcos de pila de trazas multilínea (`File …`, `at …`, `^^^`, `code: …`, `}`) omitida(s); ver datos/PM-01/logs-warning-o-mas.json)
```
### Observaciones del observador ChaosForge (/api/observations, si aplica)
```text
SIN_DATOS (0 entradas en la ventana). Contenido de datos/PM-01/observaciones.json:
{"no_disponible": "el ChaosForge desplegado no expone /api/observations"}
```
### Estado de objetos al inicio y al final de la ventana
Al inicio: `SIN_DATOS` (no se capturó `kubectl` antes de la inyección).

Al final (`datos/PM-01/estado-final.txt`; hora de captura no registrada en el archivo, exportado 2026-11-09T22:52:10Z; extracto: cabeceras y filas de cartservice):
```text
NAME                                    READY   UP-TO-DATE   AVAILABLE   AGE   CONTAINERS   IMAGES                                                                                       SELECTOR
deployment.apps/cartservice             1/1     1            1           23d   server       us-central1-docker.pkg.dev/google-samples/microservices-demo/cartservice:v0.10.4             app=cartservice
NAME                                         READY   STATUS    RESTARTS   AGE     IP            NODE                                            NOMINATED NODE   READINESS GATES
pod/cartservice-696588d894-shbh2             1/1     Running   0          9m3s    10.48.1.173   gk3-chaosforge-lab-nap-9wa8vr0j-68bc90b0-vp9l   <none>           <none>
NAME                                                         ADDRESSTYPE   PORTS   ENDPOINTS     AGE
endpointslice.discovery.k8s.io/cartservice-dm4x5             IPv4          7070    10.48.1.173   23d
```

---
*A partir de aquí empieza la interpretación. Todo lo que sigue se escribe después de pegar las señales.*

## Resumen
Durante unos 2 min 47 s (22:41:06 – 22:43:53 UTC) cartservice no tuvo instancias, porque su Deployment se escaló a 0 réplicas, y frontend devolvió HTTP 500 en casi todas las rutas que leen el carrito: inicio, producto, carrito, agregar al carrito y checkout. Se recuperó solo cuando ChaosForge volvió a 1 réplica, a las 22:43:07, y el pod nuevo empezó a atender.

## Línea de tiempo (UTC)
| t (UTC) | Qué ocurrió | Señal que lo respalda (fuente y línea de arriba) |
|---|---|---|
| 22:41:04 | Inyección solicitada (`scale_zero`, 120 s) | `corridas.log`: `Experimento: d7db0523-… (inicio 2026-11-09T22:41:04Z)` |
| 22:41:06 | Disparador: Deployment escalado de 1 a 0; se borra y detiene el pod `…-nrw4s` | Eventos `ScalingReplicaSet … from 1 to 0`, `SuccessfulDelete`, `Killing` |
| 22:41:06.157 | El objetivo registra su apagado (último log del pod viejo) | cartservice `Application is shutting down...` |
| 22:41:06.240 | Primer síntoma en un llamador: frontend no puede leer el carrito (`connection refused` a `…:7070`) | frontend `could not retrieve cart: … dial tcp 10.49.8.13:7070: connect: connection refused` |
| 22:41:07.862 | Falla también agregar al carrito (POST /cart) | frontend `failed to add to cart: …` |
| 22:41:08 | Sonda de readiness falla en el pod que se está terminando | Evento `Unhealthy … Readiness probe failed` |
| 22:41:41.779 | Primer checkout fallido: checkoutservice no obtiene el carrito | frontend `failed to complete the order: … cart failure: failed to get user cart during checkout` |
| 22:43:07 | Restauración: Deployment escalado de 0 a 1; pod nuevo `…-shbh2` | Eventos `ScalingReplicaSet … from 0 to 1`, `SuccessfulCreate`, `Scheduled` |
| 22:43:09 – 22:43:14 | Contenedor iniciado; el servidor escucha en 7070 | Evento `Started`; cartservice `Now listening on: http://[::]:7070` |
| 22:43:28 – 22:43:29 | Sonda de liveness falla una vez durante el arranque | Evento `Liveness probe failed: timeout: health rpc did not complete within 1s`; cartservice `Service method 'Check' canceled.` |
| 22:43:37 | El pod nuevo atiende la primera lectura de carrito | cartservice `GetCartAsync called …` en `…-shbh2` |
| 22:43:53.572 | Último error de frontend atribuible a cartservice | último `could not retrieve cart` (nota de omisión del bloque de llamadores) |
| 22:44:05 | ChaosForge informa "Restaurado" | `corridas.log`: `Restaurado: 2026-11-09T22:44:05Z` |
| 22:44:05 – 22:49:05 | Recuperación estable: ningún error de cartservice hasta el fin de la ventana | `logs-warning-o-mas.json`: 0 líneas con `cart` después de 22:43:53; la única línea posterior es el rechazo `visa_electron` de 22:46:42, que es ruido de base |

## Detección
- **Cómo y cuándo se hace visible:** a las 22:41:06.240, 0,24 s después del evento de escalado, frontend registra ERROR `could not retrieve cart … connect: connection refused`. Es inmediato porque frontend lee el carrito en casi todas sus páginas.
- **Qué señal lo discrimina:** el evento `ScalingReplicaSet "… cartservice-… from 1 to 0"`, junto con `connection refused` hacia el puerto 7070 en el llamador. No aparecen errores de Redis, lo que lo distingue de una falla de redis-cart.
- **Qué NO lo habría detectado:** los logs del propio cartservice, porque sin instancias no hay logs y en la ventana tiene 0 líneas ≥ WARNING. La sonda de readiness del pod viejo solo falla una vez, a las 22:41:08, y no hay evento que diga "0 endpoints". Las sondas `/` y `/cart` de ChaosForge **sí** lo detectan: frontend devuelve 500 en esas rutas.

## Impacto
| Servicio | líneas ≥ WARNING antes (22:36:04–22:41:04) | durante la falla (22:41:04–22:44:05) | después (22:44:05–22:49:05) | patrón dominante |
|---|---|---|---|---|
| frontend | 0 | 530 (ERROR) | 1 | `could not retrieve cart` (471), `failed to add to cart` (48), `failed to complete the order … cart failure` (11) |
| paymentservice | 0 | 0 | 12 | `UnacceptedCreditCard … visa_electron` (1 error + 11 líneas de traza): ruido de base, no relacionado |
| cartservice | 0 | 0 | 0 | — (sin instancias no hay logs) |

- **Operaciones de usuario afectadas:** según `request complete` de frontend en `logs-boutique.json` durante la falla:
  - Inicio `GET /`: 129 respuestas 500 y 5 respuestas 200.
  - Producto `GET /product/*`: 227 respuestas 500 y 16 respuestas 200.
  - Ver carrito `GET /cart`: 115 respuestas 500 y 13 respuestas 200.
  - Agregar al carrito `POST /cart`: 48 respuestas 500 y 5 respuestas 302.
  - Checkout `POST /cart/checkout`: 11 respuestas 500 y 7 respuestas 200.
  - Sin errores: `POST /setCurrency` (43 respuestas 302) y `/_healthz` (36 respuestas 200).
  - En los 5 min previos hubo 0 respuestas 5xx sobre 874 completadas.
- **Servicios con síntomas (víctimas):** frontend, que es llamador directo. checkoutservice también es llamador directo según `topologia.yaml`: su fallo aparece dentro del error de frontend (`cart failure: failed to get user cart during checkout`), pero checkoutservice no registró líneas ≥ WARNING propias.
- **Duración del impacto observable:** 2 min 47 s (22:41:06.240 → 22:43:53.572). Supera en unos 46 s el tiempo con 0 réplicas (22:41:06 → 22:43:07).
- **Lo que no se pudo observar:**
  - `/api/observations`: SIN_DATOS.
  - `logs-boutique.json` está truncado en 22:46:04.150, antes del fin de la ventana (22:49:05). Los conteos INFO o DEBUG posteriores a esa hora no existen en el export. El periodo de falla está completo.
  - `USERS` y `RATE` no se registraron.

## Causa raíz y disparador
- **Disparador (trigger):** el escalado del Deployment `cartservice` de 1 a 0 réplicas a las 22:41:06. Fue una inyección controlada `scale_zero` de 120 s.
- **Causa raíz:** cartservice quedó sin instancias listas ni endpoints. Los llamadores (frontend y, a través de él, checkoutservice) recibieron `connection refused` en `:7070` y frontend convirtió ese error en HTTP 500.

| componente | t_inicio (UTC) | razón (vocabulario cerrado) | runbook |
|---|---|---|---|
| cartservice | 2026-11-09T22:41:06Z | servicio-sin-instancias | RB-01 |

Condición (texto corto): `instancias_deseadas == 0` desde 22:41:06 hasta 22:43:07, con `ScalingReplicaSet … to 0` antes del primer error de los llamadores, que nombran el puerto 7070.

## Remediación
- **Acción aplicada:** "Restaurar" automático de ChaosForge al vencer los 120 s. El Deployment vuelve a 1 réplica a las 22:43:07, según el evento `Scaled up … from 0 to 1`.
- **Verificación:**
  - El pod nuevo escucha desde 22:43:14 y atiende `GetCartAsync` desde 22:43:37.
  - El último error de frontend es de 22:43:53.
  - No hay más errores con `cart` hasta el fin del export ≥ WARNING (22:46:42); son 3 min sin recaídas.
  - `estado-final.txt` muestra `cartservice 1/1` y un EndpointSlice con `10.48.1.173`.

## Lecciones aprendidas
### Qué salió bien
- El evento de escalado y el primer error del llamador están separados por 0,24 s, y el mensaje del error nombra la operación (`could not retrieve cart`) y el puerto (`:7070`). El orden temporal de RB-01 se cumple sin ambigüedad.
- No hubo ruido de base antes de la inyección: 0 líneas ≥ WARNING en 5 min.
### Qué salió mal
- El impacto se extendió más que la falla. frontend siguió fallando unos 46 s después del escalado a 1 y unos 16 s después de que el pod nuevo ya atendía. Esto es compatible con el backoff de reconexión gRPC del cliente [INF].
- La falla de un servicio "de carrito" tumbó también inicio y producto: frontend consulta el carrito en cada página.
### Dónde tuvimos suerte
- El pod nuevo arrancó con la imagen ya presente en el nodo (`already present on machine`). Con una descarga lenta de imagen, la ventana de impacto habría sido mayor.
- La única falla de liveness del pod nuevo (22:43:28) no provocó un reinicio.
### Qué confundió
- Los errores nombran la IP del Service (`10.49.8.13:7070`) y no el nombre `cartservice:7070`. Para atribuirlos hay que cruzar el puerto con `topologia.yaml`.
- Los logs del pod nuevo de cartservice incluyen `Error reading message.` y `System.IO.IOException` con severidad INFO durante el arranque, lo que puede parecer un síntoma.
- El rechazo `visa_electron` de paymentservice (22:46:42) es ruido de base del generador de carga y no tiene relación con esta falla.
### Brechas del Lake
- RB-01, corroborante de llamadores: dice que los errores "nombran `<svc>:<puerto>`", pero los observados nombran `IP-del-Service:puerto`. Hay que admitir coincidencia por puerto + topología.
- Ficha de cartservice: le falta que la caída afecta también a `GET /` y `GET /product/*`, y no solo a `/cart` y checkout.
- RB-01 y fichas en general: no registran que el impacto dura más que el periodo con 0 réplicas, por la reconexión del cliente. Conviene mencionarlo para no tomar como "otra falla" los errores posteriores al escalado a 1.

## Acciones
| Acción | Tipo (mitigar / prevenir / proceso / otro) | Responsable | Seguimiento |
|---|---|---|---|
| Ajustar en RB-01 el corroborante de llamadores para aceptar `IP:puerto` del Service, cruzado con `topologia.yaml` | proceso | por asignar | hallazgo para la próxima revisión del Lake |
| Agregar a la ficha de cartservice las rutas afectadas observadas (`/`, `/product/*`, `/cart`, `POST /cart`, checkout) | proceso | por asignar | hallazgo para la próxima revisión del Lake |
| Documentar en RB-01 que los errores de llamadores pueden seguir unos 15–60 s después de que el objetivo vuelve a estar listo | proceso | por asignar | hallazgo para la próxima revisión del Lake |
| Evaluar ≥ 2 réplicas o un PodDisruptionBudget para cartservice (recomendación; no se aplica en el laboratorio) | prevenir | por asignar | propuesta, sin cambio en el clúster |
| Registrar `USERS` y `RATE` del loadgenerator en cada corrida | proceso | por asignar | `correr_corridas.sh` |

## Información de apoyo
- Metadatos de la corrida: [`datos/PM-01/corrida.yaml`](datos/PM-01/corrida.yaml) e id/horas en [`corridas.log`](corridas.log)
- Eventos: [`datos/PM-01/eventos-k8s.json`](datos/PM-01/eventos-k8s.json)
- Logs ≥ WARNING (completos): [`datos/PM-01/logs-warning-o-mas.json`](datos/PM-01/logs-warning-o-mas.json)
- Logs de todas las severidades (truncado a 20000 entradas; última entrada 2026-11-09T22:46:04.150388545Z, la ventana termina 2026-11-09T22:49:05Z): [`datos/PM-01/logs-boutique.json`](datos/PM-01/logs-boutique.json)
- Estado final: [`datos/PM-01/estado-final.txt`](datos/PM-01/estado-final.txt)
- Observaciones: [`datos/PM-01/observaciones.json`](datos/PM-01/observaciones.json) (no disponible)
- Topología y ficha: [`../topologia.yaml`](../topologia.yaml), [`../fichas/cartservice.md`](../fichas/cartservice.md); runbook [`../runbooks/RB-01-servicio-sin-instancias.md`](../runbooks/RB-01-servicio-sin-instancias.md)

---
*Referencias del formato:* Google SRE Book, Apéndice D "Example Postmortem" (https://sre.google/sre-book/example-postmortem/); Google SRE Book, cap. 15 "Postmortem Culture: Learning from Failure" (https://sre.google/sre-book/postmortem-culture/); PagerDuty Postmortem Template (https://response.pagerduty.com/after/post_mortem_template/).
