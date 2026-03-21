"""
Experiment 0017: Variance-weighted embedding dimensions.

Not all 1024 embedding dimensions are equally informative. Some capture
the shared "resource management" signal, others capture distinctive
features. Weight each dimension by its variance across entries — high
variance = discriminative, low variance = shared noise.

Usage:
    PYTHONPATH=. uv run python experiments/0017-variance-weighted-dims/run.py
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
    print(f"Loaded {len(parsed)} entries, vectors {vectors.shape}\n")

    # Compute per-dimension variance
    variances = np.var(vectors, axis=0)
    print(f"Dimension variances: min={variances.min():.6f} max={variances.max():.6f} "
          f"mean={variances.mean():.6f} std={variances.std():.6f}")

    # Distribution of variances
    percentiles = [10, 25, 50, 75, 90, 95, 99]
    print(f"Variance percentiles:")
    for p in percentiles:
        print(f"  {p}th: {np.percentile(variances, p):.6f}")

    # How many dims have high vs low variance?
    threshold = np.median(variances)
    high_var_dims = np.where(variances > threshold)[0]
    low_var_dims = np.where(variances <= threshold)[0]
    print(f"\nHigh-variance dims: {len(high_var_dims)}")
    print(f"Low-variance dims: {len(low_var_dims)}")

    # Try different weighting strategies
    strategies = {
        "original": vectors,
        "variance_weighted": vectors * np.sqrt(variances),
        "top_256_dims": vectors[:, np.argsort(variances)[-256:]],
        "top_128_dims": vectors[:, np.argsort(variances)[-128:]],
        "top_64_dims": vectors[:, np.argsort(variances)[-64:]],
        "bottom_256_removed": vectors[:, np.argsort(variances)[256:]],
        "sqrt_variance_only_top50pct": vectors[:, high_var_dims] * np.sqrt(variances[high_var_dims]),
    }

    print(f"\n{'='*70}")
    print("COMPARISON OF WEIGHTING STRATEGIES")
    print(f"{'='*70}")
    print(f"{'Strategy':40s} {'Mean Sim':>10s} {'Std':>10s} {'K=10 sizes':>30s}")

    for name, vecs in strategies.items():
        stats = pairwise_stats(vecs)
        labels = kmeans_cosine(vecs, 10)
        sizes = sorted([int((labels == k).sum()) for k in range(10)], reverse=True)
        print(f"  {name:38s} {stats['mean']:10.4f} {stats['std']:10.4f} {str(sizes)}")

    # Detailed view of best strategy
    # Find the one with lowest mean similarity
    best_name = min(strategies.keys(), key=lambda n: pairwise_stats(strategies[n])["mean"])
    print(f"\n{'='*70}")
    print(f"BEST STRATEGY: {best_name}")
    print(f"{'='*70}")
    best_vecs = strategies[best_name]
    labels = kmeans_cosine(best_vecs, 10)

    for ki in range(10):
        mask = labels == ki
        indices = np.where(mask)[0]
        action_counts: dict[str, int] = {}
        for idx in indices:
            action_counts[parsed[idx]["action"]] = action_counts.get(parsed[idx]["action"], 0) + 1
        top = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
        action_str = ", ".join(f"{a}:{c}" for a, c in top)
        print(f"\n  Cluster {ki} ({int(mask.sum())} entries) [{action_str}]")
        for idx in indices[:3]:
            print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:120]}")


if __name__ == "__main__":
    main()
