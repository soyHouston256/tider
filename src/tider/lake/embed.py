"""Embeddings. HashEmbedder es determinista y sin dependencias (pruebas/offline); en el piloto se reemplaza por un modelo real."""
from __future__ import annotations
import hashlib, math, re
from typing import Protocol

DIM = 256


class Embedder(Protocol):
    def embed(self, text: str) -> list[float]: ...


def tokens(text: str) -> list[str]:
    return re.findall(r"[a-záéíóúñ0-9_\-\.]+", text.lower())


class HashEmbedder:
    def embed(self, text: str) -> list[float]:
        v = [0.0] * DIM
        for tok in tokens(text):
            h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
            v[h % DIM] += 1.0 if (h >> 8) % 2 == 0 else -1.0
        n = math.sqrt(sum(x * x for x in v)) or 1.0
        return [x / n for x in v]


def cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))
