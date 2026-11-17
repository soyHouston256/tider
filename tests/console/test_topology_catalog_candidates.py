from tider.console.catalog_review import topology_candidates
from tider.console.context_lake import ContextLake

TOPOLOGY = {
    "servicios": [{"nombre": "frontend"}, {"nombre": "cartservice"}, {"nombre": "redis-cart"}],
    "aristas": [
        {"from": "frontend", "to": "cartservice", "variable": "CART_SERVICE_ADDR", "valor": "cartservice:7070"},
        {"from": "cartservice", "to": "redis-cart", "variable": "REDIS_ADDR", "valor": "redis-cart:6379"},
        {"from": "frontend", "to": "No Valido", "variable": "X"},
    ],
}


def test_topology_candidates_extracts_services_and_configured_edges():
    result = topology_candidates(TOPOLOGY, "abc")
    assert sorted(s["name"] for s in result["services"]) == ["cartservice", "frontend", "redis-cart"]
    assert [e["label"] for e in result["relations"]] == ["CART_SERVICE_ADDR", "REDIS_ADDR"]
    assert result["relations"][0]["sources"][0]["file"] == "topologia.yaml"


def test_set_topology_feeds_catalog_proposal():
    lake = ContextLake(max_documents=5, max_chunks=50)
    lake.set_topology(TOPOLOGY, "abc")
    proposal = lake.catalog()["proposal"]
    assert len(proposal["services"]) == 3
    assert len(proposal["relations"]) == 2
