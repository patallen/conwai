"""
Experiment 0015: PCA analysis of embedding space.

Find the principal components of variation in the embedding space.
What dimensions capture the most variance? Can we cluster on just
the top discriminative dimensions?

Usage:
    PYTHONPATH=. uv run python experiments/0015-pca-analysis/run.py
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


def pca(X: np.ndarray, n_components: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """PCA via SVD. Returns (projected, components, explained_variance_ratio)."""
    mean = X.mean(axis=0)
    centered = X - mean
    U, S, Vt = np.linalg.svd(centered, full_matrices=False)
    explained_var = (S**2) / (len(X) - 1)
    total_var = explained_var.sum()
    ratio = explained_var / total_var

    projected = centered @ Vt[:n_components].T
    return projected, Vt[:n_components], ratio[:n_components]


def kmeans_cosine(
    vectors: np.ndarray, k: int, max_iter: int = 100, seed: int = 42
) -> np.ndarray:
    """K-means with cosine distance. Returns labels."""
    rng = np.random.RandomState(seed)
    n = len(vectors)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = vectors / norms

    # Random init
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


def pairwise_stats(vectors: np.ndarray) -> dict:
    if len(vectors) < 2:
        return {}
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sim = (vectors / norms) @ (vectors / norms).T
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {"mean": float(np.mean(upper)), "std": float(np.std(upper))}


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

    # PCA
    n_components = 50
    projected, components, var_ratio = pca(vectors, n_components)
    print("\nPCA variance explained:")
    cumulative = 0.0
    for i in range(min(20, n_components)):
        cumulative += var_ratio[i]
        bar = "#" * int(var_ratio[i] * 200)
        print(
            f"  PC{i + 1:2d}: {var_ratio[i] * 100:5.2f}% (cum: {cumulative * 100:5.1f}%) {bar}"
        )

    print(f"\n  Top 5 PCs explain: {sum(var_ratio[:5]) * 100:.1f}%")
    print(f"  Top 10 PCs explain: {sum(var_ratio[:10]) * 100:.1f}%")
    print(f"  Top 20 PCs explain: {sum(var_ratio[:20]) * 100:.1f}%")
    print(f"  Top 50 PCs explain: {sum(var_ratio[:50]) * 100:.1f}%")

    # Cluster on different numbers of PCs
    print(f"\n{'=' * 70}")
    print("CLUSTERING ON TOP-N PRINCIPAL COMPONENTS (K=10)")
    print(f"{'=' * 70}")
    for n_pcs in [2, 3, 5, 10, 20, 50]:
        pc_vecs = projected[:, :n_pcs]
        stats = pairwise_stats(pc_vecs)
        labels = kmeans_cosine(pc_vecs, 10)
        sizes = sorted([int((labels == k).sum()) for k in range(10)], reverse=True)
        print(
            f"  {n_pcs:2d} PCs: mean_sim={stats.get('mean', 0):.4f} "
            f"std={stats.get('std', 0):.4f} sizes={sizes}"
        )

    # What do the top PCs correlate with?
    print(f"\n{'=' * 70}")
    print("TOP PC ANALYSIS: What does each PC separate?")
    print(f"{'=' * 70}")
    for pc_idx in range(5):
        pc_values = projected[:, pc_idx]
        # Sort entries by this PC
        sorted_indices = np.argsort(pc_values)

        print(f"\nPC{pc_idx + 1} (explains {var_ratio[pc_idx] * 100:.2f}% variance):")

        # Bottom 5 (most negative)
        print("  BOTTOM (most negative):")
        for idx in sorted_indices[:3]:
            print(
                f"    [{idx:3d}] [{parsed[idx]['action']:15s}] {parsed[idx]['reasoning'][:100]}"
            )

        # Top 5 (most positive)
        print("  TOP (most positive):")
        for idx in sorted_indices[-3:]:
            print(
                f"    [{idx:3d}] [{parsed[idx]['action']:15s}] {parsed[idx]['reasoning'][:100]}"
            )

        # Action type correlation
        action_means: dict[str, float] = {}
        for action in set(p["action"] for p in parsed):
            indices = [i for i, p in enumerate(parsed) if p["action"] == action]
            if indices:
                action_means[action] = float(pc_values[indices].mean())
        sorted_actions = sorted(action_means.items(), key=lambda x: x[1])
        print(
            f"  Action means: {', '.join(f'{a}:{v:+.2f}' for a, v in sorted_actions)}"
        )


if __name__ == "__main__":
    main()
