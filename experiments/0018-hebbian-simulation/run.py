"""
Experiment 0018: Hebbian reinforcement simulation.

Simulate the co-recall process: when two entries are recalled together
(because they're both relevant to a query), boost their similarity.
Over many recall events, entries that FUNCTIONALLY belong together
should drift closer in embedding space.

Uses Helen's actual diary entries as queries — each entry is a "moment"
where the agent would recall relevant memories.

Usage:
    PYTHONPATH=. uv run python experiments/0018-hebbian-simulation/run.py
"""

import json
from pathlib import Path

import numpy as np

CACHE_VECS = Path("experiments/helen_embeddings.npz")
CACHE_PARSED = Path("experiments/helen_parsed.json")
RECALL_TOP_K = 5
HEBBIAN_RATE = 0.02
N_PASSES = 3


def cosine_matrix(vectors: np.ndarray) -> np.ndarray:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = vectors / norms
    return normed @ normed.T


def pairwise_stats(sim_matrix: np.ndarray) -> dict:
    upper = sim_matrix[np.triu_indices(len(sim_matrix), k=1)]
    return {
        "mean": float(np.mean(upper)),
        "std": float(np.std(upper)),
        "min": float(np.min(upper)),
        "max": float(np.max(upper)),
    }


def cluster_centroid(vectors: np.ndarray, threshold: float) -> list[list[int]]:
    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []
    for idx in range(len(vectors)):
        vec = vectors[idx]
        norm_v = np.linalg.norm(vec)
        if norm_v < 1e-10:
            clusters.append([idx])
            centroids.append(vec.copy())
            continue
        best_ci, best_sim = -1, -1.0
        for ci, c in enumerate(centroids):
            norm_c = np.linalg.norm(c)
            if norm_c < 1e-10:
                continue
            sim = float(np.dot(vec, c) / (norm_v * norm_c))
            if sim > best_sim:
                best_sim = sim
                best_ci = ci
        if best_ci >= 0 and best_sim >= threshold:
            clusters[best_ci].append(idx)
            n = len(clusters[best_ci])
            centroids[best_ci] = centroids[best_ci] * ((n - 1) / n) + vec / n
        else:
            clusters.append([idx])
            centroids.append(vec.copy())
    return clusters


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"].copy()
    original_vectors = vectors.copy()
    print(f"Loaded {len(parsed)} entries, vectors {vectors.shape}")
    sim = cosine_matrix(vectors)
    stats = pairwise_stats(sim)
    print(f"Initial: mean={stats['mean']:.4f} std={stats['std']:.4f}\n")

    # Co-recall frequency matrix
    corecall_count = np.zeros((len(vectors), len(vectors)), dtype=int)

    # Simulate recall passes
    for pass_num in range(N_PASSES):
        for query_idx in range(len(vectors)):
            # Use this entry as a query — find top-K most similar (excluding self)
            sims = cosine_matrix(vectors)[query_idx]
            sims[query_idx] = -1  # exclude self
            top_k = np.argsort(sims)[-RECALL_TOP_K:]

            # Record co-recall: all pairs in top_k were recalled together
            recalled = list(top_k)
            for i in range(len(recalled)):
                for j in range(i + 1, len(recalled)):
                    corecall_count[recalled[i], recalled[j]] += 1
                    corecall_count[recalled[j], recalled[i]] += 1

            # Hebbian update: nudge co-recalled vectors toward each other
            for i in range(len(recalled)):
                for j in range(i + 1, len(recalled)):
                    a, b = recalled[i], recalled[j]
                    # Move a slightly toward b and vice versa
                    diff = vectors[b] - vectors[a]
                    vectors[a] += HEBBIAN_RATE * diff
                    vectors[b] -= HEBBIAN_RATE * diff

        sim = cosine_matrix(vectors)
        stats = pairwise_stats(sim)
        print(
            f"After pass {pass_num + 1}: mean={stats['mean']:.4f} std={stats['std']:.4f}"
        )

    # Final analysis
    print(f"\n{'=' * 70}")
    print("CO-RECALL FREQUENCY ANALYSIS")
    print(f"{'=' * 70}")
    upper_corecall = corecall_count[np.triu_indices(len(vectors), k=1)]
    print(
        f"Co-recall counts: min={upper_corecall.min()} max={upper_corecall.max()} "
        f"mean={upper_corecall.mean():.1f} std={upper_corecall.std():.1f}"
    )

    # Pairs with highest co-recall
    print("\nTop 10 most co-recalled pairs:")
    flat_indices = np.argsort(upper_corecall)[-10:]
    triu = np.triu_indices(len(vectors), k=1)
    for fi in reversed(flat_indices):
        i, j = triu[0][fi], triu[1][fi]
        orig_sim = float(cosine_matrix(original_vectors)[i, j])
        new_sim = float(cosine_matrix(vectors)[i, j])
        print(
            f"  [{i:3d}]-[{j:3d}] corecall={corecall_count[i, j]:3d} "
            f"sim: {orig_sim:.4f} → {new_sim:.4f}"
        )
        print(f"    [{i:3d}] [{parsed[i]['action']}] {parsed[i]['reasoning'][:80]}")
        print(f"    [{j:3d}] [{parsed[j]['action']}] {parsed[j]['reasoning'][:80]}")

    # Cluster the Hebbian-modified vectors
    print(f"\n{'=' * 70}")
    print("CLUSTERING AFTER HEBBIAN MODIFICATION")
    print(f"{'=' * 70}")
    for threshold in [0.70, 0.75, 0.80, 0.85, 0.90]:
        clusters = cluster_centroid(vectors, threshold)
        sizes = sorted([len(c) for c in clusters], reverse=True)
        non_sing = sum(1 for s in sizes if s > 1)
        print(
            f"  threshold={threshold:.2f}: {len(clusters)} clusters "
            f"({non_sing} non-singleton) top={sizes[:10]}"
        )

    # Compare: how did the embedding space change?
    print(f"\n{'=' * 70}")
    print("EMBEDDING SPACE CHANGE")
    print(f"{'=' * 70}")
    orig_sim = cosine_matrix(original_vectors)
    new_sim = cosine_matrix(vectors)
    diff = new_sim - orig_sim
    upper_diff = diff[np.triu_indices(len(vectors), k=1)]
    print(
        f"Similarity changes: mean={upper_diff.mean():.6f} "
        f"std={upper_diff.std():.6f} "
        f"min={upper_diff.min():.6f} max={upper_diff.max():.6f}"
    )

    # Which pairs changed the most?
    print("\nPairs that moved TOGETHER the most:")
    top_increases = np.argsort(upper_diff)[-5:]
    for fi in reversed(top_increases):
        i, j = triu[0][fi], triu[1][fi]
        print(
            f"  [{i:3d}]-[{j:3d}] Δ={upper_diff[fi]:+.4f} "
            f"({float(orig_sim[i, j]):.4f} → {float(new_sim[i, j]):.4f})"
        )
        print(f"    [{i:3d}] [{parsed[i]['action']}] {parsed[i]['reasoning'][:80]}")
        print(f"    [{j:3d}] [{parsed[j]['action']}] {parsed[j]['reasoning'][:80]}")

    print("\nPairs that moved APART the most:")
    top_decreases = np.argsort(upper_diff)[:5]
    for fi in top_decreases:
        i, j = triu[0][fi], triu[1][fi]
        print(
            f"  [{i:3d}]-[{j:3d}] Δ={upper_diff[fi]:+.4f} "
            f"({float(orig_sim[i, j]):.4f} → {float(new_sim[i, j]):.4f})"
        )
        print(f"    [{i:3d}] [{parsed[i]['action']}] {parsed[i]['reasoning'][:80]}")
        print(f"    [{j:3d}] [{parsed[j]['action']}] {parsed[j]['reasoning'][:80]}")


if __name__ == "__main__":
    main()
