import pytest
from fastapi.testclient import TestClient

from tider.console.api import create_app
from tider.console.catalog_review import CatalogReview
from tider.console.context_lake import ContextLake
from tider.console.models import AnalyzeRequest
from tider.console.providers import EvidenceProvider
from tider.console.settings import Settings

from .test_context_lake import TinyEmbedding

DIAGRAM = """<mxGraphModel><root>
<mxCell id="a" value="frontend" vertex="1"/>
<mxCell id="b" value="cartservice" vertex="1"/>
<mxCell id="c" value="redis-cart" vertex="1"/>
<mxCell id="d" value="Solicitud de análisis" vertex="1"/>
<mxCell id="e" value="Filtro Cloud Logging" vertex="1"/>
<mxCell source="a" target="b" value="llama a" edge="1"/>
<mxCell source="b" target="c" value="utiliza" edge="1"/>
<mxCell source="d" target="e" edge="1"/>
</root></mxGraphModel>"""


def full_review(lake):
    data = lake.catalog()
    return CatalogReview(
        revision=data["revision"],
        services=data["proposal"]["services"],
        relations=data["proposal"]["relations"],
    )


def test_proposal_has_provenance_but_is_not_active_until_review():
    lake = ContextLake(TinyEmbedding())
    doc = lake.add("architecture.drawio", DIAGRAM)
    proposal = lake.catalog()["proposal"]
    assert {s["name"] for s in proposal["services"]} == {"frontend", "cartservice", "redis-cart"}
    assert len(proposal["relations"]) == 2
    assert all(s["sources"][0]["doc_id"] == doc["id"] for s in proposal["services"])
    with pytest.raises(ValueError, match="Confirma"):
        lake.query_scope("frontend")
    lake.confirm_catalog(full_review(lake))
    assert lake.query_scope("cartservice") == ["cartservice", "frontend", "redis-cart"]
    assert lake.query_scope("frontend") == ["cartservice", "frontend"]  # direct, not transitive
    with pytest.raises(ValueError, match="no pertenece"):
        lake.query_scope("invented")


def test_review_supports_rename_reject_and_stale_version_detection():
    lake = ContextLake(TinyEmbedding())
    doc = lake.add("architecture.drawio", DIAGRAM)
    review = full_review(lake)
    frontend = next(s for s in review.services if s.name == "frontend")
    frontend.name = "storefront"
    review.services = [s for s in review.services if s.name != "redis-cart"]
    ids = {s.id for s in review.services}
    review.relations = [r for r in review.relations if r.source in ids and r.target in ids]
    active = lake.confirm_catalog(review)["confirmed"]
    assert lake.query_scope("storefront") == ["cartservice", "storefront"]
    assert next(s for s in active["services"] if s["name"] == "storefront")["original_name"] == "frontend"
    with pytest.raises(ValueError, match="cambió"):
        lake.confirm_catalog(review)
    lake.add("extra.md", "# Documentation\ncart troubleshooting")
    assert lake.catalog()["status"] == "pending"
    with pytest.raises(ValueError, match="Confirma"):
        lake.query_scope("storefront")
    lake.delete(doc["id"])
    assert lake.catalog()["proposal"]["services"] == []


def test_markdown_mermaid_and_metadata_merge_sources():
    lake = ContextLake(TinyEmbedding())
    lake.add("architecture.drawio", DIAGRAM)
    lake.add(
        "runbook.md",
        "---\nservice: cartservice\n---\n# Cart\n```mermaid\nflowchart LR\nF[frontend] --> C[cartservice]\n```",
    )
    proposal = lake.catalog()["proposal"]
    cart = next(s for s in proposal["services"] if s["name"] == "cartservice")
    assert {s["file"] for s in cart["sources"]} == {"architecture.drawio", "runbook.md"}
    assert len(proposal["relations"]) == 2
    assert lake.catalog()["status"] == "pending"


def test_api_catalog_guards_and_provider_scope(monkeypatch):
    import tider.console.api as api
    import tider.console.providers as providers

    monkeypatch.setattr(api, "ContextLake", lambda: ContextLake(TinyEmbedding()))
    app = create_app(Settings(evidence_mode="gcp", llm_provider="none"))
    with TestClient(app) as client:
        client.post(
            "/v1/context/documents", json={"name": "architecture.drawio", "content": DIAGRAM}
        ).raise_for_status()
        assert client.get("/v1/lab/config").json()["services"] == []
        lake = app.state.context_lake
        review = full_review(lake).model_dump()
        assert (
            client.post(
                "/v1/context/catalog/confirm", json=review, headers={"Origin": "https://evil.example"}
            ).status_code
            == 403
        )
        assert client.post("/v1/context/catalog/confirm", json=review).status_code == 200
        assert set(client.get("/v1/lab/config").json()["services"]) == {
            "frontend",
            "cartservice",
            "redis-cart",
        }
        captured = {}

        def read(service, start, end, settings, services=None):
            captured["scope"] = services
            return []

        monkeypatch.setattr(providers, "gcp_signals", read)
        request = AnalyzeRequest(
            incident_id="test",
            service="cartservice",
            mode="gcp",
            start="2026-10-24T19:47:00-05:00",
            end="2026-10-24T19:49:00-05:00",
        )
        EvidenceProvider(app.state.analysis_service.settings, lake).load(request)
        assert captured["scope"] == ["cartservice", "frontend", "redis-cart"]
        assert client.post("/v1/context/catalog/confirm", json=review).status_code == 409
