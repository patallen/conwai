"""
Experiment 0021: TF-IDF with bigrams.

"zero bread" and "surplus flour" are more distinctive than single words.
Bigrams capture phrases that distinguish behavioral contexts.

Usage:
    PYTHONPATH=. uv run python experiments/0021-tfidf-bigrams/run.py
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


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


def get_bigrams(tokens: list[str]) -> list[str]:
    return [f"{tokens[i]}_{tokens[i + 1]}" for i in range(len(tokens) - 1)]


def build_tfidf(
    documents: list[str], use_bigrams: bool = False
) -> tuple[np.ndarray, list[str]]:
    doc_tokens = [tokenize(doc) for doc in documents]
    if use_bigrams:
        doc_features = [tokenize(doc) + get_bigrams(tokenize(doc)) for doc in documents]
    else:
        doc_features = doc_tokens

    all_features: set[str] = set()
    for features in doc_features:
        all_features.update(features)
    vocab = sorted(all_features)
    word_to_idx = {w: i for i, w in enumerate(vocab)}

    n_docs = len(documents)
    n_vocab = len(vocab)
    df = np.zeros(n_vocab)
    for features in doc_features:
        seen = set(features)
        for w in seen:
            df[word_to_idx[w]] += 1

    idf = np.log((n_docs + 1) / (df + 1)) + 1

    matrix = np.zeros((n_docs, n_vocab))
    for di, features in enumerate(doc_features):
        counts = Counter(features)
        total = len(features) if features else 1
        for word, count in counts.items():
            wi = word_to_idx[word]
            matrix[di, wi] = (count / total) * idf[wi]

    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    matrix = matrix / norms

    return matrix, vocab


def pairwise_stats(vectors: np.ndarray) -> dict:
    sim = vectors @ vectors.T
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {"mean": float(np.mean(upper)), "std": float(np.std(upper))}


def kmeans_cosine(
    vectors: np.ndarray, k: int, max_iter: int = 100, seed: int = 42
) -> np.ndarray:
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

    # Compare unigram vs bigram TF-IDF
    for name, use_bi in [("unigram", False), ("unigram+bigram", True)]:
        matrix, vocab = build_tfidf(documents, use_bigrams=use_bi)
        stats = pairwise_stats(matrix)
        print(
            f"{name}: shape={matrix.shape} mean_sim={stats['mean']:.4f} std={stats['std']:.4f}"
        )

    # Focus on bigram version
    matrix, vocab = build_tfidf(documents, use_bigrams=True)

    # Show top bigrams by IDF
    bigram_vocab = [v for v in vocab if "_" in v]
    print(f"\nBigram vocab size: {len(bigram_vocab)}")

    # Find bigrams with interesting IDF (not too rare, not too common)
    doc_features = [set(tokenize(d) + get_bigrams(tokenize(d))) for d in documents]
    bigram_df: dict[str, int] = {}
    for features in doc_features:
        for f in features:
            if "_" in f:
                bigram_df[f] = bigram_df.get(f, 0) + 1

    # Bigrams in 5-50 documents (interesting range)
    interesting = [(bg, count) for bg, count in bigram_df.items() if 5 <= count <= 50]
    interesting.sort(key=lambda x: -x[1])
    print("\nInteresting bigrams (in 5-50 docs, top 30):")
    for bg, count in interesting[:30]:
        print(f"  {bg:30s} in {count:3d} docs")

    # K-means
    print(f"\n{'=' * 70}")
    print("K-MEANS ON BIGRAM TF-IDF")
    print(f"{'=' * 70}")
    for k in [8, 10, 15]:
        labels = kmeans_cosine(matrix, k)
        sizes = sorted([int((labels == ki).sum()) for ki in range(k)], reverse=True)
        print(f"\n  K={k}: sizes={sizes}")
        for ki in range(k):
            mask = labels == ki
            indices = np.where(mask)[0]
            action_counts: dict[str, int] = {}
            for idx in indices:
                action_counts[parsed[idx]["action"]] = (
                    action_counts.get(parsed[idx]["action"], 0) + 1
                )
            top = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
            action_str = ", ".join(f"{a}:{c}" for a, c in top)
            # Find top bigrams in this cluster
            cluster_bigram_counts: Counter = Counter()
            for idx in indices:
                tokens = tokenize(parsed[idx]["reasoning"])
                bigrams = get_bigrams(tokens)
                cluster_bigram_counts.update(bigrams)
            top_bigrams = cluster_bigram_counts.most_common(3)
            bigram_str = ", ".join(f'"{bg}"' for bg, _ in top_bigrams)
            print(
                f"    Cluster {ki}: {int(mask.sum()):3d} [{action_str}] top_bigrams=[{bigram_str}]"
            )
            for idx in indices[:2]:
                print(f"      [{idx:3d}] {parsed[idx]['reasoning'][:100]}")


if __name__ == "__main__":
    main()
