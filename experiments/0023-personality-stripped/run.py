"""
Experiment 0023: Strip personality markers before embedding.

Helen's entries are saturated with "my skeptical nature", "given my
deliberate approach", etc. These phrases appear in almost every entry
and may be a major contributor to the dense ball. Strip them and see
if the remaining content is more distinguishable.

Usage:
    PYTHONPATH=. uv run python experiments/0023-personality-stripped/run.py
"""

import json
import re
from pathlib import Path

import numpy as np

from conwai.embeddings import FastEmbedder

CACHE_PARSED = Path("experiments/helen_parsed.json")
# Need FastEmbedder here because we re-embed stripped text

_ACTION_RE = re.compile(r"\] (\w+)→")

# Personality phrases that appear frequently in Helen's entries
PERSONALITY_PATTERNS = [
    r"my skeptical nature\s*(demands|dictates|requires|tells me)?",
    r"given my skeptical nature,?",
    r"my skeptical and deliberate\s*(nature|approach)",
    r"as a skeptic,?",
    r"my deliberate\s*(nature|approach|pace|pacing)",
    r"given my deliberate approach,?",
    r"my usual\s*(deliberate|cautious|skeptical)\s*(pace|pacing|approach|nature)",
    r"despite my\s*(usual )?(skeptic\w+|deliberate|cautious)\s*(nature|approach)?",
    r"abandon(ing)? my usual\s*(deliberate|cautious|skeptical)",
    r"my\s*(cautious|careful|deliberate)\s*(nature|approach)",
    r"I am skeptical\s*(of|about)?",
]

_PERSONALITY_RE = re.compile(
    "|".join(f"({p})" for p in PERSONALITY_PATTERNS),
    re.IGNORECASE,
)


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def strip_personality(text: str) -> str:
    stripped = _PERSONALITY_RE.sub(" ", text)
    return re.sub(r"\s+", " ", stripped).strip()


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

    # Strip personality
    stripped = [strip_personality(p["reasoning"]) for p in parsed]

    # Show effect
    matches = 0
    for i, (orig, s) in enumerate(zip([p["reasoning"] for p in parsed], stripped)):
        if orig != s:
            matches += 1
    print(f"Entries with personality markers: {matches}/{len(parsed)}")

    print("\nSample stripping:")
    for i in range(min(5, len(parsed))):
        orig = parsed[i]["reasoning"][:120]
        s = stripped[i][:120]
        if orig != s:
            print(f"  [{i}] ORIG:     {orig}")
            print(f"       STRIPPED: {s}")

    # Load cached original embeddings and embed stripped
    orig_vecs = np.load(Path("experiments/helen_embeddings.npz"))["vectors"]
    print("\nEmbedding stripped text...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    strip_vecs = np.array(embedder.embed(stripped))

    orig_stats = pairwise_stats(orig_vecs)
    strip_stats = pairwise_stats(strip_vecs)
    print(f"Original: mean={orig_stats['mean']:.4f} std={orig_stats['std']:.4f}")
    print(f"Stripped: mean={strip_stats['mean']:.4f} std={strip_stats['std']:.4f}")

    # K-means comparison
    print(f"\n{'=' * 70}")
    print("K-MEANS K=10 COMPARISON")
    print(f"{'=' * 70}")
    for name, vecs in [("original", orig_vecs), ("personality_stripped", strip_vecs)]:
        labels = kmeans_cosine(vecs, 10)
        sizes = sorted([int((labels == k).sum()) for k in range(10)], reverse=True)
        print(f"  {name}: sizes={sizes}")

    # Detailed clusters on stripped
    print(f"\n{'=' * 70}")
    print("STRIPPED CLUSTERS (K=10)")
    print(f"{'=' * 70}")
    labels = kmeans_cosine(strip_vecs, 10)
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
        print(f"\n  Cluster {ki} ({int(mask.sum())} entries) [{action_str}]")
        for idx in indices[:2]:
            print(f"    [{idx:3d}] {stripped[idx][:110]}")


if __name__ == "__main__":
    main()
