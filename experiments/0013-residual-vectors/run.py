"""
Experiment 0013: Residual vectors — subtract corpus centroid before clustering.

The shared "resource management reasoning" component dominates all embeddings.
If we subtract the centroid (the "average entry"), what remains is what makes
each entry DISTINCTIVE. Cluster the residuals.

Usage:
    PYTHONPATH=. uv run python experiments/0013-residual-vectors/run.py
"""

import re
from pathlib import Path

import numpy as np

from conwai.llm import FastEmbedder
from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"
THRESHOLDS = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70]

_ACTION_RE = re.compile(r"\] (\w+)→")


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(line.strip() for line in lines[1:] if line.strip()) or lines[0]
    return action, reasoning


def pairwise_stats(vectors: np.ndarray) -> dict:
    if len(vectors) < 2:
        return {}
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sim = (vectors / norms) @ (vectors / norms).T
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {
        "mean": float(np.mean(upper)),
        "std": float(np.std(upper)),
        "min": float(np.min(upper)),
        "max": float(np.max(upper)),
        "p25": float(np.percentile(upper, 25)),
        "p75": float(np.percentile(upper, 75)),
    }


def cluster_centroid(vectors: list[np.ndarray], threshold: float) -> list[list[int]]:
    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []
    for idx, vec in enumerate(vectors):
        best_ci, best_sim = -1, -1.0
        norm_v = np.linalg.norm(vec)
        if norm_v < 1e-10:
            clusters.append([idx])
            centroids.append(vec.copy())
            continue
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
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries\n")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning})

    print("Embedding reasoning texts...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    raw_vecs = embedder.embed([p["reasoning"] for p in parsed])
    original = np.array(raw_vecs)

    # Original stats
    orig_stats = pairwise_stats(original)
    print(
        f"Original: mean={orig_stats['mean']:.4f} std={orig_stats['std']:.4f} "
        f"range=[{orig_stats['min']:.4f}, {orig_stats['max']:.4f}]"
    )

    # Compute centroid and subtract
    centroid = np.mean(original, axis=0)
    residuals = original - centroid

    res_stats = pairwise_stats(residuals)
    print(
        f"Residual: mean={res_stats['mean']:.4f} std={res_stats['std']:.4f} "
        f"range=[{res_stats['min']:.4f}, {res_stats['max']:.4f}]"
    )
    print(f"  Spread improvement: std {orig_stats['std']:.4f} → {res_stats['std']:.4f}")
    print()

    # Also try subtracting per-action-type centroids
    action_groups: dict[str, list[int]] = {}
    for i, p in enumerate(parsed):
        action_groups.setdefault(p["action"], []).append(i)

    action_residuals = original.copy()
    for action, indices in action_groups.items():
        if len(indices) > 1:
            action_centroid = np.mean(original[indices], axis=0)
            for idx in indices:
                action_residuals[idx] = original[idx] - action_centroid

    act_stats = pairwise_stats(action_residuals)
    print(
        f"Action-residual: mean={act_stats['mean']:.4f} std={act_stats['std']:.4f} "
        f"range=[{act_stats['min']:.4f}, {act_stats['max']:.4f}]"
    )
    print()

    # Cluster residuals at various thresholds
    print(f"{'=' * 70}")
    print("CLUSTERING GLOBAL RESIDUALS")
    print(f"{'=' * 70}")
    for threshold in THRESHOLDS:
        vec_list = [residuals[i] for i in range(len(residuals))]
        clusters = cluster_centroid(vec_list, threshold)
        clusters_sorted = sorted(clusters, key=lambda c: -len(c))
        sizes = [len(c) for c in clusters_sorted]
        non_sing = sum(1 for s in sizes if s > 1)
        print(
            f"  threshold={threshold:.2f}: {len(clusters)} clusters "
            f"({non_sing} non-singleton) top={sizes[:10]}"
        )

    # Find best threshold and show clusters
    best_threshold = None
    for t in THRESHOLDS:
        vec_list = [residuals[i] for i in range(len(residuals))]
        clusters = cluster_centroid(vec_list, t)
        if 5 <= len(clusters) <= 25:
            best_threshold = t
            break
    if best_threshold is None:
        best_threshold = 0.30

    print(f"\n{'=' * 70}")
    print(f"DETAILED VIEW AT THRESHOLD {best_threshold:.2f}")
    print(f"{'=' * 70}")
    vec_list = [residuals[i] for i in range(len(residuals))]
    clusters = cluster_centroid(vec_list, best_threshold)
    clusters_sorted = sorted(clusters, key=lambda c: -len(c))

    for ci, cluster in enumerate(clusters_sorted[:15]):
        action_counts: dict[str, int] = {}
        for idx in cluster:
            action_counts[parsed[idx]["action"]] = (
                action_counts.get(parsed[idx]["action"], 0) + 1
            )
        action_str = ", ".join(
            f"{k}:{v}" for k, v in sorted(action_counts.items(), key=lambda x: -x[1])
        )
        print(f"\n  Cluster {ci + 1} (size={len(cluster)}) [{action_str}]")
        for idx in cluster[:3]:
            print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:130]}")
        if len(cluster) > 3:
            print(f"    ... and {len(cluster) - 3} more")

    # Also cluster action-residuals
    print(f"\n{'=' * 70}")
    print("CLUSTERING ACTION-TYPE RESIDUALS")
    print(f"{'=' * 70}")
    for threshold in THRESHOLDS:
        vec_list = [action_residuals[i] for i in range(len(action_residuals))]
        clusters = cluster_centroid(vec_list, threshold)
        sizes = sorted([len(c) for c in clusters], reverse=True)
        non_sing = sum(1 for s in sizes if s > 1)
        print(
            f"  threshold={threshold:.2f}: {len(clusters)} clusters "
            f"({non_sing} non-singleton) top={sizes[:10]}"
        )


if __name__ == "__main__":
    main()
