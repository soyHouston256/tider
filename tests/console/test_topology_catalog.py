"""related_services() frente a la topología configurada de Online Boutique (discrepancia D2)."""

from pathlib import Path

import pytest

from tider.console.providers.catalog import EDGES, SERVICES, related_services

# Origen: project/code/Context Lake/V3-piloto-online-boutique/topologia.yaml (revisión 1,
# 2026-11-09). Copia literal de sus 16 `aristas` para que la prueba no dependa de una
# carpeta fuera del repositorio; si el archivo está disponible, también se compara con él.
TOPOLOGY_EDGES = {
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
}
TOPOLOGY_FILE = (
    Path(__file__).resolve().parents[3] / "Context Lake" / "V3-piloto-online-boutique" / "topologia.yaml"
)


def test_catalog_has_the_16_configured_edges():
    assert len(EDGES) == len(set(EDGES)) == 16
    assert set(EDGES) == TOPOLOGY_EDGES
    assert {name for edge in EDGES for name in edge} <= set(SERVICES)


def test_catalog_matches_topology_yaml_when_available():
    yaml = pytest.importorskip("yaml")
    if not TOPOLOGY_FILE.is_file():
        pytest.skip(f"topologia.yaml no disponible en {TOPOLOGY_FILE}")
    data = yaml.safe_load(TOPOLOGY_FILE.read_text(encoding="utf-8"))
    assert {(e["from"], e["to"]) for e in data["aristas"]} == set(EDGES)


def test_related_services_uses_direct_neighbours_in_both_directions():
    assert "redis-cart" not in related_services("frontend")
    assert "redis-cart" not in related_services("checkoutservice")
    assert set(related_services("cartservice")) == {"cartservice", "redis-cart", "frontend", "checkoutservice"}
    assert set(related_services("redis-cart")) == {"redis-cart", "cartservice"}
    assert set(related_services("productcatalogservice")) == {
        "productcatalogservice", "frontend", "checkoutservice", "recommendationservice",
    }
    assert set(related_services("checkoutservice")) == {
        "checkoutservice", "productcatalogservice", "shippingservice", "paymentservice",
        "emailservice", "currencyservice", "cartservice", "frontend",
    }
    assert related_services("cartservice")[0] == "cartservice"
    assert related_services("desconocido") == ["desconocido"]
