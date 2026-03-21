"""
Experiment 0034: Find condition→behavior patterns in residual+PCA space.

Instead of K-means (which forces broad categories), use high-threshold
nearest-neighbor cliques in the residual+PCA space. Then for each clique,
extract what CONDITION and BEHAVIOR the entries share — that's the
consolidated knowledge.

The goal: "when at zero bread and offered bad rate → accept anyway"
NOT: "trade evaluation cluster"

Usage:
    PYTHONPATH=. uv run python experiments/0034-tight-cliques/run.py
"""

import json
import re
from pathlib import Path

import numpy as np

CACHE_VECS = Path("experiments/helen_embeddings.npz")
CACHE_PARSED = Path("experiments/helen_parsed.json")


def pca_project(X: np.ndarray, n_components: int) -> np.ndarray:
    mean = X.mean(axis=0)
    centered = X - mean
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ Vt[:n_components].T


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def find_cliques(vectors: np.ndarray, threshold: float) -> list[list[int]]:
    """Find cliques where ALL pairs exceed threshold. No size limit."""
    n = len(vectors)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    normed = vectors / norms
    sim = normed @ normed.T

    seen_cliques: set[frozenset] = set()
    cliques: list[list[int]] = []

    for seed in range(n):
        # Find all neighbors above threshold
        neighbors = [j for j in range(n) if j != seed and sim[seed, j] > threshold]
        if not neighbors:
            continue

        # Build maximal clique from seed
        clique = [seed]
        for candidate in sorted(neighbors, key=lambda j: -sim[seed, j]):
            if all(sim[candidate, c] > threshold for c in clique):
                clique.append(candidate)

        if len(clique) >= 2:
            key = frozenset(clique)
            if key not in seen_cliques:
                seen_cliques.add(key)
                cliques.append(sorted(clique))

    return cliques


def extract_shared_words(entries: list[str]) -> list[str]:
    """Find words that appear in ALL entries of a clique."""
    word_sets = []
    for entry in entries:
        words = set(re.findall(r"[a-z]+", entry.lower()))
        word_sets.append(words)
    if not word_sets:
        return []
    shared = word_sets[0]
    for ws in word_sets[1:]:
        shared = shared & ws
    # Remove ultra-common words
    stopwords = {"i", "my", "the", "a", "an", "to", "and", "of", "in", "is", "am",
                 "will", "for", "with", "as", "at", "by", "on", "it", "that", "this",
                 "be", "have", "has", "not", "but", "or", "so", "if", "me", "do"}
    return sorted(shared - stopwords)


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"]
    print(f"Loaded {len(parsed)} entries\n")

    # Residual + PCA
    centroid = np.mean(vectors, axis=0)
    residuals = vectors - centroid
    projected = pca_project(residuals, 5)

    # Find cliques at various thresholds
    for threshold in [0.90, 0.85, 0.80, 0.75, 0.70]:
        cliques = find_cliques(projected, threshold)
        sizes = [len(c) for c in cliques]
        print(f"Threshold {threshold:.2f}: {len(cliques)} cliques, "
              f"sizes range {min(sizes) if sizes else 0}-{max(sizes) if sizes else 0}, "
              f"total entries covered: {len(set().union(*[set(c) for c in cliques])) if cliques else 0}")

    # Detailed analysis at the most interesting threshold
    # Pick threshold that gives 15-40 cliques
    best_threshold = 0.80
    cliques = find_cliques(projected, best_threshold)
    cliques.sort(key=lambda c: -len(c))

    print(f"\n{'='*70}")
    print(f"CLIQUES AT THRESHOLD {best_threshold} ({len(cliques)} cliques)")
    print(f"{'='*70}")

    for ci, clique in enumerate(cliques[:25]):
        entries_text = [parsed[idx]["reasoning"] for idx in clique]
        actions = [parsed[idx]["action"] for idx in clique]
        action_counts: dict[str, int] = {}
        for a in actions:
            action_counts[a] = action_counts.get(a, 0) + 1
        action_str = ", ".join(f"{a}:{c}" for a, c in sorted(action_counts.items(), key=lambda x: -x[1]))

        shared = extract_shared_words(entries_text)

        print(f"\n  Clique {ci+1} (size={len(clique)}) [{action_str}]")
        print(f"    Shared words: {', '.join(shared[:15])}")
        # Show first 3 entries (truncated)
        for idx in clique[:3]:
            print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:120]}")
        if len(clique) > 3:
            print(f"    ... and {len(clique)-3} more")

    # Try to extract condition→behavior patterns
    print(f"\n{'='*70}")
    print("CONDITION→BEHAVIOR EXTRACTION")
    print(f"{'='*70}")
    print("For each clique, what condition and behavior do ALL entries share?\n")

    for ci, clique in enumerate(cliques[:15]):
        entries_text = [parsed[idx]["reasoning"] for idx in clique]
        shared = extract_shared_words(entries_text)

        # Look for condition indicators
        condition_words = {"zero", "critically", "starving", "surplus", "low",
                          "stable", "ample", "risk", "desperate", "vulnerable"}
        behavior_words = {"forage", "bake", "trade", "accept", "reject", "decline",
                         "ignore", "offer", "inspect", "vote", "post", "send"}
        resource_words = {"bread", "flour", "water", "coins"}

        conditions = [w for w in shared if w in condition_words]
        behaviors = [w for w in shared if w in behavior_words]
        resources = [w for w in shared if w in resource_words]

        if conditions or behaviors:
            pattern = ""
            if conditions and resources:
                pattern += f"WHEN {'+'.join(conditions)} {'+'.join(resources)}"
            elif conditions:
                pattern += f"WHEN {'+'.join(conditions)}"
            if behaviors:
                pattern += f" → {'+'.join(behaviors)}"
            print(f"  Clique {ci+1} ({len(clique)} entries): {pattern}")
            print(f"    All shared: {', '.join(shared[:20])}")
        else:
            print(f"  Clique {ci+1} ({len(clique)} entries): no clear pattern detected")
            print(f"    Shared: {', '.join(shared[:20])}")


if __name__ == "__main__":
    main()
