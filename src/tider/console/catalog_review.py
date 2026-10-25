"""Deterministic, source-backed candidates; only a human-confirmed snapshot is active."""

import hashlib
import re
from copy import deepcopy

from pydantic import BaseModel, Field

from tider.lake.ingest import parse_mermaid

NAME = r"[a-z0-9](?:[-a-z0-9]{0,61}[a-z0-9])?"


def valid_name(value):
    return isinstance(value, str) and re.fullmatch(NAME, value) is not None


def candidate_id(name):
    return hashlib.sha256(name.encode()).hexdigest()[:20]


def extract_candidates(name, doc_id, content, pages):
    nodes, edges = {}, []

    def add_node(label, page, excerpt):
        label = label.strip()
        if not valid_name(label):
            return None
        origin = {"doc_id": doc_id, "file": name, "location": page, "excerpt": excerpt[:300]}
        item = nodes.setdefault(label, {"id": candidate_id(label), "name": label, "sources": []})
        if origin not in item["sources"]:
            item["sources"].append(origin)
        return item["id"]

    def add_edge(source, target, label, page, excerpt):
        src, dst = add_node(source, page, excerpt), add_node(target, page, excerpt)
        if src and dst:
            edges.append(
                {
                    "source": src,
                    "target": dst,
                    "label": label[:120],
                    "sources": [{"doc_id": doc_id, "file": name, "location": page, "excerpt": excerpt[:300]}],
                }
            )

    if name.lower().endswith(".drawio"):
        for page, body in pages:
            for line in body.splitlines():
                # Only standalone technical identifiers, not sentences or diagram headings.
                add_node(line, page, line)
                match = re.fullmatch(rf"({NAME}) → ({NAME}) \((.*?)\)", line)
                if match:
                    add_edge(*match.groups(), page, line)
    else:
        front = re.match(r"\A\ufeff?---\s*\n(.*?)\n---(?:\n|$)", content, re.S)
        if front:
            for match in re.finditer(r"^service:\s*[\"\']?(" + NAME + r")[\"\']?\s*$", front[1], re.M):
                add_node(match[1], "Metadatos: service", match[0])
        for index, block in enumerate(re.findall(r"```mermaid\s*\n(.*?)```", content, re.S), 1):
            for edge in parse_mermaid(block):
                add_edge(
                    edge.src,
                    edge.dst,
                    edge.label or "relación dibujada",
                    f"Mermaid {index}",
                    f"{edge.src} → {edge.dst}",
                )
    return {"services": list(nodes.values()), "relations": edges}


def propose(sources):
    services, relations = {}, {}
    for source in sources.values():
        for item in source["services"]:
            row = services.setdefault(item["id"], {"id": item["id"], "name": item["name"], "sources": []})
            row["sources"].extend(s for s in item["sources"] if s not in row["sources"])
        for item in source["relations"]:
            key = (item["source"], item["target"])
            edge_id = candidate_id("|".join(key))
            row = relations.setdefault(key, {**item, "id": edge_id, "sources": []})
            row["sources"].extend(s for s in item["sources"] if s not in row["sources"])
    return {
        "services": sorted(services.values(), key=lambda item: item["name"]),
        "relations": list(relations.values()),
    }


class ReviewedService(BaseModel):
    id: str = Field(max_length=64)
    name: str = Field(pattern="^" + NAME + "$", max_length=63)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class ReviewedRelation(BaseModel):
    id: str = Field(max_length=64)
    source: str = Field(max_length=64)
    target: str = Field(max_length=64)
    label: str = Field(min_length=1, max_length=120)


class CatalogReview(BaseModel):
    revision: int = Field(ge=0)
    services: list[ReviewedService] = Field(min_length=1, max_length=100)
    relations: list[ReviewedRelation] = Field(default_factory=list, max_length=300)


def confirmed_snapshot(review, proposal):
    original_services = {s["id"]: s for s in proposal["services"]}
    original_edges = {e["id"]: e for e in proposal["relations"]}
    ids = [s.id for s in review.services]
    names = [s.name for s in review.services]
    if len(ids) != len(set(ids)) or len(names) != len(set(names)):
        raise ValueError("No se permiten servicios duplicados.")
    if not set(ids) <= original_services.keys():
        raise ValueError("El catálogo incluye candidatos que no existen en la propuesta.")
    selected, relations = [], []
    for service in review.services:
        if any(not alias.strip() or len(alias) > 120 for alias in service.aliases):
            raise ValueError("Los alias deben contener entre 1 y 120 caracteres.")
        selected.append(
            {
                **deepcopy(original_services[service.id]),
                "name": service.name,
                "aliases": list(dict.fromkeys(a.strip().lower() for a in service.aliases)),
                "original_name": original_services[service.id]["name"],
            }
        )
    seen = set()
    edge_ids = set()
    for edge in review.relations:
        if edge.id not in original_edges or edge.source not in ids or edge.target not in ids:
            raise ValueError("Cada relación debe proceder de una fuente y conectar servicios seleccionados.")
        if edge.id in edge_ids or edge.source == edge.target or (edge.source, edge.target) in seen:
            raise ValueError("No se permiten relaciones duplicadas ni hacia el mismo servicio.")
        seen.add((edge.source, edge.target))
        edge_ids.add(edge.id)
        relations.append(
            {
                **deepcopy(original_edges[edge.id]),
                **edge.model_dump(),
                "original_source": original_edges[edge.id]["source"],
                "original_target": original_edges[edge.id]["target"],
            }
        )
    return {"services": selected, "relations": relations}
