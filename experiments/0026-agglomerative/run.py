"""
Experiment 0026: Agglomerative (hierarchical) clustering.

Build a dendrogram from bottom up — reveals hierarchical structure
that flat K-means misses. We can see at what distance level distinct
groups form, and whether there's a natural number of clusters.

Implemented in numpy (no sklearn).

Usage:
    PYTHONPATH=. uv run python experiments/0026-agglomerative/run.py
"""

import re
from collections import Counter
from pathlib import Path

import numpy as np

from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"

_ACTION_RE = re.compile(r"\] (\w+)→")
_WORD_RE = re.compile(r"[a-z]+")

STOPWORDS = {
    "i",
    "me",
    "my",
    "myself",
    "we",
    "our",
    "you",
    "your",
    "he",
    "him",
    "his",
    "she",
    "her",
    "it",
    "its",
    "they",
    "them",
    "their",
    "am",
    "is",
    "are",
    "was",
    "were",
    "be",
    "been",
    "being",
    "have",
    "has",
    "had",
    "having",
    "do",
    "does",
    "did",
    "a",
    "an",
    "the",
    "and",
    "but",
    "if",
    "or",
    "because",
    "as",
    "while",
    "of",
    "at",
    "by",
    "for",
    "with",
    "about",
    "to",
    "from",
    "in",
    "out",
    "on",
    "off",
    "over",
    "under",
    "then",
    "here",
    "there",
    "when",
    "where",
    "how",
    "all",
    "both",
    "each",
    "more",
    "most",
    "other",
    "some",
    "no",
    "not",
    "only",
    "so",
    "than",
    "too",
    "very",
    "can",
    "will",
    "just",
    "should",
    "now",
}


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(line.strip() for line in lines[1:] if line.strip()) or lines[0]
    return action, reasoning


def tokenize_filtered(text: str) -> list[str]:
    words = _WORD_RE.findall(text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def build_tfidf(documents: list[str]) -> np.ndarray:
    doc_tokens = [tokenize_filtered(doc) for doc in documents]
    all_words: set[str] = set()
    for tokens in doc_tokens:
        all_words.update(tokens)
    vocab = sorted(all_words)
    word_to_idx = {w: i for i, w in enumerate(vocab)}
    n_docs = len(documents)
    n_vocab = len(vocab)
    df = np.zeros(n_vocab)
    for tokens in doc_tokens:
        for w in set(tokens):
            df[word_to_idx[w]] += 1
    idf = np.log((n_docs + 1) / (df + 1)) + 1
    matrix = np.zeros((n_docs, n_vocab))
    for di, tokens in enumerate(doc_tokens):
        counts = Counter(tokens)
        total = len(tokens) if tokens else 1
        for word, count in counts.items():
            wi = word_to_idx[word]
            matrix[di, wi] = (count / total) * idf[wi]
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return matrix / norms


def agglomerative_clustering(
    dist_matrix: np.ndarray,
) -> list[tuple[int, int, float, int]]:
    """
    Single-linkage agglomerative clustering.
    Returns merge history: [(cluster_a, cluster_b, distance, new_size), ...]
    """
    n = len(dist_matrix)
    # Track which cluster each point belongs to
    list(range(n))
    cluster_sizes = {i: 1 for i in range(n)}
    active = set(range(n))

    # Work with a mutable distance matrix
    dists = dist_matrix.copy()
    np.fill_diagonal(dists, np.inf)

    merges = []

    while len(active) > 1:
        # Find closest pair among active clusters
        min_dist = np.inf
        min_i, min_j = -1, -1
        active_list = sorted(active)
        for ai, i in enumerate(active_list):
            for j in active_list[ai + 1 :]:
                if dists[i, j] < min_dist:
                    min_dist = dists[i, j]
                    min_i, min_j = i, j

        if min_i < 0:
            break

        new_size = cluster_sizes[min_i] + cluster_sizes[min_j]
        merges.append((min_i, min_j, min_dist, new_size))

        # Update distances (single linkage: min of distances)
        for k in active:
            if k != min_i and k != min_j:
                new_dist = min(dists[min_i, k], dists[min_j, k])
                dists[min_i, k] = new_dist
                dists[k, min_i] = new_dist

        active.remove(min_j)
        cluster_sizes[min_i] = new_size

        # Mark merged cluster distances as inf
        for k in range(len(dists)):
            dists[min_j, k] = np.inf
            dists[k, min_j] = np.inf

    return merges


def cut_dendrogram(
    merges: list[tuple[int, int, float, int]], n: int, n_clusters: int
) -> np.ndarray:
    """Cut dendrogram to get n_clusters clusters."""
    labels = np.arange(n)
    for i, (a, b, dist, size) in enumerate(merges):
        if n - i <= n_clusters:
            break
        # Merge b into a
        labels[labels == b] if b < n else b
        # Find all points in cluster b and reassign to a
        labels[labels == b] = a
    # Renumber
    unique = np.unique(labels)
    mapping = {old: new for new, old in enumerate(unique)}
    return np.array([mapping[line] for line in labels])


def main() -> None:
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries\n")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning})

    # Use TF-IDF (no stopwords) as the representation
    documents = [p["reasoning"] for p in parsed]
    tfidf = build_tfidf(documents)
    print(f"TF-IDF shape: {tfidf.shape}")

    # Compute cosine distance matrix
    sim = tfidf @ tfidf.T
    dist = 1 - sim
    np.fill_diagonal(dist, 0)
    print("Distance matrix computed\n")

    # Run agglomerative clustering (only on first 100 entries for speed)
    subset_n = min(100, len(parsed))
    print(f"Running agglomerative clustering on first {subset_n} entries...")
    merges = agglomerative_clustering(dist[:subset_n, :subset_n])

    # Show merge distances
    print("\nMerge distance progression (every 10th merge):")
    for i in range(0, len(merges), 10):
        _, _, d, s = merges[i]
        remaining = subset_n - i
        print(
            f"  Step {i:3d}: distance={d:.4f} merged_size={s} clusters_remaining={remaining}"
        )

    # Find natural number of clusters (biggest gap in merge distances)
    distances = [m[2] for m in merges]
    gaps = [distances[i + 1] - distances[i] for i in range(len(distances) - 1)]

    # Top 5 biggest gaps
    if gaps:
        top_gaps = sorted(enumerate(gaps), key=lambda x: -x[1])[:5]
        print("\nLargest gaps in merge distances (potential natural cluster counts):")
        for gap_idx, gap_size in top_gaps:
            n_clusters = subset_n - gap_idx - 1
            print(
                f"  After step {gap_idx}: gap={gap_size:.4f} → suggests {n_clusters} clusters"
            )

    # Show clusters at a few cut points on FULL data using K-means
    # (agglomerative is too slow for 251 entries)
    print(f"\n{'=' * 70}")
    print("K-MEANS ON TF-IDF (FULL DATA, FOR COMPARISON)")
    print(f"{'=' * 70}")

    def kmeans(vecs, k, seed=42):
        rng = np.random.RandomState(seed)
        n = len(vecs)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        normed = vecs / norms
        indices = rng.choice(n, k, replace=False)
        centroids = normed[indices].copy()
        for _ in range(100):
            sims = normed @ centroids.T
            labels = sims.argmax(axis=1)
            new_c = np.zeros_like(centroids)
            for ki in range(k):
                mask = labels == ki
                if mask.sum() > 0:
                    c = normed[mask].mean(axis=0)
                    norm = np.linalg.norm(c)
                    new_c[ki] = c / norm if norm > 0 else c
            if np.allclose(centroids, new_c, atol=1e-6):
                break
            centroids = new_c
        return labels

    for k in [5, 8, 10, 15]:
        labels = kmeans(tfidf, k)
        sizes = sorted([int((labels == ki).sum()) for ki in range(k)], reverse=True)
        print(f"  K={k}: sizes={sizes}")


if __name__ == "__main__":
    main()
