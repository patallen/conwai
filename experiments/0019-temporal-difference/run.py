"""
Experiment 0019: Temporal difference embeddings.

Instead of embedding each entry independently, embed the CHANGE between
consecutive entries. "What's different about this tick vs the last one?"
might cluster better than "what happened this tick?" because the shared
baseline is removed.

Usage:
    PYTHONPATH=. uv run python experiments/0019-temporal-difference/run.py
"""

import json
from pathlib import Path

import numpy as np

CACHE_VECS = Path("experiments/helen_embeddings.npz")
CACHE_PARSED = Path("experiments/helen_parsed.json")


def pairwise_stats(vectors: np.ndarray) -> dict:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sim = (vectors / norms) @ (vectors / norms).T
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {"mean": float(np.mean(upper)), "std": float(np.std(upper))}


def kmeans_cosine(vectors: np.ndarray, k: int, max_iter: int = 100, seed: int = 42) -> np.ndarray:
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
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"]
    print(f"Loaded {len(parsed)} entries, vectors {vectors.shape}")

    # Compute temporal differences
    diffs = np.diff(vectors, axis=0)  # (250, 1024)
    diff_parsed = parsed[1:]  # skip first entry
    print(f"Temporal differences: {diffs.shape}")

    # Stats comparison
    orig_stats = pairwise_stats(vectors)
    diff_stats = pairwise_stats(diffs)
    print(f"\nOriginal:    mean={orig_stats['mean']:.4f} std={orig_stats['std']:.4f}")
    print(f"Differences: mean={diff_stats['mean']:.4f} std={diff_stats['std']:.4f}")

    # Also try windowed differences (diff from rolling window of last 5)
    window = 5
    windowed_diffs = np.zeros_like(vectors)
    for i in range(len(vectors)):
        start = max(0, i - window)
        if start < i:
            local_mean = vectors[start:i].mean(axis=0)
            windowed_diffs[i] = vectors[i] - local_mean
        else:
            windowed_diffs[i] = vectors[i] - vectors.mean(axis=0)

    win_stats = pairwise_stats(windowed_diffs)
    print(f"Windowed(5): mean={win_stats['mean']:.4f} std={win_stats['std']:.4f}")

    # K-means on each representation
    print(f"\n{'='*70}")
    print("K-MEANS COMPARISON (K=10)")
    print(f"{'='*70}")

    for name, vecs, entries in [
        ("original", vectors, parsed),
        ("temporal_diff", diffs, diff_parsed),
        ("windowed_diff_5", windowed_diffs, parsed),
    ]:
        labels = kmeans_cosine(vecs, 10)
        sizes = sorted([int((labels == k).sum()) for k in range(10)], reverse=True)
        print(f"\n  {name}: sizes={sizes}")

        for ki in range(10):
            mask = labels == ki
            indices = np.where(mask)[0]
            action_counts: dict[str, int] = {}
            for idx in indices:
                if idx < len(entries):
                    a = entries[idx]["action"]
                    action_counts[a] = action_counts.get(a, 0) + 1
            top = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
            action_str = ", ".join(f"{a}:{c}" for a, c in top)
            print(f"    Cluster {ki}: {int(mask.sum()):3d} [{action_str}]")
            for idx in indices[:2]:
                if idx < len(entries):
                    print(f"      [{idx:3d}] {entries[idx]['reasoning'][:100]}")


if __name__ == "__main__":
    main()
