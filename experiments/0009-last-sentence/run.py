"""
Experiment 0009: Embed only the last sentence of reasoning.

Hypothesis: The last sentence of each reasoning block is typically the
decision/conclusion ("I should trade", "I need to be cautious", "this agent
is unreliable"). These conclusions may be more semantically distinct than the
full reasoning text, which is dominated by resource vocabulary.

Usage:
    PYTHONPATH=. uv run python experiments/0009-last-sentence/run.py
"""

from pathlib import Path

import numpy as np

from conwai.embeddings import FastEmbedder
from conwai.storage import SQLiteStorage

THRESHOLDS = [0.70, 0.75, 0.80]
MAX_CLUSTER_SIZE = 5
SAMPLES_PER_CLUSTER = 3


def extract_reasoning(entry: str) -> str:
    """Pull out just the reasoning lines (skip first timestamp+action line)."""
    lines = entry.strip().split("\n")
    parts = [line.strip() for line in lines[1:] if line.strip()]
    if parts:
        return " ".join(parts)
    return entry.strip()


def extract_last_sentence(reasoning: str) -> str:
    """Take only the last sentence of the reasoning block.

    Split on ". " or terminal "." and return the last non-empty segment.
    This targets the conclusion/decision that closes the reasoning.
    """
    # Split on ". " first (sentence boundary with space)
    segments = [s.strip() for s in reasoning.split(". ")]
    # Also handle trailing period: strip it from the last segment
    cleaned = []
    for seg in segments:
        seg = seg.rstrip(".")
        if seg:
            cleaned.append(seg)
    if not cleaned:
        return reasoning.strip()
    return cleaned[-1]


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def cluster_at_threshold(
    vectors: list[np.ndarray], threshold: float
) -> list[list[int]]:
    """Incremental clustering: for each entry, find neighbors above threshold,
    form tightest clique of size up to MAX_CLUSTER_SIZE.

    Returns list of clusters (each cluster is a list of entry indices).
    Entries that are never clustered are not included.
    """
    n = len(vectors)
    # Precompute all pairwise similarities
    sim_matrix = np.zeros((n, n))
    for i in range(n):
        for j in range(i + 1, n):
            s = cosine_sim(vectors[i], vectors[j])
            sim_matrix[i, j] = s
            sim_matrix[j, i] = s

    clusters: list[list[int]] = []
    assigned: set[int] = set()

    for idx in range(n):
        # Find all neighbors above threshold
        neighbors = [
            (j, sim_matrix[idx, j])
            for j in range(n)
            if j != idx and sim_matrix[idx, j] > threshold
        ]
        if not neighbors:
            continue

        neighbors.sort(key=lambda x: -x[1])

        # Build tightest clique starting with this entry and its best neighbor
        cluster = [idx, neighbors[0][0]]
        for other_idx, _ in neighbors[1:]:
            if len(cluster) >= MAX_CLUSTER_SIZE:
                break
            if all(sim_matrix[other_idx, c] > threshold for c in cluster):
                cluster.append(other_idx)

        if len(cluster) < 2:
            continue

        cluster_key = frozenset(cluster)
        # Avoid exact duplicate clusters
        if not any(frozenset(existing) == cluster_key for existing in clusters):
            clusters.append(sorted(cluster))
            assigned.update(cluster)

    return clusters


def report_clusters(
    clusters: list[list[int]],
    entries: list[str],
    last_sentences: list[str],
    threshold: float,
) -> None:
    print(f"\n{'=' * 70}")
    print(f"THRESHOLD {threshold:.2f}: {len(clusters)} clusters")
    print(f"{'=' * 70}")

    if not clusters:
        print("  (no clusters formed)")
        return

    # Sort by cluster size descending
    sorted_clusters = sorted(clusters, key=lambda c: -len(c))

    for ci, cluster in enumerate(sorted_clusters):
        print(f"\n  Cluster {ci + 1} (size={len(cluster)}):")
        print("  Last sentences in cluster:")
        for idx in cluster:
            print(f"    [{idx:3d}] {last_sentences[idx][:100]}")
        print("  Sample full entries:")
        for idx in cluster[:SAMPLES_PER_CLUSTER]:
            full = entries[idx].strip()
            # Indent for readability
            lines = full.split("\n")
            print(f"    [{idx:3d}] {lines[0][:80]}")
            for line in lines[1:]:
                if line.strip():
                    print(f"         {line.strip()[:80]}")


def main() -> None:
    db_path = Path("data.pre-abliterated.bak/state.db")
    agent = "Helen"

    print(f"Loading {agent} from {db_path}")
    storage = SQLiteStorage(path=db_path)
    brain_data = storage.load_component(agent, "brain")
    if not brain_data:
        print(f"No brain data found for {agent}")
        return

    diary = brain_data.get("diary", [])
    raw_entries = [e["content"] for e in diary]
    print(f"Diary: {len(raw_entries)} entries\n")

    # Extract reasoning, then last sentence from each
    reasonings = [extract_reasoning(e) for e in raw_entries]
    last_sentences = [extract_last_sentence(r) for r in reasonings]

    # Print 10 sample last sentences
    print("=" * 70)
    print("SAMPLE LAST SENTENCES (10 examples)")
    print("=" * 70)
    step = max(1, len(raw_entries) // 10)
    sample_indices = list(range(0, len(raw_entries), step))[:10]
    for i in sample_indices:
        print(f"\n  [{i:3d}] Full reasoning: {reasonings[i][:100]}")
        print(f"        Last sentence: {last_sentences[i]}")

    # Embed last sentences
    print(f"\n{'=' * 70}")
    print("EMBEDDING last sentences with BAAI/bge-large-en-v1.5 ...")
    print(f"{'=' * 70}")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    raw_vecs = embedder.embed(last_sentences)
    vectors = [np.array(v) for v in raw_vecs]
    print(f"Embedded {len(vectors)} vectors, dim={len(raw_vecs[0])}\n")

    # Cluster at each threshold and collect results
    results: dict[float, list[list[int]]] = {}
    for threshold in THRESHOLDS:
        clusters = cluster_at_threshold(vectors, threshold)
        results[threshold] = clusters
        print(f"Threshold {threshold:.2f}: {len(clusters)} clusters")

    # Detailed report at each threshold
    for threshold in THRESHOLDS:
        report_clusters(results[threshold], raw_entries, last_sentences, threshold)

    # Summary table
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    print(f"{'Threshold':>12}  {'Clusters':>10}  {'Avg size':>10}  {'Max size':>10}")
    for threshold in THRESHOLDS:
        clusters = results[threshold]
        if clusters:
            sizes = [len(c) for c in clusters]
            avg = sum(sizes) / len(sizes)
            mx = max(sizes)
        else:
            avg = mx = 0
        print(f"  {threshold:.2f}        {len(clusters):>10}  {avg:>10.1f}  {mx:>10d}")


if __name__ == "__main__":
    main()
