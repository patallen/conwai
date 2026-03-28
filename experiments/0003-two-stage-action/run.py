"""
Experiment 0003: Two-stage clustering — bucket by action type, then sub-cluster.

Hypothesis: Within each action type (forage, inspect, bake, etc.), the reasoning
may reveal distinct behavioral sub-patterns that are masked when all types are
mixed together.

Usage:
    PYTHONPATH=. uv run python experiments/0003-two-stage-action/run.py
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
    reasoning = " ".join(line.strip() for line in lines[1:] if line.strip()) or lines[0]
    return action, reasoning


def pairwise_stats(vectors: np.ndarray) -> dict:
    if len(vectors) < 2:
        return {"n": len(vectors), "min": 0, "max": 0, "mean": 0, "std": 0}
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sim = (vectors / norms) @ (vectors / norms).T
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {
        "n": len(vectors),
        "min": float(np.min(upper)),
        "max": float(np.max(upper)),
        "mean": float(np.mean(upper)),
        "std": float(np.std(upper)),
        "median": float(np.median(upper)),
    }


def cluster_centroid(vectors: list[np.ndarray], threshold: float) -> list[list[int]]:
    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []
    for idx, vec in enumerate(vectors):
        best_ci, best_sim = -1, -1.0
        for ci, c in enumerate(centroids):
            sim = float(
                np.dot(vec, c) / (np.linalg.norm(vec) * np.linalg.norm(c) + 1e-10)
            )
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

    # Parse all entries
    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning})

    # Group by action type
    buckets: dict[str, list[tuple[int, str]]] = {}
    for i, p in enumerate(parsed):
        buckets.setdefault(p["action"], []).append((i, p["reasoning"]))

    print("Action type distribution:")
    for action, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
        print(f"  {action:20s} {len(items):4d}")
    print()

    # Embed ALL reasoning texts at once (more efficient)
    print("Embedding all reasoning texts...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    all_reasoning = [p["reasoning"] for p in parsed]
    all_vecs = embedder.embed(all_reasoning)
    vectors = np.array(all_vecs)
    print(f"Shape: {vectors.shape}\n")

    # Analyze each action type bucket
    for action, items in sorted(buckets.items(), key=lambda x: -len(x[1])):
        indices = [idx for idx, _ in items]
        bucket_vecs = vectors[indices]

        print(f"{'=' * 70}")
        print(f"ACTION: {action} ({len(items)} entries)")
        print(f"{'=' * 70}")

        stats = pairwise_stats(bucket_vecs)
        if stats["n"] >= 2:
            print(
                f"  Pairwise sim: mean={stats['mean']:.4f} std={stats['std']:.4f} "
                f"min={stats['min']:.4f} max={stats['max']:.4f}"
            )

        # Try clustering at multiple thresholds
        for threshold in [0.80, 0.85, 0.90]:
            local_vecs = [vectors[idx] for idx in indices]
            clusters = cluster_centroid(local_vecs, threshold)
            sizes = sorted([len(c) for c in clusters], reverse=True)
            n_clusters = len(clusters)
            n_singleton = sum(1 for s in sizes if s == 1)
            print(
                f"  threshold={threshold:.2f}: {n_clusters} clusters "
                f"(singletons={n_singleton}) sizes={sizes[:10]}{'...' if len(sizes) > 10 else ''}"
            )

        # Show samples from sub-clusters at best threshold
        best_threshold = 0.85
        local_vecs = [vectors[idx] for idx in indices]
        clusters = cluster_centroid(local_vecs, best_threshold)
        clusters_sorted = sorted(clusters, key=lambda c: -len(c))

        if len(clusters_sorted) > 1:
            print(f"\n  Sub-clusters at {best_threshold} (top 5):")
            for ci, cluster in enumerate(clusters_sorted[:5]):
                print(f"    Cluster {ci + 1} (size={len(cluster)}):")
                for local_idx in cluster[:2]:
                    global_idx = indices[local_idx]
                    print(
                        f"      [{global_idx:3d}] {parsed[global_idx]['reasoning'][:130]}"
                    )
        print()


if __name__ == "__main__":
    main()
