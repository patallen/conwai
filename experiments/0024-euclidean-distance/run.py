"""
Experiment 0024: Euclidean distance instead of cosine similarity.

Cosine similarity ignores vector magnitude — only direction matters.
Euclidean distance considers both direction AND magnitude. The dense
ball might have internal structure visible to euclidean but not cosine.

Usage:
    PYTHONPATH=. uv run python experiments/0024-euclidean-distance/run.py
"""

import re
from pathlib import Path

import numpy as np

from conwai.llm import FastEmbedder
from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"

_ACTION_RE = re.compile(r"\] (\w+)→")


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def kmeans_euclidean(
    vectors: np.ndarray, k: int, max_iter: int = 100, seed: int = 42
) -> np.ndarray:
    rng = np.random.RandomState(seed)
    n = len(vectors)
    indices = rng.choice(n, k, replace=False)
    centroids = vectors[indices].copy()
    for _ in range(max_iter):
        # Assign to nearest centroid (euclidean)
        dists = np.zeros((n, k))
        for ki in range(k):
            dists[:, ki] = np.linalg.norm(vectors - centroids[ki], axis=1)
        labels = dists.argmin(axis=1)
        new_centroids = np.zeros_like(centroids)
        for ki in range(k):
            mask = labels == ki
            if mask.sum() > 0:
                new_centroids[ki] = vectors[mask].mean(axis=0)
        if np.allclose(centroids, new_centroids, atol=1e-6):
            break
        centroids = new_centroids
    return labels


def kmeans_cosine(
    vectors: np.ndarray, k: int, max_iter: int = 100, seed: int = 42
) -> np.ndarray:
    rng = np.random.RandomState(seed)
    n = len(vectors)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = vectors / norms
    indices = rng.choice(n, k, replace=False)
    centroids = normed[indices].copy()
    for _ in range(max_iter):
        sims = normed @ centroids.T
        labels = sims.argmax(axis=1)
        new_centroids = np.zeros_like(centroids)
        for ki in range(k):
            mask = labels == ki
            if mask.sum() > 0:
                c = normed[mask].mean(axis=0)
                norm = np.linalg.norm(c)
                new_centroids[ki] = c / norm if norm > 0 else c
        if np.allclose(centroids, new_centroids, atol=1e-6):
            break
        centroids = new_centroids
    return labels


def main() -> None:
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries\n")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning})

    print("Embedding...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    vectors = np.array(embedder.embed([p["reasoning"] for p in parsed]))

    # Euclidean distance stats
    n = len(vectors)
    dists = np.zeros((n, n))
    for i in range(n):
        dists[i] = np.linalg.norm(vectors - vectors[i], axis=1)
    upper_dists = dists[np.triu_indices(n, k=1)]

    print("Euclidean distance stats:")
    print(f"  mean={upper_dists.mean():.4f} std={upper_dists.std():.4f}")
    print(f"  min={upper_dists.min():.4f} max={upper_dists.max():.4f}")
    print(
        f"  p25={np.percentile(upper_dists, 25):.4f} p75={np.percentile(upper_dists, 75):.4f}"
    )

    # Vector magnitude stats
    magnitudes = np.linalg.norm(vectors, axis=1)
    print("\nVector magnitudes:")
    print(f"  mean={magnitudes.mean():.4f} std={magnitudes.std():.4f}")
    print(f"  min={magnitudes.min():.4f} max={magnitudes.max():.4f}")

    # Compare cosine vs euclidean K-means
    print(f"\n{'=' * 70}")
    print("K-MEANS COMPARISON: COSINE vs EUCLIDEAN")
    print(f"{'=' * 70}")
    centroid = np.mean(vectors, axis=0)
    residuals = vectors - centroid

    for name, vecs in [("raw", vectors), ("residual", residuals)]:
        for k in [8, 10]:
            labels_cos = kmeans_cosine(vecs, k)
            labels_euc = kmeans_euclidean(vecs, k)
            sizes_cos = sorted(
                [int((labels_cos == ki).sum()) for ki in range(k)], reverse=True
            )
            sizes_euc = sorted(
                [int((labels_euc == ki).sum()) for ki in range(k)], reverse=True
            )
            print(f"\n  {name} K={k}:")
            print(f"    cosine:    {sizes_cos}")
            print(f"    euclidean: {sizes_euc}")

    # Detailed euclidean clusters
    print(f"\n{'=' * 70}")
    print("EUCLIDEAN K-MEANS K=10 ON RAW VECTORS")
    print(f"{'=' * 70}")
    labels = kmeans_euclidean(vectors, 10)
    for ki in range(10):
        mask = labels == ki
        indices = np.where(mask)[0]
        action_counts: dict[str, int] = {}
        for idx in indices:
            action_counts[parsed[idx]["action"]] = (
                action_counts.get(parsed[idx]["action"], 0) + 1
            )
        top = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
        action_str = ", ".join(f"{a}:{c}" for a, c in top)
        # Mean magnitude in cluster
        cluster_mags = magnitudes[indices]
        print(
            f"\n  Cluster {ki} ({int(mask.sum())} entries) [{action_str}] "
            f"mean_mag={cluster_mags.mean():.4f}"
        )
        for idx in indices[:2]:
            print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:100]}")


if __name__ == "__main__":
    main()
