"""Session-scoped document retrieval. Files are data, never executable instructions."""

import base64
import hashlib
import html
import math
import re
import unicodedata
import zlib
from collections import Counter
from copy import deepcopy
from threading import RLock
from urllib.parse import unquote
from uuid import uuid4

from defusedxml import ElementTree

from tider.lake.ingest import split_markdown

from .catalog_review import CatalogReview, confirmed_snapshot, extract_candidates, propose

MAX_BYTES = 1_000_000
MAX_DOCUMENTS = 20
MAX_CHUNKS = 300
# Conservative retrieval gate, not an answerability or causality classifier.
MAX_DISTANCE = 0.55
STOP_WORDS = set(
    "a al algo como con cual cuales cuando de del desde donde el ella en es esta estan este "
    "estos hay la las le lo los me mi mis nos o para por que se si sin sobre su sus te tiene "
    "tienen todo tu tus un una unos unas y dame dime lista favor quiero saber "
    "the a an is are of to in for and what which how my give me please".split()
)


def terms(value: str) -> set[str]:
    value = "".join(c for c in unicodedata.normalize("NFKD", value.lower()) if not unicodedata.combining(c))
    return {
        word for word in re.findall(r"[a-z0-9][a-z0-9_-]*", value) if word not in STOP_WORDS and len(word) > 2
    }


# A static operations manual can explain how to measure something. An answer about
# a relative time needs a passage anchored to that time, too.
RELATIVE_TIME = re.compile(r"\b(hoy|ayer|anoche|ahora(?: mismo)?|en este (?:momento|instante)|"
                           r"today|yesterday|tonight|right now|currently)\b", re.I)


def rank_passages(query, rows, k):
    """Rank by semantic similarity and corpus-weighted word matches; return citable passages."""
    keywords = terms(query)
    if not keywords:
        return []
    documents = [(row, terms(row["text"])) for row in rows
                 if any(line.strip() and not line.lstrip().startswith("#") for line in row["text"].splitlines())]
    frequency = Counter(word for _, words in documents for word in words)
    time_anchor = RELATIVE_TIME.search(query)
    asks_for_method = bool(re.search(r"\b(c[oó]mo|how)\b", query, re.I))

    def weight(word):
        return 1 + math.log((1 + len(documents)) / (1 + frequency[word]))

    query_weight = sum(weight(t) for t in sorted(keywords))
    ranked = []
    for row, words in documents:
        if time_anchor and not asks_for_method and time_anchor[0].casefold() not in row["text"].casefold():
            continue
        hits = keywords & words
        matched = sum(weight(t) for t in sorted(hits))
        coverage = matched / query_weight
        distance = row["distance"]
        identifier = any("_" in t or "-" in t for t in hits)
        lexical = (len(hits) >= 2 and coverage >= 0.20) or identifier or coverage >= 0.65
        semantic = distance <= 0.43 or (distance <= MAX_DISTANCE and bool(hits))
        if not (semantic or lexical):
            continue
        # Coverage retains rare technical names; cosine similarity helps paraphrases.
        score = coverage + 0.45 * (1 - distance)
        ranked.append((-score, distance, row["doc_id"], row["chunk"], row))
    ranked.sort(key=lambda item: item[:4])
    return [{**item[-1], "distance": round(item[1], 4)} for item in ranked[:k]]

def plain(value: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", " ", value)).strip()


def extract(name: str, content: str) -> list[tuple[str, str]]:
    if name.lower().endswith(".md"):
        # YAML front matter describes a document; it is not an independent passage.
        body = re.sub(
            r"\A\ufeff?---[ \t]*\r?\n.*?\r?\n(?:---|\.\.\.)[ \t]*(?:\r?\n|$)",
            "",
            content,
            count=1,
            flags=re.S,
        )
        return [("Documento", body)]
    if not name.lower().endswith(".drawio"):
        raise ValueError("Admite Markdown (.md) y diagramas .drawio.")
    try:
        root = ElementTree.fromstring(content)
        pages = [root] if root.tag == "mxGraphModel" else list(root.findall("diagram"))
        result = []
        for number, page in enumerate(pages, 1):
            model = page if page.tag == "mxGraphModel" else page.find("mxGraphModel")
            if model is None and page.text and page.text.strip():
                inflater = zlib.decompressobj(-15)
                decoded = inflater.decompress(base64.b64decode(page.text.strip()), MAX_BYTES + 1)
                if len(decoded) > MAX_BYTES or not inflater.eof:
                    raise ValueError("La página comprimida supera el límite o está incompleta.")
                model = ElementTree.fromstring(unquote(decoded.decode("utf-8")))
            if model is None:
                continue
            cells = list(model.iter("mxCell"))
            names = {c.get("id"): plain(c.get("value", "")) for c in cells if c.get("vertex") == "1"}
            lines = [v for v in names.values() if v]
            for cell in cells:
                if cell.get("edge") == "1":
                    source, target = names.get(cell.get("source")), names.get(cell.get("target"))
                    if source and target:
                        lines.append(
                            f"{source} → {target} ({plain(cell.get('value', '')) or 'relación dibujada'})"
                        )
            result.append((page.get("name", f"Página {number}"), "\n".join(lines)))
        return result
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("No se pudo leer el XML del diagrama draw.io.") from exc


class ContextLake:
    """One isolated Chroma collection per application; lazy local embeddings."""

    def __init__(self, embedding_function=None):
        import chromadb
        from chromadb.config import Settings
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        self.lock = RLock()
        self.documents = {}
        self.catalog_sources = {}
        self.catalog_revision = 0
        self.confirmed_catalog = None
        self.client = chromadb.EphemeralClient(settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.create_collection(
            name="context-" + uuid4().hex,
            embedding_function=embedding_function or DefaultEmbeddingFunction(),
            metadata={"hnsw:space": "cosine"},
        )

    def inventory(self):
        with self.lock:
            return {
                "documents": list(self.documents.values()),
                "chunks": self.collection.count(),
                "storage": "memory",
                "embedding": "all-MiniLM-L6-v2 (local)",
                "limits": {"bytes_per_file": MAX_BYTES, "documents": MAX_DOCUMENTS},
            }

    def add(self, name: str, content: str):
        name = name.replace("\\", "/").rsplit("/", 1)[-1]
        if not name or len(name) > 200 or len(content.encode("utf-8")) > MAX_BYTES:
            raise ValueError("Nombre inválido o archivo mayor de 1 MB.")
        doc_id = hashlib.sha256((name + "\0" + content).encode()).hexdigest()
        pages = extract(name, content)
        chunks = [(page, chunk) for page, body in pages for chunk in split_markdown(body, 900)]
        if not chunks:
            raise ValueError(
                "El archivo solo contiene metadatos o no contiene texto extraíble. No se indexó."
            )
        with self.lock:
            if doc_id in self.documents:
                return self.documents[doc_id]
            if len(self.documents) >= MAX_DOCUMENTS or self.collection.count() + len(chunks) > MAX_CHUNKS:
                raise ValueError(
                    "Límite de sesión: 20 documentos o 300 fragmentos. Retira documentos antes de añadir más."
                )
            kind = "architecture" if name.lower().endswith(".drawio") else "runbook"
            self.collection.add(
                ids=[f"{doc_id}:{i}" for i in range(len(chunks))],
                documents=[text for _, text in chunks],
                metadatas=[
                    {"doc_id": doc_id, "title": name, "page": page, "chunk": i + 1, "doc_type": kind}
                    for i, (page, _) in enumerate(chunks)
                ],
            )
            doc = {"id": doc_id, "name": name, "chunks": len(chunks), "pages": len(pages)}
            self.documents[doc_id] = doc
            self.catalog_sources[doc_id] = extract_candidates(name, doc_id, content, pages)
            self.catalog_revision += 1
            self.confirmed_catalog = None
            return doc

    def delete(self, doc_id: str):
        with self.lock:
            if doc_id not in self.documents:
                raise KeyError(doc_id)
            self.collection.delete(where={"doc_id": doc_id})
            del self.documents[doc_id]
            del self.catalog_sources[doc_id]
            self.catalog_revision += 1
            self.confirmed_catalog = None

    def search(self, query: str, k: int = 4):
        with self.lock:
            count = self.collection.count()
            if not count:
                return []
            result = self.collection.query(
                query_texts=[query], n_results=count, include=["documents", "metadatas", "distances"]
            )
            rows = [{**meta, "text": text, "distance": distance}
                    for meta, text, distance in zip(result["metadatas"][0], result["documents"][0],
                                                    result["distances"][0], strict=True)]
            return rank_passages(query, rows, k)

    def snapshot_documents(self):
        """Freeze source text and metadata for one investigation, without embeddings."""
        with self.lock:
            data = self.collection.get(include=["documents", "metadatas"])
            return [dict(meta, text=text) for meta, text in zip(data["metadatas"], data["documents"])]

    def catalog(self):
        with self.lock:
            return deepcopy(
                {
                    "revision": self.catalog_revision,
                    "status": "confirmed"
                    if self.confirmed_catalog
                    else ("pending" if self.documents else "empty"),
                    "proposal": propose(self.catalog_sources),
                    "confirmed": self.confirmed_catalog,
                }
            )

    def confirm_catalog(self, review: CatalogReview):
        with self.lock:
            if review.revision != self.catalog_revision:
                raise ValueError("La propuesta cambió. Vuelve a abrir la revisión antes de confirmar.")
            self.confirmed_catalog = confirmed_snapshot(review, propose(self.catalog_sources))
            self.catalog_revision += 1
            return self.catalog()

    def query_scope(self, service: str):
        with self.lock:
            if not self.documents:
                return None
            if not self.confirmed_catalog:
                raise ValueError("Confirma el catálogo documental antes de consultar los logs.")
            names = {s["id"]: s["name"] for s in self.confirmed_catalog["services"]}
            if service not in names.values():
                raise ValueError("El servicio no pertenece al catálogo confirmado.")
            related = {service}
            for edge in self.confirmed_catalog["relations"]:
                source, target = names[edge["source"]], names[edge["target"]]
                if source == service:
                    related.add(target)
                if target == service:
                    related.add(source)
            return sorted(related)
