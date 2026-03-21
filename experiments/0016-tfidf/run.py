"""
Experiment 0016: TF-IDF vectors (numpy implementation, no sklearn).

TF-IDF naturally de-emphasizes shared vocabulary via the IDF term.
Words that appear in every entry (flour, water, bread) get low IDF.
Distinctive words get high IDF. This might separate entries better
than dense embeddings.

Usage:
    PYTHONPATH=. uv run python experiments/0016-tfidf/run.py
"""

import math
import re
from collections import Counter
from pathlib import Path

import numpy as np

from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"

_ACTION_RE = re.compile(r"\] (\w+)→")
_WORD_RE = re.compile(r"[a-z]+")


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def build_tfidf(documents: list[str]) -> tuple[np.ndarray, list[str]]:
    """Build TF-IDF matrix from documents. Returns (matrix, vocab)."""
    # Build vocabulary
    doc_tokens = [tokenize(doc) for doc in documents]
    all_words: set[str] = set()
    for tokens in doc_tokens:
        all_words.update(tokens)
    vocab = sorted(all_words)
    word_to_idx = {w: i for i, w in enumerate(vocab)}

    n_docs = len(documents)
    n_vocab = len(vocab)

    # Document frequency
    df = np.zeros(n_vocab)
    for tokens in doc_tokens:
        seen = set(tokens)
        for w in seen:
            df[word_to_idx[w]] += 1

    # IDF: log(N / df) + 1, with smoothing
    idf = np.log((n_docs + 1) / (df + 1)) + 1

    # TF-IDF matrix
    matrix = np.zeros((n_docs, n_vocab))
    for di, tokens in enumerate(doc_tokens):
        counts = Counter(tokens)
        total = len(tokens) if tokens else 1
        for word, count in counts.items():
            wi = word_to_idx[word]
            tf = count / total  # normalized TF
            matrix[di, wi] = tf * idf[wi]

    # L2 normalize rows
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms

    return matrix, vocab


def pairwise_stats(vectors: np.ndarray) -> dict:
    sim = vectors @ vectors.T
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {
        "mean": float(np.mean(upper)), "std": float(np.std(upper)),
        "min": float(np.min(upper)), "max": float(np.max(upper)),
    }


def kmeans_cosine(vectors: np.ndarray, k: int, max_iter: int = 100, seed: int = 42) -> np.ndarray:
    rng = np.random.RandomState(seed)
    n = len(vectors)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = vectors / norms

    indices = rng.choice(n, k, replace=False)
    centroids = normed[indices].copy()

    for _ in range(max_iter):
        sims = normed @ centroids.T
        labels = sims.argmax(axis=1)
        new_centroids = np.zeros_like(centroids)
        for ki in range(k):
            mask = labels == ki
            if mask.sum() > 0:
                c = normed[mask].mean(axis=0)
                norm = np.linalg.norm(c)
                new_centroids[ki] = c / norm if norm > 0 else c
        if np.allclose(centroids, new_centroids, atol=1e-6):
            break
        centroids = new_centroids
    return labels


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
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries\n")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning})

    documents = [p["reasoning"] for p in parsed]

    # Build TF-IDF
    print("Building TF-IDF matrix...")
    tfidf_matrix, vocab = build_tfidf(documents)
    print(f"Shape: {tfidf_matrix.shape} (entries x vocab)")

    # Show top IDF words (most distinctive)
    doc_tokens = [tokenize(doc) for doc in documents]
    df = np.zeros(len(vocab))
    for tokens in doc_tokens:
        seen = set(tokens)
        for w in seen:
            df[vocab.index(w)] += 1
    idf = np.log((len(documents) + 1) / (df + 1)) + 1

    print(f"\nTop 20 highest-IDF words (most distinctive):")
    top_idf = np.argsort(idf)[::-1][:20]
    for i in top_idf:
        print(f"  {vocab[i]:20s} IDF={idf[i]:.3f} (in {int(df[i])} docs)")

    print(f"\nTop 20 lowest-IDF words (most common):")
    low_idf = np.argsort(idf)[:20]
    for i in low_idf:
        print(f"  {vocab[i]:20s} IDF={idf[i]:.3f} (in {int(df[i])} docs)")

    # Pairwise stats
    stats = pairwise_stats(tfidf_matrix)
    print(f"\nTF-IDF pairwise similarity:")
    print(f"  mean={stats['mean']:.4f} std={stats['std']:.4f} "
          f"range=[{stats['min']:.4f}, {stats['max']:.4f}]")
    print(f"  (Compare: bge-large mean=0.7972 std=0.0745)")
    print()

    # Threshold-based clustering
    print(f"{'='*70}")
    print("THRESHOLD CLUSTERING ON TF-IDF")
    print(f"{'='*70}")
    for threshold in [0.05, 0.10, 0.15, 0.20, 0.30, 0.40]:
        clusters = cluster_centroid(tfidf_matrix, threshold)
        sizes = sorted([len(c) for c in clusters], reverse=True)
        non_sing = sum(1 for s in sizes if s > 1)
        print(f"  threshold={threshold:.2f}: {len(clusters)} clusters "
              f"({non_sing} non-singleton) top={sizes[:10]}")

    # K-means on TF-IDF
    print(f"\n{'='*70}")
    print("K-MEANS ON TF-IDF")
    print(f"{'='*70}")
    for k in [5, 8, 10, 15]:
        labels = kmeans_cosine(tfidf_matrix, k)
        sizes = sorted([int((labels == ki).sum()) for ki in range(k)], reverse=True)
        print(f"\n  K={k}: sizes={sizes}")
        if k <= 10:
            for ki in range(k):
                mask = labels == ki
                indices = np.where(mask)[0]
                action_counts: dict[str, int] = {}
                for idx in indices:
                    a = parsed[idx]["action"]
                    action_counts[a] = action_counts.get(a, 0) + 1
                top = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
                action_str = ", ".join(f"{a}:{c}" for a, c in top)
                print(f"    Cluster {ki}: {int(mask.sum()):3d} [{action_str}]")
                for idx in indices[:2]:
                    print(f"      [{idx:3d}] {parsed[idx]['reasoning'][:100]}")


if __name__ == "__main__":
    main()
