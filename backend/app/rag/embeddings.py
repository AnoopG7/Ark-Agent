"""Text embedders: a local ONNX model for the app and a deterministic hash embedder for tests."""

import hashlib
import math
import re
from pathlib import Path
from typing import Protocol


class Embedder(Protocol):
    dim: int

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    """``BAAI/bge-small-en-v1.5`` via fastembed (ONNX on CPU, no external service)."""

    def __init__(self, model_name: str, dim: int, cache_dir: Path | None = None) -> None:
        from fastembed import TextEmbedding

        self.dim = dim
        self._model = TextEmbedding(model_name, cache_dir=str(cache_dir) if cache_dir else None)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]

    def embed_query(self, text: str) -> list[float]:
        return next(iter(self._model.query_embed(text))).tolist()


class HashEmbedder:
    """Bag-of-words feature hashing, L2-normalised. Deterministic and dependency-free."""

    _TOKEN = re.compile(r"[a-z0-9]+")
    _STOP = frozenset(
        [
            "a",
            "an",
            "the",
            "of",
            "for",
            "to",
            "in",
            "on",
            "and",
            "or",
            "is",
            "are",
            "be",
            "by",
            "with",
            "per",
            "at",
            "as",
            "it",
        ]
    )

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def _vector(self, text: str) -> list[float]:
        vec = [0.0] * self.dim
        for token in self._TOKEN.findall(text.lower()):
            if token in self._STOP:
                continue
            token = token.rstrip("s") if len(token) > 3 else token
            h = int(hashlib.md5(token.encode()).hexdigest(), 16)
            vec[h % self.dim] += 1.0 if (h >> 64) & 1 else -1.0
        norm = math.sqrt(sum(v * v for v in vec)) or 1.0
        return [v / norm for v in vec]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vector(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)
