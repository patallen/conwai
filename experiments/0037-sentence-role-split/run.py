"""
Experiment 0037: Split entries into CONDITION and DECISION sentences.

Diary entries follow a consistent structure from the LLM:
  Sentence 1: State description ("I am starving with zero bread...")
  Sentence 2+: Reasoning and decision ("I will forage immediately...")

Split each entry into its FIRST sentence (condition/state) and LAST
sentence (decision/action). Embed each separately. Cluster the
PAIRS — entries with similar condition AND similar decision share
a consolidatable pattern.

Usage:
    PYTHONPATH=. uv run python experiments/0037-sentence-role-split/run.py
"""

import json
import re
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

CACHE_PARSED = Path("experiments/helen_parsed.json")
CACHE_VECS = Path("experiments/helen_embeddings.npz")

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')


def split_first_last(text: str) -> tuple[str, str]:
    """Split into first sentence (condition) and last sentence (decision)."""
    sents = [s.strip() for s in _SENT_SPLIT.split(text.strip()) if len(s.strip()) > 10]
    if len(sents) >= 2:
        return sents[0], sents[-1]
    elif len(sents) == 1:
        return sents[0], sents[0]
    return text, text


def pca_project(X: np.ndarray, n_components: int) -> np.ndarray:
    mean = X.mean(axis=0)
    centered = X - mean
    _, _, Vt = np.linalg.svd(centered, full_matrices=False)
    return centered @ Vt[:n_components].T


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    print(f"Loaded {len(parsed)} entries\n")

    # Split each entry
    conditions = []
    decisions = []
    for p in parsed:
        cond, dec = split_first_last(p["reasoning"])
        conditions.append(cond)
        decisions.append(dec)

    # Show samples
    print("Sample splits:")
    for i in [0, 18, 50, 77, 94, 150]:
        if i < len(parsed):
            print(f"  [{i:3d}] CONDITION: {conditions[i][:100]}")
            print(f"        DECISION:  {decisions[i][:100]}")
            print()

    # Embed conditions and decisions separately
    from conwai.embeddings import FastEmbedder
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")

    print("Embedding conditions...")
    cond_vecs = np.array(embedder.embed(conditions))
    print("Embedding decisions...")
    dec_vecs = np.array(embedder.embed(decisions))

    # Residual + PCA on each
    cond_residual = cond_vecs - np.mean(cond_vecs, axis=0)
    dec_residual = dec_vecs - np.mean(dec_vecs, axis=0)
    cond_pca = pca_project(cond_residual, 3)
    dec_pca = pca_project(dec_residual, 3)

    # Concatenate condition+decision representations
    combined = np.concatenate([cond_pca, dec_pca], axis=1)  # 6D
    print(f"\nCombined (condition+decision) shape: {combined.shape}")

    # Cluster the combined representation
    print(f"\n{'='*70}")
    print("CLUSTERING CONDITION+DECISION PAIRS")
    print(f"{'='*70}")
    for k in [5, 8, 10, 15, 20]:
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(combined)
        sil = silhouette_score(combined, labels)
        sizes = sorted([int((labels == ki).sum()) for ki in range(k)], reverse=True)
        print(f"  K={k:2d}: sil={sil:.4f} sizes={sizes}")

    # Detailed view at K=10
    best_k = 10
    labels = KMeans(n_clusters=best_k, random_state=42, n_init=10).fit_predict(combined)

    print(f"\n{'='*70}")
    print(f"CONSOLIDATED PATTERNS (K={best_k})")
    print(f"{'='*70}")
    for ki in range(best_k):
        mask = labels == ki
        indices = np.where(mask)[0]
        size = int(mask.sum())

        action_counts: dict[str, int] = {}
        for idx in indices:
            action_counts[parsed[idx]["action"]] = action_counts.get(parsed[idx]["action"], 0) + 1
        top_actions = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
        action_str = ", ".join(f"{a}:{c}" for a, c in top_actions)

        # Find the most common condition and decision in this cluster
        cluster_conds = [conditions[idx] for idx in indices]
        cluster_decs = [decisions[idx] for idx in indices]

        # Cluster centroid in condition and decision space
        cond_center = cond_pca[indices].mean(axis=0)
        dec_center = dec_pca[indices].mean(axis=0)

        # Find the entry closest to the centroid (most representative)
        dists = np.linalg.norm(combined[indices] - combined[indices].mean(axis=0), axis=1)
        representative_idx = indices[np.argmin(dists)]

        print(f"\n  PATTERN {ki+1} ({size} episodes) [{action_str}]")
        print(f"    Representative condition: {conditions[representative_idx][:120]}")
        print(f"    Representative decision:  {decisions[representative_idx][:120]}")
        print(f"    Examples:")
        for idx in indices[:3]:
            print(f"      [{idx:3d}] C: {conditions[idx][:80]}")
            print(f"           D: {decisions[idx][:80]}")

    # Compare: cluster conditions only vs decisions only vs both
    print(f"\n{'='*70}")
    print("COMPARISON: WHAT TO CLUSTER ON")
    print(f"{'='*70}")
    for name, vecs in [("conditions_only", cond_pca), ("decisions_only", dec_pca), ("combined", combined)]:
        labels = KMeans(n_clusters=10, random_state=42, n_init=10).fit_predict(vecs)
        sil = silhouette_score(vecs, labels)
        sizes = sorted([int((labels == ki).sum()) for ki in range(10)], reverse=True)
        print(f"  {name:20s}: sil={sil:.4f} sizes={sizes}")


if __name__ == "__main__":
    main()
