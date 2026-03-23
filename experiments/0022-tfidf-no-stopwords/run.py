"""
Experiment 0022: TF-IDF with stopword removal.

Remove high-frequency words that add noise: pronouns, articles,
common verbs ("I", "my", "will", "to", "am", "have", "the", etc).
Also remove domain-universal words that IDF doesn't catch because
they appear in MOST but not ALL docs.

Usage:
    PYTHONPATH=. uv run python experiments/0022-tfidf-no-stopwords/run.py
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
    # English stopwords
    "i",
    "me",
    "my",
    "myself",
    "we",
    "our",
    "ours",
    "you",
    "your",
    "yours",
    "he",
    "him",
    "his",
    "she",
    "her",
    "hers",
    "it",
    "its",
    "they",
    "them",
    "their",
    "what",
    "which",
    "who",
    "whom",
    "this",
    "that",
    "these",
    "those",
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
    "doing",
    "a",
    "an",
    "the",
    "and",
    "but",
    "if",
    "or",
    "because",
    "as",
    "until",
    "while",
    "of",
    "at",
    "by",
    "for",
    "with",
    "about",
    "against",
    "between",
    "through",
    "during",
    "before",
    "after",
    "above",
    "below",
    "to",
    "from",
    "up",
    "down",
    "in",
    "out",
    "on",
    "off",
    "over",
    "under",
    "again",
    "further",
    "then",
    "once",
    "here",
    "there",
    "when",
    "where",
    "why",
    "how",
    "all",
    "both",
    "each",
    "few",
    "more",
    "most",
    "other",
    "some",
    "such",
    "no",
    "nor",
    "not",
    "only",
    "own",
    "same",
    "so",
    "than",
    "too",
    "very",
    "can",
    "will",
    "just",
    "don",
    "should",
    "now",
    # Domain-near-universal (appear in >80% of docs but IDF doesn't fully suppress)
    "immediately",
    "surplus",
    "current",
    "strategy",
    "nature",
    "skeptical",
}


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def tokenize_filtered(text: str) -> list[str]:
    words = _WORD_RE.findall(text.lower())
    return [w for w in words if w not in STOPWORDS and len(w) > 2]


def build_tfidf(documents: list[str]) -> tuple[np.ndarray, list[str]]:
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
    return matrix / norms, vocab


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
    matrix, vocab = build_tfidf(documents)
    stats = pairwise_stats(matrix)
    print(f"Shape: {matrix.shape}")
    print(f"Mean sim: {stats['mean']:.4f} std: {stats['std']:.4f}")
    print("(Compare: raw TF-IDF 0.186, bge-large 0.797)\n")

    # Show what words remain after filtering
    print(f"Vocab after stopword removal: {len(vocab)} words")
    # Top remaining by document frequency
    doc_tokens = [set(tokenize_filtered(d)) for d in documents]
    word_df: dict[str, int] = {}
    for tokens in doc_tokens:
        for w in tokens:
            word_df[w] = word_df.get(w, 0) + 1
    top_words = sorted(word_df.items(), key=lambda x: -x[1])[:20]
    print("Most common remaining words:")
    for w, c in top_words:
        print(f"  {w:20s} in {c:3d} docs")

    # K-means
    print(f"\n{'=' * 70}")
    print("K-MEANS (K=10)")
    print(f"{'=' * 70}")
    labels = kmeans_cosine(matrix, 10)
    for ki in range(10):
        mask = labels == ki
        indices = np.where(mask)[0]
        action_counts: dict[str, int] = {}
        for idx in indices:
            action_counts[parsed[idx]["action"]] = (
                action_counts.get(parsed[idx]["action"], 0) + 1
            )
        top = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
        action_str = ", ".join(f"{a}:{c}" for a, c in top)
        # Top words in cluster
        cluster_words: Counter = Counter()
        for idx in indices:
            cluster_words.update(tokenize_filtered(parsed[idx]["reasoning"]))
        top_w = cluster_words.most_common(5)
        word_str = ", ".join(w for w, _ in top_w)
        print(f"\n  Cluster {ki} ({int(mask.sum())} entries) [{action_str}]")
        print(f"    Top words: {word_str}")
        for idx in indices[:3]:
            print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:100]}")


if __name__ == "__main__":
    main()
