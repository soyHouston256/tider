"""Servicios y dependencias del laboratorio Online Boutique.

Obsoleto para el pipeline v2: `EDGES` y `related_services()` quedan solo para el modo v1. En v2 las
relaciones salen del Cartógrafo (`console/topology.py`), con nodos de la plataforma y aristas
configuradas (Lake) y observadas; `TopologiaLake.desde_catalogo()` usa `EDGES` solo como respaldo sin Lake.
"""

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


# Dependencias configuradas (from = quien llama, to = destino): las 16 aristas de
# Context Lake/V3-piloto-online-boutique/topologia.yaml (revisión 1, 2026-11-09; corrige D2).
# redis-cart solo se alcanza vía cartservice; loadgenerator→frontend es tráfico sintético.
EDGES: tuple[tuple[str, str], ...] = (
    ("frontend", "productcatalogservice"),
    ("frontend", "currencyservice"),
    ("frontend", "cartservice"),
    ("frontend", "recommendationservice"),
    ("frontend", "shippingservice"),
    ("frontend", "checkoutservice"),
    ("frontend", "adservice"),
    ("cartservice", "redis-cart"),
    ("checkoutservice", "productcatalogservice"),
    ("checkoutservice", "shippingservice"),
    ("checkoutservice", "paymentservice"),
    ("checkoutservice", "emailservice"),
    ("checkoutservice", "currencyservice"),
    ("checkoutservice", "cartservice"),
    ("recommendationservice", "productcatalogservice"),
    ("loadgenerator", "frontend"),
)


def related_services(service: str) -> list[str]:
    """Alcance de la consulta de logs: el servicio, los que llama y los que lo llaman (1 salto),
    igual que ContextLake.query_scope con un catálogo confirmado."""
    callees = [dst for src, dst in EDGES if src == service]
    callers = [src for src, dst in EDGES if dst == service]
    return list(dict.fromkeys([service, *callees, *callers]))
