"""
Experiment 0002: Prefix action type to reasoning before embedding.

Hypothesis: Adding the action type as a discriminative prefix will help the
embedding model separate entries by what the agent DID, not just what it
thought about.

Usage:
    PYTHONPATH=. uv run python experiments/0002-action-type-prefix/run.py
"""

import re
from pathlib import Path

import numpy as np

from conwai.llm import FastEmbedder
from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"
THRESHOLDS = [0.70, 0.75, 0.80, 0.85]

_ACTION_RE = re.compile(r"\] (\w+)→")


def parse_entry(content: str) -> tuple[str, str]:
    """Return (action_type, reasoning) from a diary entry."""
    lines = content.strip().split("\n")
    first_line = lines[0]
    m = _ACTION_RE.search(first_line)
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(line.strip() for line in lines[1:] if line.strip()) or first_line
    return action, reasoning


def cluster_centroid(vectors: list[np.ndarray], threshold: float) -> list[list[int]]:
    """Greedy centroid-based clustering."""
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
    print(f"Loaded {len(diary)} diary entries\n")

    entries = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        prefixed = f"{action}: {reasoning}"
        entries.append({"action": action, "reasoning": reasoning, "prefixed": prefixed})

    # Show sample prefixed texts
    print("Sample prefixed texts:")
    for i in range(min(5, len(entries))):
        print(f"  [{i}] {entries[i]['prefixed'][:140]}")
    print()

    # Embed prefixed texts
    print("Embedding prefixed texts...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    texts = [e["prefixed"] for e in entries]
    raw_vecs = embedder.embed(texts)
    vectors = [np.array(v) for v in raw_vecs]
    print(f"Embedded {len(vectors)} vectors\n")

    # Cluster at each threshold
    for threshold in THRESHOLDS:
        clusters = cluster_centroid(vectors, threshold)
        clusters_sorted = sorted(clusters, key=lambda c: -len(c))
        sizes = [len(c) for c in clusters_sorted]

        print(f"{'=' * 70}")
        print(f"THRESHOLD {threshold:.2f}: {len(clusters)} clusters")
        print(f"{'=' * 70}")
        print(f"  Size distribution: {sizes[:20]}{'...' if len(sizes) > 20 else ''}")

        # For each cluster, show action type breakdown and samples
        for ci, cluster in enumerate(clusters_sorted[:15]):
            action_counts: dict[str, int] = {}
            for idx in cluster:
                a = entries[idx]["action"]
                action_counts[a] = action_counts.get(a, 0) + 1
            action_str = ", ".join(
                f"{k}:{v}"
                for k, v in sorted(action_counts.items(), key=lambda x: -x[1])
            )
            print(f"\n  Cluster {ci + 1} (size={len(cluster)}): [{action_str}]")
            for idx in cluster[:3]:
                print(f"    [{idx:3d}] {entries[idx]['prefixed'][:150]}")
            if len(cluster) > 3:
                print(f"    ... and {len(cluster) - 3} more")
        print()


if __name__ == "__main__":
    main()
