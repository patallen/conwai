"""
Experiment 0020: Sentence-level decomposition.

Instead of embedding full diary entries (which are multi-sentence and
dominated by shared context), split each entry into individual sentences
and embed those. Cluster at the sentence level, then map back to entries.

Hypothesis: individual sentences like "I rejected the 2:1 offer" or
"My skeptical nature demands verification" are more distinctive than
full paragraphs of reasoning.

Usage:
    PYTHONPATH=. uv run python experiments/0020-sentence-decomposition/run.py
"""

import json
import re
from pathlib import Path

import numpy as np

from conwai.embeddings import FastEmbedder

CACHE_PARSED = Path("experiments/helen_parsed.json")
# NOTE: We need to re-embed sentences, so FastEmbedder is still needed here
# but we only load it once for sentences, not for entries (which are cached)

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_sentences(text: str) -> list[str]:
    sents = _SENT_SPLIT.split(text.strip())
    return [s.strip() for s in sents if len(s.strip()) > 10]


def pairwise_stats(vectors: np.ndarray) -> dict:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sim = (vectors / norms) @ (vectors / norms).T
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
    parsed = json.loads(CACHE_PARSED.read_text())
    print(f"Loaded {len(parsed)} entries\n")

    # Split entries into sentences
    all_sentences: list[str] = []
    sentence_to_entry: list[int] = []  # which entry each sentence belongs to
    for i, p in enumerate(parsed):
        sents = split_sentences(p["reasoning"])
        for s in sents:
            all_sentences.append(s)
            sentence_to_entry.append(i)

    print(f"Total sentences: {len(all_sentences)} from {len(parsed)} entries")
    avg_sents = len(all_sentences) / len(parsed)
    print(f"Average sentences per entry: {avg_sents:.1f}")

    # Show sample sentences
    print("\nSample sentences (first 10):")
    for i in range(min(10, len(all_sentences))):
        print(f"  [entry {sentence_to_entry[i]:3d}] {all_sentences[i][:100]}")

    # Embed all sentences
    print(f"\nEmbedding {len(all_sentences)} sentences...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    sent_vecs = np.array(embedder.embed(all_sentences))

    # Load cached entry vectors
    entry_vecs = np.load(Path("experiments/helen_embeddings.npz"))["vectors"]
    entry_stats = pairwise_stats(entry_vecs)
    sent_stats = pairwise_stats(sent_vecs)
    print(f"\nEntry-level: mean={entry_stats['mean']:.4f} std={entry_stats['std']:.4f}")
    print(f"Sentence-level: mean={sent_stats['mean']:.4f} std={sent_stats['std']:.4f}")

    # K-means on sentences
    print(f"\n{'=' * 70}")
    print("K-MEANS ON SENTENCES (K=15)")
    print(f"{'=' * 70}")
    labels = kmeans_cosine(sent_vecs, 15)

    for ki in range(15):
        mask = labels == ki
        indices = np.where(mask)[0]
        # Map back to entries
        entry_indices = set(sentence_to_entry[idx] for idx in indices)
        action_counts: dict[str, int] = {}
        for ei in entry_indices:
            a = parsed[ei]["action"]
            action_counts[a] = action_counts.get(a, 0) + 1

        print(
            f"\n  Cluster {ki} ({int(mask.sum())} sentences, {len(entry_indices)} entries)"
        )
        # Show sample sentences
        for idx in indices[:4]:
            print(f"    [{sentence_to_entry[idx]:3d}] {all_sentences[idx][:100]}")
        if mask.sum() > 4:
            print(f"    ... and {int(mask.sum()) - 4} more sentences")

    # Also try: embed sentences, then for each ENTRY compute its representation
    # as the mean of its sentence embeddings
    print(f"\n{'=' * 70}")
    print("ENTRY-LEVEL: MEAN OF SENTENCE EMBEDDINGS")
    print(f"{'=' * 70}")
    entry_from_sents = np.zeros((len(parsed), sent_vecs.shape[1]))
    for i in range(len(parsed)):
        sent_indices = [j for j, ei in enumerate(sentence_to_entry) if ei == i]
        if sent_indices:
            entry_from_sents[i] = sent_vecs[sent_indices].mean(axis=0)

    mean_sent_stats = pairwise_stats(entry_from_sents)
    print(
        f"Mean-of-sentences: mean={mean_sent_stats['mean']:.4f} std={mean_sent_stats['std']:.4f}"
    )
    print(f"(vs direct entry embedding: mean={entry_stats['mean']:.4f})")

    labels = kmeans_cosine(entry_from_sents, 10)
    sizes = sorted([int((labels == k).sum()) for k in range(10)], reverse=True)
    print(f"K-means K=10: sizes={sizes}")


if __name__ == "__main__":
    main()
