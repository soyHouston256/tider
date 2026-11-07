"""Collect ranked passage IDs from both search methods, before looking at relevance labels."""

import argparse
import math
from collections import Counter
from importlib.metadata import version
from pathlib import Path

from chromadb.utils.embedding_functions.onnx_mini_lm_l6_v2 import ONNXMiniLM_L6_V2

from tider.console.context_lake import ContextLake, terms

from .data import HERE, ROOT, digest, passage, read, runbooks, save, verify


class LexicalSearch:
    """TF-IDF cosine on the same normalized term sets used by the console's lexical gate."""

    def __init__(self, rows):
        self.docs = {passage(row): terms(row["text"]) for row in rows}
        freq = Counter(term for doc in self.docs.values() for term in doc)
        self.idf = {term: 1 + math.log((1 + len(rows)) / (1 + n)) for term, n in freq.items()}

    def search(self, query, k):
        query_terms = terms(query) & self.idf.keys()
        # Query norm is constant across the corpus. Zero dot products yield no candidates.
        scores = {}
        for key, doc in self.docs.items():
            dot = sum(self.idf[t] ** 2 for t in sorted(query_terms & doc))
            if dot:
                norm = math.sqrt(sum(self.idf[t] ** 2 for t in sorted(doc)))
                scores[key] = dot / norm
        return sorted(scores, key=lambda key: (-scores[key], key))[:k]


def collect():
    manifest = verify()
    lake = ContextLake()
    for path in [*runbooks(), *sorted((HERE / "corpus").glob("*"))]:
        lake.add(path.name, path.read_text(encoding="utf-8"))
    rows = lake.snapshot_documents()
    lexical = LexicalSearch(rows)
    k = manifest["k"]
    rankings = {}
    for key, query in read(HERE / "queries.json").items():
        rankings[key] = {"tider": [passage(x) for x in lake.search(query, k=k)],
                         "lexical": lexical.search(query, k)}
    weights_dir = ONNXMiniLM_L6_V2.DOWNLOAD_PATH / ONNXMiniLM_L6_V2.EXTRACTED_FOLDER_NAME
    return {"protocol": digest(HERE / "manifest.json"), "k": k, "versions": {
        name: version(name) for name in ("chromadb", "onnxruntime", "tokenizers")},
        "model": lake.inventory()["embedding"], "model_files": {
            f.name: digest(f) for f in sorted(weights_dir.iterdir()) if f.is_file()},
        "code": {name: digest(ROOT / name) for name in ("src/tider/console/context_lake.py",
                 "src/tider/lake/ingest.py", "eval/quality/retrieve.py", "uv.lock")},
        "passages": sorted(passage(row) for row in rows), "rankings": rankings}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path)
    path = parser.parse_args().out
    if path.exists():
        parser.error("Usa una ruta nueva para conservar el registro anterior.")
    data = collect()
    path.parent.mkdir(parents=True, exist_ok=True)
    save(path, data)
    print(f"{len(data['rankings'])} consultas, {len(data['passages'])} fragmentos.")
