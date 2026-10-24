"""Servicios y dependencias del laboratorio Online Boutique."""

SERVICES = [
    "frontend",
    "cartservice",
    "redis-cart",
    "checkoutservice",
    "paymentservice",
    "productcatalogservice",
    "currencyservice",
    "shippingservice",
    "emailservice",
    "recommendationservice",
    "adservice",
    "loadgenerator",
]


def related_services(service: str) -> list[str]:
    dependencies = {
        "frontend": ["cartservice", "redis-cart", "checkoutservice"],
        "cartservice": ["redis-cart"],
        "checkoutservice": ["cartservice", "redis-cart", "paymentservice"],
    }
    return [service, *dependencies.get(service, [])]
