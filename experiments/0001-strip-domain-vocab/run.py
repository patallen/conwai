"""
Experiment 0001: Strip domain vocabulary before embedding.

Hypothesis: removing resource-specific words forces the embedding model to cluster
on intent/action patterns rather than shared topic vocabulary.

Usage:
    PYTHONPATH=. uv run python experiments/0001-strip-domain-vocab/run.py
"""

import re
from pathlib import Path

import numpy as np

from conwai.embeddings import FastEmbedder
from conwai.storage import SQLiteStorage


DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"
CLUSTER_THRESHOLD = 0.70
SAMPLES_PER_CLUSTER = 3

DOMAIN_WORDS = {
    "flour", "water", "bread", "loaf", "loaves",
    "coin", "coins",
    "forage", "foraged", "foraging",
    "bake", "baked", "baking",
    "trade", "traded", "trading",
    "hunger", "hungry", "starving", "starve",
    "resources", "surplus", "deficit", "inventory",
    "consume", "consumed",
}

_STRIP_PATTERN = re.compile(
    r"\b(?:" + "|".join(re.escape(w) for w in DOMAIN_WORDS) + r")\b",
    re.IGNORECASE,
)
_NUMBER_PATTERN = re.compile(r"\b\d+\b")


def extract_reasoning(content: str) -> str:
    """Skip the first line (timestamp + action results), return the rest joined."""
    lines = content.strip().split("\n")
    reasoning_lines = [l.strip() for l in lines[1:] if l.strip()]
    if reasoning_lines:
        return " ".join(reasoning_lines)
    return content


def strip_domain(text: str) -> str:
    """Remove domain vocabulary and numbers, then collapse whitespace."""
    text = _STRIP_PATTERN.sub(" ", text)
    text = _NUMBER_PATTERN.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    denom = np.linalg.norm(a) * np.linalg.norm(b) + 1e-10
    return float(np.dot(a, b) / denom)


def cluster_incremental(
    vectors: list[np.ndarray],
    threshold: float,
) -> list[list[int]]:
    """
    Greedy incremental clustering identical in spirit to consolidation_real.py.

    Each vector is assigned to the first existing cluster whose centroid is
    within `threshold` cosine similarity. If no cluster matches, a new one
    is started.
    """
    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []

    for idx, vec in enumerate(vectors):
        best_cluster = -1
        best_sim = -1.0
        for ci, centroid in enumerate(centroids):
            sim = cosine(vec, centroid)
            if sim > best_sim:
                best_sim = sim
                best_cluster = ci

        if best_cluster >= 0 and best_sim >= threshold:
            clusters[best_cluster].append(idx)
            # Update centroid as running mean
            n = len(clusters[best_cluster])
            centroids[best_cluster] = centroids[best_cluster] * ((n - 1) / n) + vec * (1 / n)
        else:
            clusters.append([idx])
            centroids.append(vec.copy())

    return clusters


def main() -> None:
    print(f"DB: {DB_PATH}  Agent: {AGENT}")
    print(f"Cluster threshold: {CLUSTER_THRESHOLD}")
    print(f"Domain words stripped: {len(DOMAIN_WORDS)}\n")

    storage = SQLiteStorage(path=Path(DB_PATH))
    brain_data = storage.load_component(AGENT, "brain")
    if not brain_data:
        print(f"No brain data for {AGENT}")
        return

    diary = brain_data.get("diary", [])
    raw_entries = [e["content"] for e in diary]
    print(f"Diary entries: {len(raw_entries)}\n")

    # Extract reasoning and strip domain vocab
    originals: list[str] = []   # original reasoning (for display)
    stripped: list[str] = []    # stripped text (for embedding)

    for entry in raw_entries:
        reasoning = extract_reasoning(entry)
        originals.append(reasoning)
        stripped.append(strip_domain(reasoning))

    # Show what stripping does on a few samples
    print("Sample stripping (first 3 entries):")
    for i in range(min(3, len(originals))):
        print(f"  [{i}] ORIGINAL : {originals[i][:120]}")
        print(f"      STRIPPED : {stripped[i][:120]}")
    print()

    # Embed the stripped texts
    print("Embedding stripped texts...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    raw_vecs = embedder.embed(stripped)
    vectors = [np.array(v) for v in raw_vecs]
    print(f"Embedded {len(vectors)} vectors (dim={len(raw_vecs[0])})\n")

    # Cluster
    print("Clustering...")
    clusters = cluster_incremental(vectors, CLUSTER_THRESHOLD)
    clusters_sorted = sorted(clusters, key=lambda c: -len(c))

    print(f"\n{'='*70}")
    print(f"RESULTS: {len(clusters)} clusters from {len(vectors)} entries")
    print(f"{'='*70}\n")

    for ci, cluster in enumerate(clusters_sorted):
        print(f"Cluster {ci + 1}  (size={len(cluster)})")
        samples = cluster[:SAMPLES_PER_CLUSTER]
        for entry_idx in samples:
            text = originals[entry_idx]
            print(f"  [{entry_idx:3d}] {text[:160]}")
        if len(cluster) > SAMPLES_PER_CLUSTER:
            print(f"  ... and {len(cluster) - SAMPLES_PER_CLUSTER} more entries")
        print()

    # Summary statistics
    sizes = [len(c) for c in clusters]
    print(f"{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"  Total entries   : {len(vectors)}")
    print(f"  Total clusters  : {len(clusters)}")
    print(f"  Largest cluster : {max(sizes)}")
    print(f"  Smallest cluster: {min(sizes)}")
    print(f"  Mean size       : {np.mean(sizes):.1f}")
    print(f"  Median size     : {np.median(sizes):.1f}")
    singleton_count = sum(1 for s in sizes if s == 1)
    print(f"  Singletons      : {singleton_count}")
    print(f"  Non-singletons  : {len(clusters) - singleton_count}")

    size_dist: dict[int, int] = {}
    for s in sizes:
        size_dist[s] = size_dist.get(s, 0) + 1
    print("\n  Size distribution:")
    for size in sorted(size_dist):
        print(f"    size {size:3d}: {size_dist[size]} cluster(s)")


if __name__ == "__main__":
    main()
