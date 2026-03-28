"""Embedding protocol and implementations for vector-based memory recall."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

import numpy as np


@runtime_checkable
class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class FastEmbedder:
    """CPU-based embedder using fastembed (ONNX runtime, no torch needed)."""

    def __init__(self, model_name: str = "BAAI/bge-small-en-v1.5"):
        from fastembed import TextEmbedding

        self._model = TextEmbedding(model_name)

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [v.tolist() for v in self._model.embed(texts)]


def cosine_topk(
    query_vec: list[float],
    candidates: list[list[float]],
    k: int = 5,
) -> list[int]:
    """Return indices of the top-k most similar candidates by cosine similarity."""
    if not candidates:
        return []
    q = np.array(query_vec)
    mat = np.array(candidates)
    # Cosine similarity: dot(q, each) / (|q| * |each|)
    dots = mat @ q
    norms = np.linalg.norm(mat, axis=1) * np.linalg.norm(q)
    norms[norms == 0] = 1  # avoid division by zero
    scores = dots / norms
    # Top-k indices, highest first
    top = np.argsort(scores)[::-1][:k]
    return [int(i) for i in top if scores[i] > 0]
