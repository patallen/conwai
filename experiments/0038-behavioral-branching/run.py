"""
Experiment 0038: Detect behavioral branching.

From 0037: the same condition ("starving, zero bread") leads to different
decisions ("bake" vs "forage" vs "spend coins"). This is behavioral
branching — the agent faces the same situation multiple times but
responds differently.

Detecting these branches is consolidation gold: the agent can learn
"in situation X, I sometimes did A and sometimes did B."

Method: cluster CONDITIONS only. Within each condition cluster, cluster
DECISIONS. Where the same condition has multiple decision sub-clusters,
that's a branch point.

Usage:
    PYTHONPATH=. uv run python experiments/0038-behavioral-branching/run.py
"""

import json
import re
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

CACHE_PARSED = Path("experiments/helen_parsed.json")

_SENT_SPLIT = re.compile(r"(?<=[.!?])\s+")


def split_first_last(text: str) -> tuple[str, str]:
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


def cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    print(f"Loaded {len(parsed)} entries\n")

    conditions = []
    decisions = []
    for p in parsed:
        cond, dec = split_first_last(p["reasoning"])
        conditions.append(cond)
        decisions.append(dec)

    # Embed
    from conwai.embeddings import FastEmbedder

    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    cond_vecs = np.array(embedder.embed(conditions))
    dec_vecs = np.array(embedder.embed(decisions))

    # Residual + PCA
    cond_res = cond_vecs - np.mean(cond_vecs, axis=0)
    dec_res = dec_vecs - np.mean(dec_vecs, axis=0)
    cond_pca = pca_project(cond_res, 3)
    dec_pca = pca_project(dec_res, 3)

    # Step 1: Cluster CONDITIONS into situation types
    n_conditions = 8
    cond_labels = KMeans(
        n_clusters=n_conditions, random_state=42, n_init=10
    ).fit_predict(cond_pca)

    print(f"{'=' * 70}")
    print(f"STEP 1: {n_conditions} SITUATION TYPES")
    print(f"{'=' * 70}")

    for ci in range(n_conditions):
        mask = cond_labels == ci
        indices = np.where(mask)[0]
        size = int(mask.sum())

        # Representative condition
        center = cond_pca[indices].mean(axis=0)
        dists = np.linalg.norm(cond_pca[indices] - center, axis=1)
        rep_idx = indices[np.argmin(dists)]

        action_counts: dict[str, int] = {}
        for idx in indices:
            action_counts[parsed[idx]["action"]] = (
                action_counts.get(parsed[idx]["action"], 0) + 1
            )
        top_actions = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
        action_str = ", ".join(f"{a}:{c}" for a, c in top_actions)

        print(f"\n  Situation {ci + 1} ({size} episodes) [{action_str}]")
        print(f"    Representative: {conditions[rep_idx][:120]}")

    # Step 2: Within each situation, cluster DECISIONS
    print(f"\n{'=' * 70}")
    print("STEP 2: BEHAVIORAL BRANCHING WITHIN SITUATIONS")
    print(f"{'=' * 70}")

    for ci in range(n_conditions):
        mask = cond_labels == ci
        indices = np.where(mask)[0]
        size = int(mask.sum())

        if size < 4:
            continue

        # Cluster decisions within this situation
        dec_within = dec_pca[indices]
        n_sub = min(3, size // 2)
        if n_sub < 2:
            continue

        sub_labels = KMeans(n_clusters=n_sub, random_state=42, n_init=10).fit_predict(
            dec_within
        )

        # Check if decisions actually differ
        sub_sizes = [int((sub_labels == ki).sum()) for ki in range(n_sub)]
        if min(sub_sizes) < 2:
            continue

        # Compute inter-decision-cluster distance
        centers = [dec_within[sub_labels == ki].mean(axis=0) for ki in range(n_sub)]
        inter_sims = []
        for a in range(len(centers)):
            for b in range(a + 1, len(centers)):
                inter_sims.append(cosine_sim(centers[a], centers[b]))
        avg_inter_sim = np.mean(inter_sims) if inter_sims else 1.0

        # Only report if decisions are actually different (low inter-cluster similarity)
        center = cond_pca[indices].mean(axis=0)
        dists = np.linalg.norm(cond_pca[indices] - center, axis=1)
        rep_idx = indices[np.argmin(dists)]

        print(f"\n  Situation {ci + 1} ({size} episodes): {conditions[rep_idx][:100]}")
        print(
            f"    Decision divergence: {1 - avg_inter_sim:.3f} (higher=more divergent)"
        )

        for ki in range(n_sub):
            sub_mask = sub_labels == ki
            sub_indices = indices[sub_mask]
            sub_size = int(sub_mask.sum())

            # Representative decision
            sub_center = dec_within[sub_mask].mean(axis=0)
            sub_dists = np.linalg.norm(dec_within[sub_mask] - sub_center, axis=1)
            sub_rep = sub_indices[np.argmin(sub_dists)]

            sub_actions: dict[str, int] = {}
            for idx in sub_indices:
                sub_actions[parsed[idx]["action"]] = (
                    sub_actions.get(parsed[idx]["action"], 0) + 1
                )
            sub_action_str = ", ".join(
                f"{a}:{c}"
                for a, c in sorted(sub_actions.items(), key=lambda x: -x[1])[:3]
            )

            print(f"    Branch {ki + 1} ({sub_size} eps) [{sub_action_str}]:")
            print(f"      Decision: {decisions[sub_rep][:120]}")

    # Summary: which situations have the most behavioral variation?
    print(f"\n{'=' * 70}")
    print("BRANCH POINT SUMMARY")
    print(f"{'=' * 70}")
    print("(Situations where the agent consistently faces the same condition")
    print(
        " but makes different decisions — these are the richest consolidation targets)\n"
    )

    branch_points = []
    for ci in range(n_conditions):
        mask = cond_labels == ci
        indices = np.where(mask)[0]
        size = int(mask.sum())
        if size < 6:
            continue

        dec_within = dec_pca[indices]
        # Measure decision variance
        dec_var = np.var(dec_within, axis=0).sum()

        center = cond_pca[indices].mean(axis=0)
        dists = np.linalg.norm(cond_pca[indices] - center, axis=1)
        rep_idx = indices[np.argmin(dists)]

        branch_points.append((ci, size, dec_var, rep_idx))

    branch_points.sort(key=lambda x: -x[2])
    for ci, size, dec_var, rep_idx in branch_points:
        print(f"  Situation {ci + 1} ({size} eps, decision variance={dec_var:.4f}):")
        print(f"    {conditions[rep_idx][:120]}")


if __name__ == "__main__":
    main()
