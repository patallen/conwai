"""
Experiment 0029: PCA on residual vectors.

Combines the two best embedding techniques:
- Residual: removes shared component (0013 showed 3x std improvement)
- PCA: removes noise dimensions (0015 showed structure in 2-3 PCs)

Together: remove shared component, THEN project to top discriminative axes.
This should maximize the signal-to-noise ratio for clustering.

Usage:
    PYTHONPATH=. uv run python experiments/0029-residual-pca/run.py
"""

import json
from pathlib import Path

import numpy as np
from sklearn.cluster import AgglomerativeClustering, KMeans
from sklearn.metrics import silhouette_score

CACHE_VECS = Path("experiments/helen_embeddings.npz")
CACHE_PARSED = Path("experiments/helen_parsed.json")


def pca_project(X: np.ndarray, n_components: int) -> np.ndarray:
    mean = X.mean(axis=0)
    centered = X - mean
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ Vt[:n_components].T


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"]
    print(f"Loaded {len(parsed)} entries, vectors {vectors.shape}\n")

    # Step 1: Residual
    centroid = np.mean(vectors, axis=0)
    residuals = vectors - centroid

    # Step 2: PCA on residuals
    for n_pcs in [2, 3, 5, 10, 20]:
        projected = pca_project(residuals, n_pcs)

        print(f"\n{'=' * 70}")
        print(f"RESIDUAL + PCA({n_pcs} components)")
        print(f"{'=' * 70}")

        # Try different K values
        best_k, best_sil = 0, -1.0
        for k in [5, 8, 10, 12, 15]:
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(projected)
            sil = silhouette_score(projected, labels, metric="cosine")
            sizes = sorted([int((labels == ki).sum()) for ki in range(k)], reverse=True)
            print(f"  K={k:2d}: silhouette={sil:.4f} sizes={sizes}")
            if sil > best_sil:
                best_sil = sil
                best_k = k

        # Also try agglomerative clustering
        for linkage in ["ward", "average", "complete"]:
            for k in [8, 10]:
                try:
                    agg = AgglomerativeClustering(n_clusters=k, linkage=linkage)
                    labels = agg.fit_predict(projected)
                    sil = silhouette_score(projected, labels, metric="cosine")
                    sizes = sorted(
                        [int((labels == ki).sum()) for ki in range(k)], reverse=True
                    )
                    print(f"  Agglom({linkage},K={k}): sil={sil:.4f} sizes={sizes}")
                except Exception as e:
                    print(f"  Agglom({linkage},K={k}): failed ({e})")

        # Detailed view of best K
        print(f"\n  BEST: K={best_k} (silhouette={best_sil:.4f})")
        km = KMeans(n_clusters=best_k, random_state=42, n_init=10)
        labels = km.fit_predict(projected)

        for ki in range(best_k):
            mask = labels == ki
            indices = np.where(mask)[0]
            action_counts: dict[str, int] = {}
            for idx in indices:
                action_counts[parsed[idx]["action"]] = (
                    action_counts.get(parsed[idx]["action"], 0) + 1
                )
            top = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
            action_str = ", ".join(f"{a}:{c}" for a, c in top)
            print(f"    Cluster {ki} ({int(mask.sum())}) [{action_str}]")
            for idx in indices[:2]:
                print(f"      [{idx:3d}] {parsed[idx]['reasoning'][:100]}")

    # Summary: find the absolute best combo
    print(f"\n{'=' * 70}")
    print("SILHOUETTE SUMMARY (best K per PCA dimension)")
    print(f"{'=' * 70}")
    print(f"{'PCs':>5s} {'Best K':>7s} {'Silhouette':>12s}")
    for n_pcs in [2, 3, 5, 10, 20, 50]:
        projected = pca_project(residuals, n_pcs)
        best_sil = -1.0
        best_k = 0
        for k in [5, 8, 10, 12, 15, 20]:
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(projected)
            sil = silhouette_score(projected, labels, metric="cosine")
            if sil > best_sil:
                best_sil = sil
                best_k = k
        print(f"  {n_pcs:3d}    {best_k:5d}      {best_sil:10.4f}")


if __name__ == "__main__":
    main()
