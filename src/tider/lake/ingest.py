"""Ingesta al context lake: Markdown (runbooks/ADR) y Mermaid (arquitectura). Las imágenes quedan fuera del MVP."""
from __future__ import annotations
import re
from datetime import date
from pathlib import Path
import yaml
from .models import Chunk, Doc, Edge

FRONT = re.compile(r"^---\n(.*?)\n---\n", re.S)
NODE = re.compile(r"(\w+)\s*[\[\(\{]+\"?([^\]\)\}\"]+)\"?[\]\)\}]+")
EDGE = re.compile(r"(\w+)(?:\s*[\[\(\{]+[^\]\)\}]*[\]\)\}]+)?\s*[-=.]+>\s*(?:\|([^|]*)\|\s*)?(\w+)")


def parse_mermaid(text: str) -> list[Edge]:
    """Extrae aristas src --> dst de un diagrama Mermaid (graph/flowchart). Usa la etiqueta del nodo como nombre."""
    names = {nid: label.strip() for nid, label in NODE.findall(text)}
    edges = []
    for line in text.splitlines():
        for src, label, dst in EDGE.findall(line):
            edges.append(Edge(names.get(src, src), names.get(dst, dst), (label or "").strip()))
    return edges


def split_markdown(body: str, max_chars: int = 1200) -> list[str]:
    """Parte por encabezados; cada trozo conserva su encabezado para no perder contexto."""
    parts, cur = [], []
    for line in body.splitlines():
        if line.startswith("#") and cur:
            parts.append("\n".join(cur)); cur = []
        cur.append(line)
    if cur:
        parts.append("\n".join(cur))
    out = []
    for p in parts:
        while len(p) > max_chars:
            cut = p.rfind("\n", 1, max_chars)
            cut = cut if cut > 0 else max_chars   # sin salto de línea a mano: corte duro
            out.append(p[:cut]); p = p[cut:]
        if p.strip():
            out.append(p)
    return out


def load_file(path: Path, base: Path | None = None) -> tuple[Doc, list[Chunk], list[Edge]]:
    raw = path.read_text(encoding="utf-8")
    meta, body = {}, raw
    m = FRONT.match(raw)
    if m:
        meta = yaml.safe_load(m.group(1)) or {}
        body = raw[m.end():]
    doc_type = meta.get("type") or ("architecture" if path.suffix in (".mmd", ".mermaid") else "runbook")
    updated = meta.get("updated")
    if isinstance(updated, str):
        updated = date.fromisoformat(updated)
    doc_id = path.relative_to(base).as_posix() if base else str(path)
    doc = Doc(id=doc_id, doc_type=doc_type, service=meta.get("service"),
              title=meta.get("title", path.stem), updated=updated, meta=meta)
    edges: list[Edge] = []
    if path.suffix in (".mmd", ".mermaid") or "```mermaid" in body:
        diagrams = [body] if path.suffix in (".mmd", ".mermaid") else re.findall(r"```mermaid\n(.*?)```", body, re.S)
        for d in diagrams:
            edges += parse_mermaid(d)
    for e in edges:
        e.doc_id = doc.id
    chunks = [Chunk(doc.id, i, t) for i, t in enumerate(split_markdown(body))]
    return doc, chunks, edges


def ingest_dir(store, root: str | Path, base: str | Path | None = None) -> int:
    """base fija el doc_id (ruta relativa a base); por defecto, el padre de root (docs/... -> "docs/...")."""
    n, root = 0, Path(root)
    base = Path(base) if base else root.parent
    for p in sorted(root.rglob("*")):
        if p.suffix in (".md", ".mmd", ".mermaid"):
            doc, chunks, edges = load_file(p, base=base)
            store.upsert(doc, chunks, edges)
            n += 1
    return n
