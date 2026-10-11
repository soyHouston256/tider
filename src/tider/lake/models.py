from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date


@dataclass
class Doc:
    id: str
    doc_type: str            # runbook | architecture | incident | adr
    service: str | None = None
    title: str = ""
    updated: date | None = None
    meta: dict = field(default_factory=dict)


@dataclass
class Chunk:
    doc_id: str
    ord: int
    text: str


@dataclass
class Edge:
    src: str
    dst: str
    label: str = ""
    doc_id: str = ""
