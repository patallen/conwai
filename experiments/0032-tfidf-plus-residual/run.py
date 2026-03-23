"""
Experiment 0032: Hybrid TF-IDF + Residual Embedding.

Concatenate TF-IDF features (good at word-level discrimination) with
residual embedding features (good at semantic-level discrimination).
Then PCA to reduce the combined high-dimensional space.

Usage:
    PYTHONPATH=. uv run python experiments/0032-tfidf-plus-residual/run.py
"""

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

CACHE_VECS = Path("experiments/helen_embeddings.npz")
CACHE_PARSED = Path("experiments/helen_parsed.json")

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
    "immediately",
    "surplus",
    "current",
    "strategy",
    "nature",
    "skeptical",
}


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


def pca_project(X: np.ndarray, n_components: int) -> np.ndarray:
    mean = X.mean(axis=0)
    centered = X - mean
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ Vt[:n_components].T


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"]
    print(f"Loaded {len(parsed)} entries\n")

    # Build TF-IDF
    documents = [p["reasoning"] for p in parsed]
    tfidf = build_tfidf(documents)
    print(f"TF-IDF shape: {tfidf.shape}")

    # Residual embeddings
    centroid = np.mean(vectors, axis=0)
    residuals = vectors - centroid
    print(f"Residual shape: {residuals.shape}")

    # Normalize both to same scale before concatenating
    res_std = residuals.std()
    tfidf_std = tfidf.std()
    residuals_normed = residuals / (res_std + 1e-10)
    tfidf_normed = tfidf / (tfidf_std + 1e-10)

    # Concatenate
    combined = np.concatenate([residuals_normed, tfidf_normed], axis=1)
    print(f"Combined shape: {combined.shape}")

    # PCA on combined
    print(f"\n{'=' * 70}")
    print("COMPARISON: INDIVIDUAL vs COMBINED")
    print(f"{'=' * 70}")

    representations = {
        "tfidf_only": tfidf,
        "residual_only": residuals,
        "residual_pca5": pca_project(residuals, 5),
        "combined_pca5": pca_project(combined, 5),
        "combined_pca10": pca_project(combined, 10),
        "combined_pca20": pca_project(combined, 20),
    }

    for name, vecs in representations.items():
        for k in [5, 8, 10]:
            km = KMeans(n_clusters=k, random_state=42, n_init=10)
            labels = km.fit_predict(vecs)
            sil = silhouette_score(vecs, labels, metric="cosine")
            sizes = sorted([int((labels == ki).sum()) for ki in range(k)], reverse=True)
            print(f"  {name:20s} K={k:2d}: sil={sil:.4f} sizes={sizes}")
        print()

    # Detailed best
    best_name = "combined_pca5"
    best_vecs = representations[best_name]
    km = KMeans(n_clusters=8, random_state=42, n_init=10)
    labels = km.fit_predict(best_vecs)
    sil = silhouette_score(best_vecs, labels, metric="cosine")

    print(f"\n{'=' * 70}")
    print(f"DETAILED: {best_name} K=8 (sil={sil:.4f})")
    print(f"{'=' * 70}")
    for ki in range(8):
        mask = labels == ki
        indices = np.where(mask)[0]
        action_counts: dict[str, int] = {}
        for idx in indices:
            action_counts[parsed[idx]["action"]] = (
                action_counts.get(parsed[idx]["action"], 0) + 1
            )
        top = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
        action_str = ", ".join(f"{a}:{c}" for a, c in top)
        print(f"  Cluster {ki} ({int(mask.sum())}) [{action_str}]")
        for idx in indices[:2]:
            print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:100]}")


if __name__ == "__main__":
    main()
