"""Context Lake v3 (Fase 4): carga, vía por clave, postmortems como antecedente, manifiesto y A11.

Usa una copia reducida del Lake en fixtures/lake_v3 (2 fichas, 2 runbooks, 1 postmortem, PLANTILLA,
PENDIENTES y datos/ crudos) y un embedding de prueba para no descargar MiniLM.
"""

import shutil
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tider.console.api import create_app
from tider.console.context_lake import ContextLake
from tider.console.lake_loader import lake_files, load_v3
from tider.console.settings import Settings

from .test_context_lake import TinyEmbedding

FIXTURE = Path(__file__).parent / "fixtures" / "lake_v3"


@pytest.fixture
def lake():
    return ContextLake(TinyEmbedding(), max_documents=60, max_chunks=600)


def test_load_v3_counts_one_fragment_per_document(lake):
    manifest = load_v3(FIXTURE, lake)
    by_type = {}
    for doc in lake.inventory()["documents"]:
        assert doc["chunks"] == 1  # fichas, runbooks y postmortems: un fragmento (P6)
        by_type[doc["tipo_doc"]] = by_type.get(doc["tipo_doc"], 0) + 1
    assert by_type == {"ficha": 2, "runbook": 2, "postmortem": 1}
    assert lake.collection.count() == 5
    assert len(manifest["documentos"]) == 5


def test_get_returns_exact_document_by_key(lake):
    load_v3(FIXTURE, lake)
    ficha = lake.get("ficha", "cartservice")
    assert ficha["name"] == "cartservice.md"
    assert ficha["metadata"]["servicio"] == "cartservice"
    assert ficha["metadata"]["mecanismo"] is None  # las fichas no declaran mecanismo
    assert ficha["text"].startswith("## Qué hace") and "tipo_doc:" not in ficha["text"]
    by_id = lake.get("runbook", "RB-01")
    assert by_id["name"] == "RB-01-servicio-sin-instancias.md"
    assert lake.get("runbook", "servicio-sin-instancias") == by_id
    assert by_id["text"] == (FIXTURE / "runbooks" / by_id["name"]).read_text().split("\n---\n", 1)[1].strip()
    assert lake.get("ficha", "frontend") is None
    assert lake.get("postmortem", "PM-01") is None  # los postmortems solo por búsqueda


def test_postmortems_loaded_as_antecedent_and_filterable(lake):
    load_v3(FIXTURE, lake)
    rows = lake.search("cartservice scale_zero connection refused", k=4, where={"tipo_doc": "postmortem"})
    assert [r["title"] for r in rows] == ["PM-01-cartservice-scale_zero.md"]
    assert rows[0]["uso"] == "antecedente" and rows[0]["evidencia"] is False
    assert rows[0]["conjunto"] == "historial" and rows[0]["doc_type"] == "postmortem"
    assert all(r["doc_type"] == "ficha" for r in lake.search("cartservice redis", where={"tipo_doc": "ficha"}))
    assert all(d["uso"] != "antecedente" for d in lake.snapshot_documents() if d["doc_type"] != "postmortem")


def test_skips_template_pending_and_raw_exports():
    names = {path.name for path, _ in lake_files(FIXTURE)}
    assert (FIXTURE / "postmortems" / "datos" / "PM-01" / "no-indexar.md").exists()
    assert names.isdisjoint({"PLANTILLA.md", "PENDIENTES.md", "README.md", "no-indexar.md", "observaciones.json"})
    assert names == {"cartservice.md", "paymentservice.md", "RB-01-servicio-sin-instancias.md",
                     "RB-05-se-cae-al-arrancar.md", "PM-01-cartservice-scale_zero.md"}


def test_topology_loaded_as_graph_not_indexed(lake):
    load_v3(FIXTURE, lake)
    topology = lake.get_topology()
    assert {s["nombre"] for s in topology["servicios"]} >= {"cartservice", "frontend", "redis-cart"}
    assert all(m["title"] != "topologia.yaml" for m in lake.snapshot_documents())


def test_manifest_has_revision_hashes_and_changes_with_a_document(lake, tmp_path):
    manifest = load_v3(FIXTURE, lake)
    assert manifest["revision"] == 2  # README rev 2
    assert manifest["modelo"] == "test-local" and len(manifest["hash"]) == 64
    assert len(manifest["topologia"]) == 64
    payment = next(d for d in manifest["documentos"].values() if d["nombre"] == "paymentservice.md")
    assert payment["revision"] == 2 and payment["tipo_doc"] == "ficha" and len(payment["sha256"]) == 64
    assert load_v3(FIXTURE, ContextLake(TinyEmbedding()))["hash"] == manifest["hash"]  # estable
    copy = tmp_path / "lake"
    shutil.copytree(FIXTURE, copy)
    ficha = copy / "fichas" / "cartservice.md"
    ficha.write_text(ficha.read_text() + "\nLínea añadida.\n")
    assert load_v3(copy, ContextLake(TinyEmbedding()))["hash"] != manifest["hash"]


def test_malformed_package_fails_loudly(tmp_path, lake):
    with pytest.raises(ValueError, match="topologia.yaml"):
        load_v3(tmp_path, lake)
    shutil.copytree(FIXTURE, tmp_path / "lake")
    (tmp_path / "lake" / "fichas" / "intrusa.md").write_text("---\ntipo_doc: runbook\n---\n# X\ntexto")
    with pytest.raises(ValueError, match="se esperaba 'ficha'"):
        load_v3(tmp_path / "lake", lake)


def test_duplicate_key_is_rejected_and_delete_frees_it(lake):
    first = lake.add("a.md", "---\ntipo_doc: ficha\nservicio: cartservice\n---\n# A\ncart")
    with pytest.raises(ValueError, match="clave cartservice"):
        lake.add("b.md", "---\ntipo_doc: ficha\nservicio: cartservice\n---\n# B\ncart")
    lake.delete(first["id"])
    assert lake.get("ficha", "cartservice") is None
    assert lake.add("b.md", "---\ntipo_doc: ficha\nservicio: cartservice\n---\n# B\ncart")["chunks"] == 1


def test_limits_come_from_settings():
    lake = ContextLake(TinyEmbedding(), max_documents=1, max_chunks=10)
    lake.add("a.md", "# A\ncart")
    with pytest.raises(ValueError, match="1 documentos o 10 fragmentos"):
        lake.add("b.md", "# B\npayment")
    assert Settings().lake_max_documents == 60 and Settings().lake_max_chunks == 600


def test_a11_console_loads_lake_in_process_and_service_sees_it(monkeypatch):
    import tider.console.api as api

    monkeypatch.setattr(api, "ContextLake", lambda **kw: ContextLake(TinyEmbedding(), **kw))
    app = create_app(Settings(evidence_mode="mock", llm_provider="none", lake_v3_path=str(FIXTURE)))
    lake = app.state.context_lake
    service = app.state.analysis_service
    assert service.engine.context_lake is lake and service.provider.context_lake is lake
    assert service.engine.context_lake.get("runbook", "RB-01") is not None
    assert app.state.lake_manifest["hash"] == lake.manifest()["hash"]
    with TestClient(app) as client:
        assert len(client.get("/v1/context").json()["documents"]) == 5
        assert client.get("/v1/context/manifest").json()["revision"] == 2


def test_console_without_lake_path_keeps_v1_empty_lake(monkeypatch):
    import tider.console.api as api

    monkeypatch.setattr(api, "ContextLake", lambda **kw: ContextLake(TinyEmbedding(), **kw))
    app = create_app(Settings(evidence_mode="mock", llm_provider="none"))
    assert app.state.lake_manifest is None
    assert app.state.context_lake.inventory()["documents"] == []
