"""Versioned inputs shared by the offline scorer and the opt-in model run."""

import hashlib
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def read(path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False, allow_nan=False) + "\n", encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    manifest = read(HERE / "manifest.json")
    for name, expected in manifest["files"].items():
        if digest(ROOT / name) != expected:
            raise ValueError(f"Cambió una entrada congelada: {name}. Versiona el protocolo antes de medir.")
    corpus = [*runbooks(), *sorted((HERE / "corpus").iterdir())]
    if any(str(path.relative_to(ROOT)) not in manifest["files"] for path in corpus):
        raise ValueError("Documento adicional fuera del corpus congelado")
    return manifest


def runbooks():
    return sorted((ROOT / "docs/runbooks").glob("*.md"))


def passage(row):
    return f"{row['title']}#{row['chunk']}"
