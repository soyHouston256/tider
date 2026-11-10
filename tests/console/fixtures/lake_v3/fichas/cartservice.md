---
servicio: cartservice
tipo_doc: ficha
plataforma: kubernetes
app: online-boutique
revision: 1
fecha: 2026-11-09
fuente: Context Lake V2 06-alcance-arquitectura-gke.md; chaosforge/admin/faults.py, observations.py, k8s/proxy.yaml, EXPERIMENTS.md; microservices-demo v0.10.4 [conocimiento público]
---
## Qué hace
Servicio gRPC escrito en C# (.NET). Guarda y recupera el carrito de cada sesión: agregar ítem, obtener carrito y vaciar carrito. Los carritos no viven en el servicio sino en Redis. Contenedor `server`, puerto 7070. La imagen validada por ChaosForge es `us-central1-docker.pkg.dev/google-samples/microservices-demo/cartservice:v0.10.4` (faults.py).

## Depende de (llamadas salientes, con variable de entorno y puerto)
- redis-cart — `REDIS_ADDR` = `redis-cart:6379` (protocolo Redis sobre TCP).
  - En el laboratorio, cuando se prepara el mecanismo de latencia, `REDIS_ADDR` = `chaosforge-proxy:6379` y el proxy reenvía a `redis-cart:6379` (faults.py `DIRECT`/`PROXY`).
  - Leer siempre el valor efectivo de `REDIS_ADDR` en el Deployment.

## Quién depende de él (llamadas entrantes)
- frontend — `CART_SERVICE_ADDR` = cartservice:7070
- checkoutservice — `CART_SERVICE_ADDR` = cartservice:7070

## Operaciones de usuario afectadas si falla
- **Ver carrito (`/cart`) y agregar al carrito.**
- **Checkout**, porque checkoutservice lee y vacía el carrito.
- **Inicio y página de producto**: frontend consulta el carrito para mostrar el contador [conocimiento público]. Por eso un fallo de carrito puede romper páginas que no parecen relacionadas con él.

## Síntomas típicos cuando falla
**En él mismo:**
- Si tiene 0 instancias, no escribe logs.
- Si Redis no responde o la dirección es incorrecta, el servicio sigue vivo pero registra errores de almacenamiento: `Can't access cart storage`, `RedisConnectionException` o `No connection is available to service this operation` [esperado, validar con ChaosForge].
- Al arrancar registra la dirección de Redis a la que se conecta [conocimiento público], lo que permite contrastarla con `REDIS_ADDR`.

**En quien lo llama:**
- frontend registra `could not retrieve cart` o `failed to add to cart` con `rpc error: code = Unavailable` y responde HTTP 500 [esperado, validar con ChaosForge].
- checkoutservice falla al preparar el pedido.
- Si cartservice no tiene endpoints, el error de los llamadores es de conexión a `cartservice:7070` y **no** aparecen errores de Redis en cartservice. Esta es la distinción clave frente a una falla de redis-cart.

## Señales a revisar
- **Servicio:** `instancias_deseadas` y `instancias_listas`; `version_config`, incluido el valor de `REDIS_ADDR` y los recursos de CPU del contenedor `server`.
- **Instancia:** estado de los pods; `limites` de CPU y memoria; `motivo_fin` y `codigo_salida`.
- **Cambio:** ScalingReplicaSet; nueva generación con `REDIS_ADDR` o recursos modificados **antes** del primer error.
- **Evento:** `Unhealthy`, `Killing`, `BackOff`, `OOMKilling`.
- **Señal:**
  - Logs de error de cartservice que mencionen Redis.
  - Logs de frontend y checkoutservice con `cart`.
  - Métricas `latencia_p95` de `/cart` y de la dependencia Redis. El observador de ChaosForge mide `Redis PING` y `GET /cart` (observations.py).
  - `cpu_throttling` del contenedor `server`.

## Modos de falla aplicables del catálogo v1
- [RB-01 servicio sin instancias](../runbooks/RB-01-servicio-sin-instancias.md)
- [RB-02 configuración incorrecta](../runbooks/RB-02-configuracion-incorrecta.md) (`REDIS_ADDR` con puerto erróneo; inyector `wrong_port`)
- [RB-03 dependencia lenta](../runbooks/RB-03-dependencia-lenta.md) (Redis lento vía proxy; inyector `latency`)
- [RB-04 saturación de CPU](../runbooks/RB-04-saturacion-cpu.md) (inyector `cpu_limit`)
- [RB-05 se cae al arrancar](../runbooks/RB-05-se-cae-al-arrancar.md) (declarada)
- [RB-06 sin memoria](../runbooks/RB-06-sin-memoria.md) (declarada)
