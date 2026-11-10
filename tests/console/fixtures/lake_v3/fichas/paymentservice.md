---
servicio: paymentservice
tipo_doc: ficha
plataforma: kubernetes
app: online-boutique
revision: 2
cambios: "rev2: el síntoma aparece en frontend, no en checkoutservice; formato real del error (IP del Service:50051); puerto 50051 compartido con shippingservice; tráfico bajo; ruido de arranque y rechazo visa_electron; cola de recuperación. Origen: PM-04 (Brechas del Lake) y PM-01, PM-02, PM-05 (ruido de base)."
fecha: 2026-11-09
fuente: Context Lake V2 06-alcance-arquitectura-gke.md; chaosforge/admin/controller.py; recomend/_auditoria_consolidada.md (riesgo 2, decisión 14); microservices-demo v0.10.x [conocimiento público]; postmortems/PM-04-paymentservice-scale_zero.md (historial, escrito contra rev 1)
---
## Qué hace
Servicio gRPC escrito en Node.js. Simula el cobro con tarjeta de crédito:
- valida el número, el tipo y el vencimiento de la tarjeta;
- devuelve un identificador de transacción.

No contacta a ningún procesador real. Contenedor `server`, puerto 50051 (`PORT=50051`) [conocimiento público]. **shippingservice usa el mismo puerto 50051** (otro Service, otro ClusterIP).

## Depende de (llamadas salientes, con variable de entorno y puerto)
Ninguna dependencia de aplicación.

## Quién depende de él (llamadas entrantes)
- checkoutservice — `PAYMENT_SERVICE_ADDR` = paymentservice:50051

Es su único llamador. frontend **no** llama a paymentservice directamente, pero es quien **registra** el error (ver Síntomas).

## Operaciones de usuario afectadas si falla
- **Solo el checkout** (confirmar el pedido): HTTP 500 en `POST /cart/checkout`.

El resto de la tienda sigue respondiendo, así que las sondas `/` y `/cart` de ChaosForge **no detectan** esta falla (auditoría, riesgo 2; confirmado en PM-04).

**Tráfico muy bajo:** solo se usa al pagar. En PM-04 hubo 18 `[PlaceOrder]` en 2 min 27 s de falla, y el primer síntoma llegó 18,9 s después del escalado [observado en historial]. Pocas líneas de error no significan que esté sano.

## Síntomas típicos cuando falla
**En él mismo:**
- Sin instancias, no hay logs.
- En sano registra `PaymentService#Charge invoked with request …` y `Transaction processed: visa ending NNNN     Amount: …` por cada cobro [observado en historial].
  Si hay checkouts y desaparece, es un corroborante.
- **Ruido de arranque, no síntoma:** el pod nuevo registra con severidad **ERROR** `(node:1) DeprecationWarning: Calling start() is no longer necessary. It can be safely omitted.` y `(Use \`node --trace-deprecation ...\` to show where the warning was created)`, justo después de `PaymentService gRPC server started on port 50051`. También hay eventos `Readiness probe failed …` durante el arranque (PM-04).

**En quien lo llama:**
- **frontend** (no checkoutservice) registra el error, con el fallo de checkoutservice anidado y el **ClusterIP** del Service, no el nombre [observado en historial, PM-04]:
  `request error | error=failed to complete the order: rpc error: code = Internal desc = failed to charge card: could not charge the card: rpc error: code = Unavailable desc = connection error: desc = "transport: Error while dialing: dial tcp 10.49.5.115:50051: connect: connection refused" | http.req.method=POST | http.req.path=/cart/checkout`
- **checkoutservice** no escribe líneas ≥ WARNING. Solo se ve su `[PlaceOrder] …` (INFO) sin el `payment went through (transaction_id: …)` que lo sigue en sano.

**Patrón característico:** errores **solo** en `POST /cart/checkout`, en frontend, con `failed to charge card` y `connection refused` hacia `<IP>:50051`; las demás rutas responden 200. La raíz candidata es paymentservice, no checkoutservice. El puerto 50051 no basta (shippingservice lo comparte): atribuir por el texto o resolviendo el IP con `kubectl -n boutique get svc -o wide` (RB-01).

**No confundir con una tarjeta rechazada,** que es un error de negocio con el servicio sano:
- `Credit card info is invalid` [conocimiento público].
- `UnacceptedCreditCard [Error]: Sorry, we cannot process visa_electron credit cards. Only VISA or MasterCard is accepted.` (ERROR en paymentservice) y `failed to charge card … code = Code(400)` en frontend: ruido de base del generador de carga (PM-01, PM-02, PM-05). paymentservice **sí** escribe y el código es `Code(400)`, no `Unavailable`.

## Señales a revisar
- **Servicio:** `instancias_deseadas` y `instancias_listas`; `version_config`.
- **Instancia:** estado de los pods; `motivo_fin` y `codigo_salida`.
- **Cambio:** ScalingReplicaSet o una nueva generación de `paymentservice` antes del primer error de checkout.
- **Evento:** `Unhealthy`, `Killing`, `BackOff`.
- **Señal:**
  - Logs ≥ WARNING de **frontend** en `POST /cart/checkout` con `failed to charge card` y `:50051`. No buscarlo en checkoutservice.
  - `[PlaceOrder]` de checkoutservice contra `payment went through`: muchos de lo primero y ninguno de lo segundo son cobros fallidos. Si no hubo compras, el impacto queda SIN_DATOS, no "sano".

**Recuperación:** los checkouts siguen fallando tras volver a 1 réplica. En PM-04, el último error fue 54 s después de `PaymentService gRPC server started` y el primer cobro exitoso, 79 s después del escalado a 1 [observado en historial]. Esa cola es la misma falla. Dar por recuperado con el primer `payment went through` y 2 min sin errores nuevos (RB-01).

## Modos de falla aplicables del catálogo v1
- [RB-01 servicio sin instancias](../runbooks/RB-01-servicio-sin-instancias.md)
- [RB-03 dependencia lenta](../runbooks/RB-03-dependencia-lenta.md), donde paymentservice es la dependencia
- [RB-04 saturación de CPU](../runbooks/RB-04-saturacion-cpu.md)
- [RB-02 configuración incorrecta](../runbooks/RB-02-configuracion-incorrecta.md)
- [RB-05 se cae al arrancar](../runbooks/RB-05-se-cae-al-arrancar.md) (declarada)
- [RB-06 sin memoria](../runbooks/RB-06-sin-memoria.md) (declarada)

En el laboratorio actual, ChaosForge solo inyecta `scale_zero` sobre este servicio.
