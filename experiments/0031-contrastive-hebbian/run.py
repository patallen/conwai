"""
Experiment 0031: Contrastive Hebbian on residual+PCA vectors.

0018 showed naive Hebbian compresses the ball. Fix: add REPULSION.
Co-recalled pairs attract, random pairs repel. Applied to the
residual+PCA(5) space where there's already meaningful spread.

Usage:
    PYTHONPATH=. uv run python experiments/0031-contrastive-hebbian/run.py
"""

import json
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

CACHE_VECS = Path("experiments/helen_embeddings.npz")
CACHE_PARSED = Path("experiments/helen_parsed.json")


def pca_project(X: np.ndarray, n_components: int) -> np.ndarray:
    mean = X.mean(axis=0)
    centered = X - mean
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ Vt[:n_components].T


def cosine_matrix(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = vectors / norms
    return normed @ normed.T


def pairwise_stats(vectors: np.ndarray) -> dict:
    sim = cosine_matrix(vectors)
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {"mean": float(np.mean(upper)), "std": float(np.std(upper))}


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"]
    print(f"Loaded {len(parsed)} entries\n")

    # Residual + PCA
    centroid = np.mean(vectors, axis=0)
    residuals = vectors - centroid
    projected = pca_project(residuals, 5)
    original_projected = projected.copy()

    stats = pairwise_stats(projected)
    print(f"Initial (residual+PCA5): mean={stats['mean']:.4f} std={stats['std']:.4f}")

    # Baseline silhouette
    km = KMeans(n_clusters=8, random_state=42, n_init=10)
    labels = km.fit_predict(projected)
    sil = silhouette_score(projected, labels, metric="cosine")
    print(f"Baseline K=8 silhouette: {sil:.4f}\n")

    # Contrastive Hebbian: attract co-recalled, repel random
    rng = np.random.RandomState(42)
    RECALL_K = 5
    ATTRACT_RATE = 0.01
    REPEL_RATE = 0.005

    for pass_num in range(5):
        sim = cosine_matrix(projected)

        for query_idx in range(len(projected)):
            # Attract: top-K co-recalled
            sims = sim[query_idx].copy()
            sims[query_idx] = -1
            top_k = np.argsort(sims)[-RECALL_K:]

            for neighbor_idx in top_k:
                diff = projected[neighbor_idx] - projected[query_idx]
                projected[query_idx] += ATTRACT_RATE * diff
                projected[neighbor_idx] -= ATTRACT_RATE * diff

            # Repel: K random non-neighbors
            all_indices = list(range(len(projected)))
            all_indices.remove(query_idx)
            for ni in top_k:
                if ni in all_indices:
                    all_indices.remove(ni)
            if len(all_indices) >= RECALL_K:
                random_repel = rng.choice(all_indices, RECALL_K, replace=False)
                for repel_idx in random_repel:
                    diff = projected[repel_idx] - projected[query_idx]
                    projected[query_idx] -= REPEL_RATE * diff
                    projected[repel_idx] += REPEL_RATE * diff

        stats = pairwise_stats(projected)
        km = KMeans(n_clusters=8, random_state=42, n_init=10)
        labels = km.fit_predict(projected)
        sil = silhouette_score(projected, labels, metric="cosine")
        print(
            f"Pass {pass_num + 1}: mean={stats['mean']:.4f} std={stats['std']:.4f} sil(K=8)={sil:.4f}"
        )

    # Final analysis
    print(f"\n{'=' * 70}")
    print("FINAL CLUSTERING")
    print(f"{'=' * 70}")
    for k in [5, 8, 10]:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(projected)
        sil = silhouette_score(projected, labels, metric="cosine")
        sizes = sorted([int((labels == ki).sum()) for ki in range(k)], reverse=True)
        print(f"  K={k}: sil={sil:.4f} sizes={sizes}")

    # Detailed K=8
    km = KMeans(n_clusters=8, random_state=42, n_init=10)
    labels = km.fit_predict(projected)
    print("\nDetailed K=8:")
    for ki in range(8):
        mask = labels == ki
        indices = np.where(mask)[0]
        action_counts: dict[str, int] = {}
        for idx in indices:
            action_counts[parsed[idx]["action"]] = (
                action_counts.get(parsed[idx]["action"], 0) + 1
            )
        top = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
        action_str = ", ".join(f"{a}:{c}" for a, c in top)
        print(f"  Cluster {ki} ({int(mask.sum())}) [{action_str}]")
        for idx in indices[:2]:
            print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:100]}")

    # Comparison
    print(f"\n{'=' * 70}")
    print("COMPARISON: BEFORE vs AFTER CONTRASTIVE HEBBIAN")
    print(f"{'=' * 70}")
    before_stats = pairwise_stats(original_projected)
    after_stats = pairwise_stats(projected)
    km_before = KMeans(n_clusters=8, random_state=42, n_init=10)
    km_after = KMeans(n_clusters=8, random_state=42, n_init=10)
    sil_before = silhouette_score(
        original_projected, km_before.fit_predict(original_projected), metric="cosine"
    )
    sil_after = silhouette_score(
        projected, km_after.fit_predict(projected), metric="cosine"
    )
    print(
        f"  Before: mean={before_stats['mean']:.4f} std={before_stats['std']:.4f} sil={sil_before:.4f}"
    )
    print(
        f"  After:  mean={after_stats['mean']:.4f} std={after_stats['std']:.4f} sil={sil_after:.4f}"
    )


if __name__ == "__main__":
    main()
