# Arquitectura configurada de Online Boutique y ChaosForge

Fuente: lectura de deployments del namespace boutique en GKE chaosforge-lab, proyecto tider-ops, región us-central1, el 25 de octubre de 2026. No se modificó ningún recurso.

El diagrama contiene los 12 componentes encontrados y sus dependencias explícitas en variables de entorno de direcciones. No es una medición de tráfico, salud, réplicas disponibles ni un inventario de pods. Las relaciones apuntan desde el llamador hacia el destino configurado. No incluye relaciones que no estén declaradas en esas variables.

## Dependencias verificadas en configuración

- cartservice → redis-cart: REDIS_ADDR.
- checkoutservice → productcatalogservice: PRODUCT_CATALOG_SERVICE_ADDR.
- checkoutservice → shippingservice: SHIPPING_SERVICE_ADDR.
- checkoutservice → paymentservice: PAYMENT_SERVICE_ADDR.
- checkoutservice → emailservice: EMAIL_SERVICE_ADDR.
- checkoutservice → currencyservice: CURRENCY_SERVICE_ADDR.
- checkoutservice → cartservice: CART_SERVICE_ADDR.
- frontend → productcatalogservice: PRODUCT_CATALOG_SERVICE_ADDR.
- frontend → currencyservice: CURRENCY_SERVICE_ADDR.
- frontend → cartservice: CART_SERVICE_ADDR.
- frontend → recommendationservice: RECOMMENDATION_SERVICE_ADDR.
- frontend → shippingservice: SHIPPING_SERVICE_ADDR.
- frontend → checkoutservice: CHECKOUT_SERVICE_ADDR.
- frontend → adservice: AD_SERVICE_ADDR.
- loadgenerator → frontend: FRONTEND_ADDR.
- recommendationservice → productcatalogservice: PRODUCT_CATALOG_SERVICE_ADDR.

## Referencia sin despliegue correspondiente

frontend configura SHOPPING_ASSISTANT_SERVICE_ADDR hacia shoppingassistantservice:80, pero ese nombre no apareció entre los deployments consultados. Se excluye del catálogo de componentes encontrados; no se afirma que esté activo.

## Capa del laboratorio

El código de ChaosForge define GKE Autopilot y el administrador en chaosforge-system, con acceso limitado a boutique. El script abrir-panel abre un túnel privado hacia chaosforge-admin. El administrador permite seleccionar fallas sobre carrito, pagos, catálogo de productos, envíos, monedas y recomendaciones. Estos controles no constituyen dependencias de negocio y no se incluyen como servicios de la tienda.

Tider consulta Cloud Logging en modo observación. Los documentos anteriores describían una parte de la arquitectura y un alcance de consulta antiguo; este diagrama amplía las dependencias configuradas. Los alias de operaciones deben revisarse antes de confirmar el catálogo; no se deducen causas de fallas por el mero hecho de existir una arista.
