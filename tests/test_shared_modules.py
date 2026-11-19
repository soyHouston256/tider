"""Módulos del núcleo que usa la consola: ingesta Markdown/Mermaid (lake) y registro de herramientas."""

from tider.lake.ingest import parse_mermaid, split_markdown
from tider.tools.base import Tool, ToolRegistry


def test_mermaid_edges_use_labels():
    edges = parse_mermaid("graph LR\n FE[frontend] --> CART[cart]\n CART --> VK[valkey-cart]")
    assert {(e.src, e.dst) for e in edges} == {("frontend", "cart"), ("cart", "valkey-cart")}


def test_split_markdown_keeps_headings_and_cuts_long_lines():
    chunks = split_markdown("# A\ntexto\n## B\notro")
    assert len(chunks) == 2 and chunks[1].startswith("## B")
    assert all(len(c) <= 100 for c in split_markdown("x" * 250, max_chars=100))


def test_tool_failures_and_empty_results_are_not_evidence():
    def boom(**kw):
        raise ConnectionError("connection refused")

    reg = ToolRegistry(
        [
            Tool("prom", "", "metric", boom),
            Tool("vacia", "", "metric", lambda: "[]"),
            Tool("datos", "", "deploy", lambda: {"replicas": 2}),
        ]
    )
    assert reg.call("prom")["kind"] == "error"
    assert reg.call("vacia")["kind"] == "empty"
    assert reg.call("datos")["data"] == {"replicas": 2}
