---
id: RB-01
modo_falla: servicio-sin-instancias
mecanismo: scale_zero
estado_validacion: a validar con ChaosForge
tipo_doc: runbook
servicio: "*"
plataforma: kubernetes
app: online-boutique
revision: 2
cambios: "rev2: el error del llamador nombra IP-del-Service:puerto, no <svc>:<puerto>, y se resuelve con get svc (puerto 50051 ambiguo); el llamador que registra puede no ser el dependiente directo; demora del primer error; cola de errores tras la recuperación y ventana estable de 2 min; ruido de arranque y apagado; servicios con poco tráfico. Origen: Brechas del Lake de PM-01 a PM-05."
fecha: 2026-11-09
fuente: recomend/_bibliografia_firmas.md §9.3.A; recomend/modelo_comun.md; recomend/_auditoria_consolidada.md (decisiones 14, 18, 21); chaosforge/admin/controller.py; tider/src/tider/console/providers/kubernetes_events.py; postmortems PM-01 a PM-05 (historial, scale_zero, escritos contra rev 1)
---
# RB-01 · Servicio sin instancias

Un servicio no tiene ninguna instancia lista que atienda solicitudes. En el laboratorio, ChaosForge lo provoca con `scale_zero`, que escala el Deployment a 0 réplicas. Puede aplicarlo a los 12 Deployments (decisión 14).

**Respaldo en la literatura:** ITBench PodFailure y ServiceFailure; OpenRCA A.2, según el cual si caen todos los pods de un servicio, la falla es de nivel servicio. Los predicados concretos de Kubernetes son [INF].

## Firma
Se usan los campos del modelo común. Este runbook usa la razón "sin instancias" solo en dos casos: `instancias_deseadas == 0`, o pods que no se pueden programar.

**CONFIRMA**, si se cumple todo lo obligatorio y al menos un corroborante:
- **Obligatorio [INF]:** Servicio `instancias_deseadas == 0`, **o** `instancias_listas == 0` con `instancias_deseadas > 0` por un motivo de programación (`FailedScheduling`). La condición se sostiene al menos 2 lecturas.
- **Obligatorio [INF]:** el EndpointSlice del Service no tiene direcciones listas.
- **Corroborante [INF]:** un Cambio de tipo escalado (evento `ScalingReplicaSet` "Scaled down replica set <svc>-… from 1 to 0") con `t_cambio ≤ t_inicio` del primer error en los llamadores. El orden temporal sigue la literatura [LIT OpenRCA A.5; FChain].
  - El primer error puede llegar segundos después del `Killing`: el pod que se termina sigue atendiendo durante el apagado ordenado (5,8 s en PM-03), y un servicio con poco tráfico tarda hasta la primera solicitud (18,9 s en PM-04) [observado en historial]. Esa demora no invalida el orden.
- **Corroborante [INF]:** Señal en los **llamadores** (ver `topologia.yaml`) que nombra el **IP del ClusterIP y el puerto** del servicio caído, ya resuelto a `<svc>` (ver "Cómo atribuir el IP:puerto"). Formatos observados en historial (PM-01 a PM-05):
  - Clientes Go (frontend): `rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 10.49.8.13:7070: connect: connection refused"`.
  - Cliente Python (recommendationservice): `status = StatusCode.UNAVAILABLE` y `details = "failed to connect to all addresses; last error: UNKNOWN: ipv4:10.49.2.83:3550: Failed to connect to remote host: Connection refused"`. frontend lo recibe como `code = Unknown desc = Exception calling application`: el código real solo está dentro del texto.
  - Variante de timeout: `code = DeadlineExceeded desc = context deadline exceeded` (adservice, PM-05). También aparece como ruido de base fuera de las fallas: solo corrobora junto con `connection refused`.
  - `no healthy upstream` sigue siendo posible con un proxy o malla [INF]; no se observó en historial.
  - La severidad puede ser **WARNING**, no ERROR, cuando el llamador trata la falla como no fatal (anuncios y recomendaciones en frontend). Leer `severity>=WARNING`.

**DESCARTA [INF]:** `instancias_listas ≥ 1` y endpoints listos durante toda la ventana.

**SIN_DATOS:**
- No hay lectura del Deployment ni eventos de la ventana [LIT OpenRCA §2.4].
- La falta de logs del servicio **no** cuenta como evidencia en ningún sentido: un servicio con 0 instancias no escribe.
- Pocas líneas de error en los llamadores tampoco prueban que no hubo impacto. Si no se comprueba que hubo tráfico hacia el servicio en la ventana, el impacto es SIN_DATOS (ver "Servicios con poco tráfico").

**Delegar [INF]:** si `instancias_deseadas > 0` y las instancias existen pero no están listas, la razón no es "sin instancias". Pasar a RB-05 (crash loop), RB-06 (OOM) o RB-02 (configuración).

## Cómo atribuir el IP:puerto
Los errores de los llamadores **no** nombran `<svc>:<puerto>`. Nombran el ClusterIP del Service y su puerto, por ejemplo `dial tcp 10.49.5.115:50051: connect: connection refused` [observado en historial, PM-01 a PM-05]. El Service sigue existiendo con 0 réplicas, así que su ClusterIP se puede resolver durante la falla.

1. Resolver el IP con `kubectl -n boutique get svc -o wide` (lectura). Buscar la fila cuyo `CLUSTER-IP` coincide con el IP del error y cuyo `PORT(S)` contiene el puerto. Esa fila da `<svc>`.
2. Si el IP no es de ningún Service, puede ser un IP de pod. En las corridas de historial los ClusterIP estaban en `10.49.x.x` y los pods en `10.48.x.x` [observado en historial; validar en otro clúster]. Buscar el IP en `kubectl -n boutique get pods -o wide` o en los EndpointSlices.
3. **El puerto por sí solo es ambiguo.** Puertos compartidos según `topologia.yaml`:
   - Puerto de Service **50051**: paymentservice y shippingservice.
   - Puerto **6379**: redis-cart y `chaosforge-proxy` (componente del laboratorio, si está instalado).
   - Puerto de contenedor **8080**: frontend, emailservice y recommendationservice. Solo importa si el error trae un IP de pod; recommendationservice también usa 8080 como puerto de Service.
   
   Con un puerto compartido, la atribución exige resolver el IP o leer la operación en el texto (`failed to charge card` es cobro; un error que nombre el envío es shipping). Nunca atribuir solo por el puerto.

## Cómo distinguir causa de víctima
- **La causa** es el servicio cuyo **propio** Deployment muestra `instancias_listas == 0`. Su cambio (escalado) es el más temprano de la ventana.
- **Las víctimas** son sus llamadores. Tienen instancias listas y **escriben** errores con el IP:puerto del servicio caído. El error de cada víctima empieza en `t_cambio` o después.
- **El servicio que registra el error puede no ser el dependiente directo.** En las 5 corridas de historial, checkoutservice no escribió ninguna línea ≥ WARNING propia: su falla aparece **anidada** dentro del error que registra frontend. Ejemplos observados:
  - payment: `failed to complete the order: rpc error: code = Internal desc = failed to charge card: could not charge the card: rpc error: code = Unavailable … dial tcp 10.49.5.115:50051: connect: connection refused` (PM-04).
  - cart: `… cart failure: failed to get user cart during checkout: …` (PM-01).
  - productcatalog: `… failed to prepare order: failed to get product #"…"` (PM-02).
  - currency: `… failed to prepare order: failed to convert price of "…" to <moneda>` (PM-03).
  
  Para un servicio que solo llama checkoutservice (payment, email, shipping en checkout), buscar el síntoma en los logs de **frontend** en `POST /cart/checkout`, no solo en los de checkoutservice.
- **No contar líneas sin agrupar trazas.** Un llamador Python escribe cada traza línea por línea: recommendationservice produjo 1937 líneas ERROR, más del triple que frontend, y era víctima (PM-02). Una traza es un evento.
- Un servicio sin logs y sin instancias es **candidato a causa**, no "sano".
- Si el servicio caído es redis-cart, la víctima directa es cartservice y la indirecta es frontend.
- **loadgenerator con 0 instancias es un control, no un incidente de la tienda** (decisión 15).

## Ruido que no es síntoma
El propio servicio escalado escribe líneas al apagarse y al arrancar el pod nuevo. **No** son anomalía propia ni síntoma. Patrones observados en historial:
- Node.js (paymentservice PM-04, currencyservice PM-03), severidad ERROR al arrancar: `(node:1) DeprecationWarning: Calling start() is no longer necessary. It can be safely omitted.` y `(Use \`node --trace-deprecation ...\` to show where the warning was created)`.
- Java (adservice PM-05), severidad ERROR: al apagarse `*** shutting down gRPC ads server since JVM is shutting down` y `*** server shut down`; al arrancar `WARNING: A terminally deprecated method in sun.misc.Unsafe has been called` y 3 líneas más `WARNING: … sun.misc.Unsafe …`.
- C# (cartservice PM-01), severidad INFO: al apagarse `Application is shutting down...`; al arrancar `Error reading message.`, `System.IO.IOException: The client reset the request stream.` y `Service method 'Check' canceled.`.
- Eventos `Unhealthy` (`Readiness probe failed …` en el pod que se termina o en el nuevo; `Liveness probe failed: timeout: health rpc did not complete within 1s` una vez durante el arranque, sin reinicio). En historial no indicaron otra falla.

Un barrido `severity>=ERROR` sobre el objetivo los muestra como "errores del servicio". Cualquier ERROR del objetivo entre el `Killing` y unos segundos después del log de arranque del servidor se trata como ruido de ciclo de vida.

Ruido de base no relacionado, visto en varias ventanas: `UnacceptedCreditCard [Error]: Sorry, we cannot process visa_electron credit cards. Only VISA or MasterCard is accepted.` en paymentservice y el `failed to charge card … code = Code(400)` correspondiente en frontend (PM-01, PM-02, PM-05). Se distingue por `Code(400)` en lugar de `Unavailable … connection refused`.

## Servicios con poco tráfico
- Si el servicio solo se usa en una operación poco frecuente (payment, email y shipping en checkout), los llamadores escriben pocas líneas: 23 líneas de frontend en toda la ventana de PM-04, frente a cientos con cart, catálogo o moneda.
- Pocas líneas, o ninguna, **no** significan que el servicio esté sano. Antes de concluir, comprobar que hubo tráfico hacia esa operación en la ventana: `[PlaceOrder]` de checkoutservice y `request complete` de frontend en `POST /cart/checkout` (en PM-04, 18 `[PlaceOrder]` en un periodo de falla de 2 min 27 s, con 0 `payment went through`).
- Si no hubo tráfico, el impacto es SIN_DATOS. La causa sigue confirmada por el estado del Deployment.

## Pasos de verificación (SOLO LECTURA)
```sh
NS=boutique; SVC=<servicio>
kubectl -n $NS get deploy $SVC -o wide
kubectl -n $NS get deploy $SVC -o jsonpath='{.spec.replicas} {.status.readyReplicas} {.status.availableReplicas}{"\n"}'
kubectl -n $NS get pods -l app=$SVC -o wide
kubectl -n $NS get endpointslices -l kubernetes.io/service-name=$SVC
kubectl -n $NS describe deploy $SVC | sed -n '/Events:/,$p'
kubectl -n $NS get events --sort-by=.lastTimestamp --field-selector involvedObject.kind=Deployment,involvedObject.name=$SVC
kubectl -n $NS get hpa                # no debería haber HPA sobre el servicio
# Resolver el IP:puerto que aparece en el error de un llamador
kubectl -n $NS get svc -o wide        # CLUSTER-IP + PORT(S) -> <svc>
kubectl -n $NS get pods -o wide       # solo si el IP no es de un Service (IP de pod)
```
Eventos y logs históricos en Cloud Logging (ajustar la ventana):
```sh
gcloud logging read 'logName="projects/tider-ops/logs/events" AND jsonPayload.involvedObject.namespace="boutique" AND jsonPayload.reason="ScalingReplicaSet" AND timestamp>="<T0>" AND timestamp<="<T1>"' --project tider-ops --format=json
# Errores de llamadores: buscar el IP:puerto del Service, no el nombre (frontend escribe JSON, no textPayload)
gcloud logging read 'resource.type="k8s_container" AND resource.labels.namespace_name="boutique" AND severity>=WARNING AND "<CLUSTER_IP>:<puerto>" AND timestamp>="<T0>" AND timestamp<="<T1>"' --project tider-ops --limit 500
# Tráfico de checkout en la ventana (servicios de poco tráfico); INFO, sin filtro de severidad
gcloud logging read 'resource.type="k8s_container" AND resource.labels.namespace_name="boutique" AND labels."k8s-pod/app"="checkoutservice" AND "PlaceOrder" AND timestamp>="<T0>" AND timestamp<="<T1>"' --project tider-ops --limit 500
```
En la consulta de errores conviene filtrar también por `labels."k8s-pod/app"` de cada llamador, incluido frontend aunque no sea dependiente directo. La búsqueda de texto libre (`"…"`) es [INF]: validar que recupera tanto `textPayload` como `jsonPayload.message`.

## Acción de reparación sugerida
Pendiente de validación: Tider solo muestra esta acción cuando la firma está CONFIRMADA y el runbook fue validado con ChaosForge; mientras tanto se presenta como sugerencia no verificada. La firma se contrastó con las 5 corridas de historial `scale_zero` (PM-01 a PM-05, cartservice, productcatalogservice, currencyservice, paymentservice y adservice) y se cumplió en las 5. En ellas la reparación fue siempre el "Restaurar" automático de ChaosForge; el escalado manual de abajo no se ejerció.

**ACCIÓN HUMANA: Tider no ejecuta esto.**

- Si hay un experimento ChaosForge activo, **no** escales a mano. Usa "Restaurar" en el panel (`POST /api/restore`): el administrador conoce las réplicas originales y bloquea los conflictos.
- Fuera del laboratorio, confirma el número original de réplicas con `kubectl rollout history` o con la configuración versionada.

```sh
kubectl -n boutique scale deploy/<servicio> --replicas=<N_original>   # en el manifiesto base, N_original = 1 [conocimiento público]
```

## Cómo verificar que funcionó
- `readyReplicas == spec.replicas` y el EndpointSlice tiene direcciones listas.
- **Esperar la cola de errores.** Los llamadores siguen fallando un tiempo después de que el servicio vuelve: en historial, el último error llegó entre 39 y 79 s después del log de arranque del servidor y entre 47 y 89 s después del `ScalingReplicaSet … from 0 to 1` (PM-01 a PM-05). Es compatible con el backoff de reconexión gRPC de cada cliente [INF]. Los checkouts pueden ser los últimos en recuperarse (PM-02, PM-03).
- **Criterio de estabilidad:** pod Ready, EndpointSlice con direcciones y **al menos 2 minutos seguidos sin errores nuevos de los llamadores que nombren el IP:puerto del servicio**, contados desde el último error. Si aparecen errores dentro de esos 2 min, la cuenta vuelve a empezar. La duración es [INF], acorde con la cola máxima observada (89 s); la práctica de esperar y re-verificar sigue a ITBench C.5.2 [LIT].
- **No leer la cola como un incidente nuevo.** Errores con el mismo IP:puerto hasta unos 90 s después del escalado a 1 son la misma falla. Solo si siguen más de 2 min después de Ready, o cambian de destino o de patrón, se reevalúa.
- Para un servicio de poco tráfico, la recuperación se confirma con la primera operación exitosa (en PM-04, `payment went through` a las 18:42:14, 79 s después del escalado a 1), no solo por la ausencia de errores.
- Las sondas `/` y `/cart` vuelven a 200, cuando aplican. No cubren checkout ni anuncios (PM-04, PM-05).
- Que el síntoma se despeje **no** valida el diagnóstico; se juzga por separado [LIT ITBench p.31].

## Riesgos de la reparación
- **redis-cart:** el pod nuevo arranca con `emptyDir` vacío y se pierden los carritos.
- **Reconciliación:** escalar con un experimento ChaosForge abierto genera un `Conflict` y deja el experimento bloqueado.
- **Réplicas de más:** subir por encima del original altera la línea base de las próximas corridas.
- **Autopilot:** puede tardar en aprovisionar capacidad; un `FailedScheduling` transitorio no significa que la reparación fracasó.
- **HPA:** si existiera, sobrescribiría el escalado manual.

## Equivalente en ECS (breve)
- Firma: `desiredCount == 0`, o `runningCount == 0` con `desiredCount > 0`; target group sin targets healthy. El Cambio está en los eventos de servicio de ECS.
- Reparación humana: `aws ecs update-service --cluster <c> --service <s> --desired-count <N>`.
- Verificación: `runningCount == desiredCount` y targets healthy, estable tras la espera.
- Sin eventos de ECS exportados, el Cambio es SIN_DATOS.
