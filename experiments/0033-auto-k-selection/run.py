"""
Experiment 0033: Automatic K selection for consolidation.

In production, we can't manually pick K. Test methods for automatically
determining the right number of clusters:
1. Elbow method (inertia curve)
2. Silhouette method (max silhouette)
3. Gap statistic
4. Calinski-Harabasz index

Applied to the best representation: residual+PCA(5).

Usage:
    PYTHONPATH=. uv run python experiments/0033-auto-k-selection/run.py
"""

import json
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import calinski_harabasz_score, silhouette_score

CACHE_VECS = Path("experiments/helen_embeddings.npz")
CACHE_PARSED = Path("experiments/helen_parsed.json")


def pca_project(X: np.ndarray, n_components: int) -> np.ndarray:
    mean = X.mean(axis=0)
    centered = X - mean
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ Vt[:n_components].T


def gap_statistic(X: np.ndarray, k: int, n_refs: int = 10, seed: int = 42) -> float:
    """Compute gap statistic for K clusters."""
    rng = np.random.RandomState(seed)
    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    km.fit(X)
    inertia = km.inertia_

    # Reference datasets (uniform random in bounding box)
    ref_inertias = []
    for i in range(n_refs):
        ref = rng.uniform(X.min(axis=0), X.max(axis=0), size=X.shape)
        km_ref = KMeans(n_clusters=k, random_state=seed + i, n_init=5)
        km_ref.fit(ref)
        ref_inertias.append(km_ref.inertia_)

    gap = np.mean(np.log(ref_inertias)) - np.log(inertia + 1e-10)
    return float(gap)


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"]
    print(f"Loaded {len(parsed)} entries\n")

    centroid = np.mean(vectors, axis=0)
    residuals = vectors - centroid
    projected = pca_project(residuals, 5)

    k_range = range(2, 25)

    inertias = []
    silhouettes = []
    calinski = []
    gaps = []

    print(
        f"{'K':>4s} {'Inertia':>12s} {'Silhouette':>12s} {'Calinski-H':>12s} {'Gap':>10s}"
    )
    for k in k_range:
        km = KMeans(n_clusters=k, random_state=42, n_init=10)
        labels = km.fit_predict(projected)

        inertia = km.inertia_
        sil = silhouette_score(projected, labels, metric="cosine")
        ch = calinski_harabasz_score(projected, labels)
        gap = gap_statistic(projected, k)

        inertias.append(inertia)
        silhouettes.append(sil)
        calinski.append(ch)
        gaps.append(gap)

        print(f"  {k:2d}   {inertia:10.2f}   {sil:10.4f}   {ch:10.1f}   {gap:8.4f}")

    # Find optimal K by each method
    print(f"\n{'=' * 70}")
    print("OPTIMAL K SELECTION")
    print(f"{'=' * 70}")

    # Silhouette: max
    best_sil_k = list(k_range)[np.argmax(silhouettes)]
    print(f"  Silhouette method: K={best_sil_k} (sil={max(silhouettes):.4f})")

    # Calinski-Harabasz: max
    best_ch_k = list(k_range)[np.argmax(calinski)]
    print(f"  Calinski-Harabasz: K={best_ch_k} (CH={max(calinski):.1f})")

    # Elbow: largest 2nd derivative of inertia
    if len(inertias) > 2:
        second_deriv = [
            inertias[i - 1] - 2 * inertias[i] + inertias[i + 1]
            for i in range(1, len(inertias) - 1)
        ]
        elbow_idx = np.argmax(second_deriv) + 1
        elbow_k = list(k_range)[elbow_idx]
        print(f"  Elbow method:      K={elbow_k}")

    # Gap: first K where gap(k) >= gap(k+1) - std
    best_gap_k = list(k_range)[np.argmax(gaps)]
    print(f"  Gap statistic:     K={best_gap_k} (gap={max(gaps):.4f})")

    print(
        f"\n  Consensus: the methods suggest K in range [{min(best_sil_k, best_ch_k)}, {max(best_sil_k, best_ch_k)}]"
    )

    # Show clusters at consensus K
    consensus_k = best_sil_k
    print(f"\n{'=' * 70}")
    print(f"CLUSTERS AT CONSENSUS K={consensus_k}")
    print(f"{'=' * 70}")
    km = KMeans(n_clusters=consensus_k, random_state=42, n_init=10)
    labels = km.fit_predict(projected)
    for ki in range(consensus_k):
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


if __name__ == "__main__":
    main()
