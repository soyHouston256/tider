import base64
import zlib
from urllib.parse import quote

import pytest
from chromadb.api.types import EmbeddingFunction
from fastapi.testclient import TestClient

from tider.console.api import create_app
from tider.console.context_lake import ContextLake, extract
from tider.console.settings import Settings


class TinyEmbedding(EmbeddingFunction):
    def __init__(self):
        pass

    def __call__(self, input):
        return [[float("cart" in text.lower()), float("payment" in text.lower()), 0.1] for text in input]

    @staticmethod
    def build_from_config(config):
        return TinyEmbedding()

    def get_config(self):
        return {}

    @staticmethod
    def name():
        return "test-local"


MODEL = '<mxGraphModel><root><mxCell id="a" value="frontend" vertex="1"/><mxCell id="b" value="cartservice" vertex="1"/><mxCell id="c" source="a" target="b" edge="1"/></root></mxGraphModel>'


def test_drawio_plain_and_compressed_have_same_source():
    compressor = zlib.compressobj(wbits=-15)
    encoded = base64.b64encode(compressor.compress(quote(MODEL).encode()) + compressor.flush()).decode()
    plain = extract("arch.drawio", f'<mxfile><diagram name="Architecture">{MODEL}</diagram></mxfile>')
    compressed = extract("arch.drawio", f'<mxfile><diagram name="Architecture">{encoded}</diagram></mxfile>')
    assert plain == compressed
    assert "frontend → cartservice" in plain[0][1]


def test_xml_entities_are_rejected():
    with pytest.raises(ValueError):
        extract("attack.drawio", '<!DOCTYPE x [<!ENTITY a SYSTEM "file:///etc/passwd">]><mxfile>&a;</mxfile>')


def test_session_isolation_retrieval_dedup_and_delete():
    lake = ContextLake(TinyEmbedding())
    first = lake.add("cart.md", "# Cart\nInvestigate cart connection errors.")
    lake.add("payment.md", "# Payment\nInvestigate payment authorization.")
    assert lake.add("cart.md", "# Cart\nInvestigate cart connection errors.") == first
    match = lake.search("cart connection")[0]
    assert match["title"] == "cart.md"
    assert match["chunk"] == 1
    assert "Investigate cart" in match["text"]
    assert ContextLake(TinyEmbedding()).inventory()["documents"] == []
    lake.delete(first["id"])
    assert all(m["title"] != "cart.md" for m in lake.search("cart connection"))


def test_upload_api_and_origin_guard(monkeypatch):
    import tider.console.api as api

    monkeypatch.setattr(api, "ContextLake", lambda **kw: ContextLake(TinyEmbedding(), **kw))
    with TestClient(create_app(Settings(evidence_mode="mock", llm_provider="none"))) as client:
        assert (
            client.post(
                "/v1/context/documents",
                json={"name": "a.md", "content": "cart"},
                headers={"Origin": "https://elsewhere.example"},
            ).status_code
            == 403
        )
        assert (
            client.post("/v1/context/documents", json={"name": "a.pdf", "content": "cart"}).status_code == 400
        )
        assert client.post("/v1/context/documents", json={"name": "a.md", "content": " "}).status_code == 400
        assert (
            client.post("/v1/context/documents", json={"name": "a.md", "content": "é" * 600_000}).status_code
            == 400
        )
        assert (
            client.post(
                "/v1/context/documents", json={"name": "a.md", "content": "cart troubleshooting"}
            ).status_code
            == 200
        )
        assert client.get("/v1/context").json()["chunks"] == 1
        assert (
            client.post("/v1/context/search", json={"query": "cart"}).json()["matches"][0]["title"] == "a.md"
        )
        assert client.delete("/v1/context/documents/missing").status_code == 404


def test_front_matter_does_not_become_a_search_passage():
    lake = ContextLake(TinyEmbedding())
    doc = lake.add(
        "cart.md", "---\ntype: architecture\nservice: cartservice\n---\n# Cart\ncart troubleshooting"
    )
    assert doc["chunks"] == 1
    assert lake.search("cart")[0]["text"].startswith("# Cart")
    assert "type: architecture" not in lake.search("cart")[0]["text"]
    with pytest.raises(ValueError, match="metadatos"):
        lake.add("metadata.md", "---\ntype: architecture\n---\n")
    assert len(lake.inventory()["documents"]) == 1


def test_retrieval_abstains_for_weak_matches_but_keeps_explicit_terms():
    from tider.console.context_lake import rank_passages

    row = {"text": "Región: us-central1. Laboratorio GKE. frontend llama a cartservice.",
           "doc_id": "doc", "chunk": 1, "distance": 0.72}
    assert rank_passages("¿En qué región está el laboratorio?", [row], 4)
    assert not rank_passages("¿Cómo rotar certificados en GKE?", [row], 4)
    assert not rank_passages("Dame la lista de pods de mi infra", [row], 4)
    assert not rank_passages("¿Qué?", [row], 4)
    lake = ContextLake(TinyEmbedding())
    lake.add("cart.md", "# Cart\ncart troubleshooting")
    assert lake.search("payment") == []


def test_technical_identifier_beats_unrelated_heading_and_old_manual_cannot_supply_live_value():
    from tider.console.context_lake import rank_passages

    rows = [{"doc_id": "a", "chunk": 1, "text": "# CPU", "distance": .1},
            {"doc_id": "b", "chunk": 1, "text": "Configura el destino mediante PAYMENT_SERVICE_ADDR.", "distance": .72}]
    assert [r["doc_id"] for r in rank_passages("Destino de PAYMENT_SERVICE_ADDR", rows, 4)] == ["b"]
    assert rank_passages("¿Cuál es el destino de PAYMENT_SERVICE_ADDR ahora?", rows, 4) == []
    assert rank_passages("¿Cómo consulto PAYMENT_SERVICE_ADDR ahora?", rows, 4)
