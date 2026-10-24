"""Almacenes del context lake. InMemoryStore (pruebas/offline) y PgVectorStore (piloto/GKE) comparten interfaz.
search devuelve el mejor trozo POR DOCUMENTO: k resultados = k documentos distintos."""

from __future__ import annotations

import json

from .embed import Embedder, HashEmbedder, cosine, tokens
from .models import Chunk, Doc, Edge


def best_per_doc(rows: list[dict], k: int) -> list[dict]:
    seen, out = set(), []
    for r in rows:  # rows ya vienen ordenadas por score
        if r["doc_id"] not in seen:
            seen.add(r["doc_id"])
            out.append(r)
    return out[:k]


class InMemoryStore:
    def __init__(self, embedder: Embedder | None = None):
        self.embedder = embedder or HashEmbedder()
        self.docs: dict[str, Doc] = {}
        self.chunks: list[tuple[Chunk, list[float]]] = []
        self.edges: list[Edge] = []

    def upsert(self, doc: Doc, chunks: list[Chunk], edges: list[Edge]) -> None:
        self.docs[doc.id] = doc
        self.chunks = [c for c in self.chunks if c[0].doc_id != doc.id]
        self.edges = [e for e in self.edges if e.doc_id != doc.id]
        self.chunks += [(c, self.embedder.embed(c.text)) for c in chunks]
        self.edges += edges

    def search(
        self, query: str, k: int = 4, doc_type: str | None = None, service: str | None = None
    ) -> list[dict]:
        """Híbrido: coseno + traslape de palabras clave. Filtra por tipo y servicio cuando se pide
        (los documentos sin servicio, como los runbooks genéricos, valen para cualquiera)."""
        qv, qt = self.embedder.embed(query), set(tokens(query))
        scored = []
        for c, v in self.chunks:
            d = self.docs[c.doc_id]
            if doc_type and d.doc_type != doc_type:
                continue
            if service and d.service and d.service != service:
                continue
            ct = set(tokens(c.text))
            kw = len(qt & ct) / (len(qt) or 1)
            scored.append((0.5 * cosine(qv, v) + 0.5 * kw, c, d))
        scored.sort(key=lambda x: x[0], reverse=True)
        return best_per_doc(
            [
                {
                    "doc_id": d.id,
                    "doc_type": d.doc_type,
                    "title": d.title,
                    "service": d.service,
                    "updated": d.updated.isoformat() if d.updated else None,
                    "text": c.text,
                    "score": round(s, 3),
                }
                for s, c, d in scored
            ],
            k,
        )

    def neighbors(self, service: str) -> dict[str, list[str]]:
        s = service.lower()
        up = sorted({e.src for e in self.edges if e.dst.lower() == s})
        down = sorted({e.dst for e in self.edges if e.src.lower() == s})
        return {"upstream": up, "downstream": down}


class PgVectorStore:
    """Misma interfaz sobre Postgres + pgvector (ver schema.sql). SIN PROBAR: pendiente de conectar en la semana 2.
    Ojo: ts_rank y el traslape de palabras del InMemoryStore no están en la misma escala; calibrar al conectarlo."""

    def __init__(self, dsn: str, embedder: Embedder | None = None):
        import psycopg  # opcional: pip install '.[pg]'

        self.conn = psycopg.connect(dsn, autocommit=True)
        self.embedder = embedder or HashEmbedder()

    def upsert(self, doc: Doc, chunks: list[Chunk], edges: list[Edge]) -> None:
        with self.conn.transaction(), self.conn.cursor() as cur:
            cur.execute("DELETE FROM docs WHERE id=%s", (doc.id,))
            cur.execute(
                "INSERT INTO docs(id,doc_type,service,title,updated,meta) VALUES (%s,%s,%s,%s,%s,%s::jsonb)",
                (
                    doc.id,
                    doc.doc_type,
                    doc.service,
                    doc.title,
                    doc.updated,
                    json.dumps(doc.meta, default=str),
                ),
            )
            for c in chunks:
                cur.execute(
                    "INSERT INTO chunks(doc_id,ord,text,embedding) VALUES (%s,%s,%s,%s::vector)",
                    (c.doc_id, c.ord, c.text, str(self.embedder.embed(c.text))),
                )
            for e in edges:
                cur.execute(
                    "INSERT INTO edges(src,dst,label,doc_id) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (e.src, e.dst, e.label, e.doc_id),
                )

    def search(
        self, query: str, k: int = 4, doc_type: str | None = None, service: str | None = None
    ) -> list[dict]:
        qv = str(self.embedder.embed(query))
        sql = """SELECT d.id,d.doc_type,d.title,d.service,d.updated,c.text,
                        0.5*(1-(c.embedding <=> %s::vector)) + 0.5*ts_rank(c.tsv, plainto_tsquery('simple', %s)) AS score
                 FROM chunks c JOIN docs d ON d.id=c.doc_id
                 WHERE (%s::text IS NULL OR d.doc_type=%s) AND (%s::text IS NULL OR d.service IS NULL OR d.service=%s)
                 ORDER BY score DESC LIMIT %s"""
        with (
            self.conn.cursor() as cur
        ):  # ::text: con binding del lado del servidor, "NULL IS NULL" no tiene tipo
            cur.execute(sql, (qv, query, doc_type, doc_type, service, service, k * 4))
            return best_per_doc(
                [
                    {
                        "doc_id": r[0],
                        "doc_type": r[1],
                        "title": r[2],
                        "service": r[3],
                        "updated": r[4].isoformat() if r[4] else None,
                        "text": r[5],
                        "score": float(r[6]),
                    }
                    for r in cur.fetchall()
                ],
                k,
            )

    def neighbors(self, service: str) -> dict[str, list[str]]:
        with self.conn.cursor() as cur:
            cur.execute("SELECT DISTINCT src FROM edges WHERE lower(dst)=lower(%s)", (service,))
            up = sorted(r[0] for r in cur.fetchall())
            cur.execute("SELECT DISTINCT dst FROM edges WHERE lower(src)=lower(%s)", (service,))
            return {"upstream": up, "downstream": sorted(r[0] for r in cur.fetchall())}
