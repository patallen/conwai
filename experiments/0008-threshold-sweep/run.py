"""
Experiment 0008: Threshold sweep to find sub-structure in the Helen mega-cluster.

Hypothesis: At threshold 0.70 everything collapses into one cluster.
Higher thresholds should reveal internal structure.

Usage:
    PYTHONPATH=. uv run python experiments/0008-threshold-sweep/run.py
"""

from pathlib import Path

import numpy as np

from conwai.embeddings import FastEmbedder
from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"
MODEL = "BAAI/bge-large-en-v1.5"
MAX_CLUSTER_SIZE = 5
THRESHOLDS = [0.70, 0.75, 0.80, 0.85, 0.90, 0.95]


def extract_reasoning(entry: str) -> str:
    """Pull out just the reasoning portion — skip the first timestamp+action line."""
    lines = entry.strip().split("\n")
    reasoning_lines = [line.strip() for line in lines[1:] if line.strip()]
    if reasoning_lines:
        return " ".join(reasoning_lines)
    return entry


def cluster_at_threshold(
    vectors: np.ndarray,
    threshold: float,
    max_cluster_size: int = MAX_CLUSTER_SIZE,
) -> list[list[int]]:
    """
    Greedy clique-based clustering identical to consolidation_real.py logic.

    For each new entry (in order), find neighbors above threshold, build the
    tightest clique (all pairs above threshold), cap at max_cluster_size.
    An entry can appear in multiple clusters (not visited/consumed), which
    matches the original design — we want raw cluster formations, not a
    hard partition.
    """
    n = len(vectors)
    # Precompute full similarity matrix
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = vectors / norms
    sim_matrix = normalized @ normalized.T

    clusters: list[list[int]] = []

    for idx in range(n):
        # Find neighbors above threshold (excluding self)
        neighbor_sims = [
            (j, float(sim_matrix[idx, j]))
            for j in range(n)
            if j != idx and sim_matrix[idx, j] > threshold
        ]
        if not neighbor_sims:
            continue

        # Sort by descending similarity, take top (max_cluster_size - 1)
        neighbor_sims.sort(key=lambda x: -x[1])
        candidates = neighbor_sims[: max_cluster_size - 1]

        # Build tightest clique: start with [idx, best_neighbor]
        cluster = [idx, candidates[0][0]]
        for other_idx, _ in candidates[1:]:
            if len(cluster) >= max_cluster_size:
                break
            if all(sim_matrix[other_idx, c] > threshold for c in cluster):
                cluster.append(other_idx)

        if len(cluster) >= 2:
            clusters.append(cluster)

    return clusters


def summarize_clusters(clusters: list[list[int]], n_entries: int) -> dict:
    """Compute cluster statistics."""
    if not clusters:
        return {
            "num_clusters": 0,
            "sizes": [],
            "clustered_entries": 0,
            "unclustered": n_entries,
        }

    all_clustered = set()
    for c in clusters:
        all_clustered.update(c)

    sizes = sorted([len(c) for c in clusters], reverse=True)
    return {
        "num_clusters": len(clusters),
        "sizes": sizes,
        "clustered_entries": len(all_clustered),
        "unclustered": n_entries - len(all_clustered),
    }


def pairwise_stats(vectors: np.ndarray) -> dict:
    """Compute distribution of all pairwise cosine similarities."""
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normalized = vectors / norms
    sim_matrix = normalized @ normalized.T

    n = len(vectors)
    # Upper triangle only (exclude diagonal)
    upper_indices = np.triu_indices(n, k=1)
    pairwise = sim_matrix[upper_indices]

    return {
        "min": float(np.min(pairwise)),
        "max": float(np.max(pairwise)),
        "mean": float(np.mean(pairwise)),
        "median": float(np.median(pairwise)),
        "std": float(np.std(pairwise)),
        "p25": float(np.percentile(pairwise, 25)),
        "p75": float(np.percentile(pairwise, 75)),
        "p90": float(np.percentile(pairwise, 90)),
        "p95": float(np.percentile(pairwise, 95)),
        "n_pairs": len(pairwise),
    }


def find_interesting_threshold(
    results: dict[float, dict],
) -> float | None:
    """Return the threshold where distinct clusters appear (3-15 clusters)."""
    for threshold in sorted(results.keys()):
        n = results[threshold]["num_clusters"]
        if 3 <= n <= 15:
            return threshold
    return None


def main() -> None:
    print(f"DB: {DB_PATH}  Agent: {AGENT}")
    print(f"Model: {MODEL}\n")

    storage = SQLiteStorage(path=Path(DB_PATH))
    brain_data = storage.load_component(AGENT, "brain")
    if not brain_data:
        print(f"No brain data found for agent '{AGENT}'")
        return

    diary = brain_data.get("diary", [])
    raw_entries = [e["content"] for e in diary]
    print(f"Loaded {len(raw_entries)} diary entries\n")

    # Extract reasoning from all entries
    reasoning_texts = [extract_reasoning(e) for e in raw_entries]

    # Show sample extraction
    print("Sample reasoning extraction (first 3 entries):")
    for i in range(min(3, len(raw_entries))):
        full_preview = raw_entries[i][:80].replace("\n", " | ")
        reasoning_preview = reasoning_texts[i][:80]
        print(f"  [{i:3d}] FULL:      {full_preview}")
        print(f"        REASONING: {reasoning_preview}")
    print()

    # Embed ALL entries once
    print(f"Embedding {len(reasoning_texts)} reasoning texts with {MODEL}...")
    embedder = FastEmbedder(model_name=MODEL)
    raw_vectors = embedder.embed(reasoning_texts)
    vectors = np.array(raw_vectors)
    print(f"Embedding complete. Shape: {vectors.shape}\n")

    # Pairwise similarity distribution
    print("=" * 70)
    print("PAIRWISE SIMILARITY DISTRIBUTION")
    print("=" * 70)
    stats = pairwise_stats(vectors)
    print(f"  Pairs analysed : {stats['n_pairs']:,}")
    print(f"  Min            : {stats['min']:.4f}")
    print(f"  Max            : {stats['max']:.4f}")
    print(f"  Mean           : {stats['mean']:.4f}")
    print(f"  Median         : {stats['median']:.4f}")
    print(f"  Std dev        : {stats['std']:.4f}")
    print(f"  25th pct       : {stats['p25']:.4f}")
    print(f"  75th pct       : {stats['p75']:.4f}")
    print(f"  90th pct       : {stats['p90']:.4f}")
    print(f"  95th pct       : {stats['p95']:.4f}")
    print()

    # Threshold sweep
    print("=" * 70)
    print("THRESHOLD SWEEP")
    print("=" * 70)

    sweep_results: dict[float, dict] = {}
    all_clusters_by_threshold: dict[float, list[list[int]]] = {}

    for threshold in THRESHOLDS:
        clusters = cluster_at_threshold(vectors, threshold)
        summary = summarize_clusters(clusters, len(raw_entries))
        sweep_results[threshold] = summary
        all_clusters_by_threshold[threshold] = clusters

        sizes_str = str(summary["sizes"][:20])
        if len(summary["sizes"]) > 20:
            sizes_str = sizes_str[:-1] + ", ...]"
        print(
            f"  threshold={threshold:.2f}  "
            f"clusters={summary['num_clusters']:4d}  "
            f"clustered={summary['clustered_entries']:4d}/{len(raw_entries)}  "
            f"unclustered={summary['unclustered']:4d}  "
            f"sizes(top20)={sizes_str}"
        )

    print()

    # Find the most interesting threshold
    interesting = find_interesting_threshold(sweep_results)

    # If no threshold hits 3-15, find the first with > 1 cluster
    if interesting is None:
        for threshold in sorted(sweep_results.keys(), reverse=True):
            if sweep_results[threshold]["num_clusters"] > 1:
                interesting = threshold
                break

    if interesting is None:
        print(
            "No threshold produced multiple clusters. Embedding space may be too uniform."
        )
        return

    print("=" * 70)
    print(f"DETAILED VIEW AT THRESHOLD {interesting:.2f}")
    print(
        f"  ({sweep_results[interesting]['num_clusters']} clusters, "
        f"{sweep_results[interesting]['unclustered']} unclustered entries)"
    )
    print("=" * 70)
    print()

    clusters = all_clusters_by_threshold[interesting]

    # Sort clusters by size descending, then by first entry index
    clusters_sorted = sorted(clusters, key=lambda c: (-len(c), c[0]))

    for ci, cluster in enumerate(clusters_sorted):
        size = len(cluster)
        print(f"Cluster {ci + 1:3d}  (size={size}, entry indices={cluster})")

        # Print 2 sample reasoning texts
        samples = cluster[:2]
        for entry_idx in samples:
            text = reasoning_texts[entry_idx]
            # Wrap at 90 chars
            if len(text) > 200:
                text = text[:197] + "..."
            print(f"  [{entry_idx:3d}] {text}")
        print()

    # Size distribution at interesting threshold
    print("-" * 70)
    sizes = sweep_results[interesting]["sizes"]
    size_counts: dict[int, int] = {}
    for s in sizes:
        size_counts[s] = size_counts.get(s, 0) + 1
    print("Cluster size distribution:")
    for size in sorted(size_counts.keys(), reverse=True):
        bar = "#" * size_counts[size]
        print(f"  size={size}: {size_counts[size]:4d} clusters  {bar}")
    print()


if __name__ == "__main__":
    main()
