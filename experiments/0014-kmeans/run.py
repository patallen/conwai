"""
Experiment 0014: K-means clustering (numpy implementation).

K-means forces K clusters even in a dense ball. Unlike threshold-based
clustering, it doesn't need a gap between clusters — it partitions the
space into regions. Try K=5,8,10,15 and evaluate cluster quality.

Usage:
    PYTHONPATH=. uv run python experiments/0014-kmeans/run.py
"""

import json
import re
from pathlib import Path

import numpy as np

K_VALUES = [5, 8, 10, 15, 20]
MAX_ITER = 100

CACHE_VECS = Path("experiments/helen_embeddings.npz")
CACHE_PARSED = Path("experiments/helen_parsed.json")


def kmeans(vectors: np.ndarray, k: int, max_iter: int = MAX_ITER, seed: int = 42) -> tuple[np.ndarray, np.ndarray]:
    """K-means with cosine distance. Returns (labels, centroids)."""
    rng = np.random.RandomState(seed)
    n = len(vectors)

    # L2 normalize for cosine
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = vectors / norms

    # K-means++ initialization
    indices = [rng.randint(n)]
    for _ in range(1, k):
        centroids = normed[indices]
        sims = normed @ centroids.T  # (n, len(indices))
        max_sims = sims.max(axis=1)
        dists = 1 - max_sims
        dists[dists < 0] = 0
        probs = dists / (dists.sum() + 1e-10)
        idx = rng.choice(n, p=probs)
        indices.append(idx)

    centroids = normed[indices].copy()

    for iteration in range(max_iter):
        # Assign
        sims = normed @ centroids.T
        labels = sims.argmax(axis=1)

        # Update centroids
        new_centroids = np.zeros_like(centroids)
        for ki in range(k):
            mask = labels == ki
            if mask.sum() > 0:
                new_centroids[ki] = normed[mask].mean(axis=0)
                norm = np.linalg.norm(new_centroids[ki])
                if norm > 0:
                    new_centroids[ki] /= norm

        if np.allclose(centroids, new_centroids, atol=1e-6):
            break
        centroids = new_centroids

    return labels, centroids


def silhouette_cosine(vectors: np.ndarray, labels: np.ndarray) -> float:
    """Compute mean silhouette score using cosine distance."""
    n = len(vectors)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = vectors / norms
    sim_matrix = normed @ normed.T
    dist_matrix = 1 - sim_matrix

    scores = []
    for i in range(n):
        own_label = labels[i]
        own_mask = labels == own_label
        own_count = own_mask.sum()

        if own_count <= 1:
            scores.append(0.0)
            continue

        # a(i) = mean distance to same cluster
        a = dist_matrix[i, own_mask].sum() / (own_count - 1)

        # b(i) = min mean distance to other clusters
        b = float('inf')
        for k in np.unique(labels):
            if k == own_label:
                continue
            other_mask = labels == k
            b = min(b, dist_matrix[i, other_mask].mean())

        if b == float('inf'):
            scores.append(0.0)
        else:
            scores.append((b - a) / max(a, b))

    return float(np.mean(scores))


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"]
    print(f"Loaded {len(parsed)} entries, vectors shape {vectors.shape}\n")

    # Try on both raw and residual vectors
    centroid = np.mean(vectors, axis=0)
    residuals = vectors - centroid

    for name, vecs in [("raw", vectors), ("residual", residuals)]:
        print(f"\n{'='*70}")
        print(f"K-MEANS ON {name.upper()} VECTORS")
        print(f"{'='*70}")

        for k in K_VALUES:
            labels, centroids = kmeans(vecs, k)
            sizes = [int((labels == ki).sum()) for ki in range(k)]
            sizes.sort(reverse=True)

            sil = silhouette_cosine(vecs, labels)

            print(f"\n  K={k:2d}: silhouette={sil:.4f} sizes={sizes}")

            # Show action type distribution per cluster
            if k <= 10:
                for ki in range(k):
                    mask = labels == ki
                    cluster_indices = np.where(mask)[0]
                    action_counts: dict[str, int] = {}
                    for idx in cluster_indices:
                        a = parsed[idx]["action"]
                        action_counts[a] = action_counts.get(a, 0) + 1
                    top_actions = sorted(action_counts.items(), key=lambda x: -x[1])[:4]
                    action_str = ", ".join(f"{a}:{c}" for a, c in top_actions)
                    print(f"    Cluster {ki}: {int(mask.sum()):3d} entries [{action_str}]")
                    # Show 2 samples
                    for idx in cluster_indices[:2]:
                        print(f"      [{idx:3d}] {parsed[idx]['reasoning'][:100]}")

    # Summary
    print(f"\n{'='*70}")
    print("SILHOUETTE SUMMARY")
    print(f"{'='*70}")
    print(f"{'K':>4s} {'Raw':>10s} {'Residual':>10s}")
    for k in K_VALUES:
        labels_raw, _ = kmeans(vectors, k)
        labels_res, _ = kmeans(residuals, k)
        sil_raw = silhouette_cosine(vectors, labels_raw)
        sil_res = silhouette_cosine(residuals, labels_res)
        print(f"  {k:2d}   {sil_raw:10.4f} {sil_res:10.4f}")


if __name__ == "__main__":
    main()
