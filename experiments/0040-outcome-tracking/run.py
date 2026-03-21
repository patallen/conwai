"""
Experiment 0040: Outcome tracking — which branch decisions lead to better results?

Look at consecutive entries: if entry N is a decision and entry N+1 shows
the result, we can track whether the decision helped. Specifically:
- Did the agent's bread/flour/water go up or down after the decision?
- Did the agent stay in crisis or escape it?
- Did the condition recur (suggesting the decision didn't solve the problem)?

This adds a VALUE signal to the condition→decision patterns.
The consolidation should learn not just "in situation X, I do A or B"
but "in situation X, doing A works better than B."

Usage:
    PYTHONPATH=. uv run python experiments/0040-outcome-tracking/run.py
"""

import json
import re
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans

CACHE_PARSED = Path("experiments/helen_parsed.json")
CACHE_VECS = Path("experiments/helen_embeddings.npz")

_SENT_SPLIT = re.compile(r'(?<=[.!?])\s+')

# Extract resource mentions
_ZERO_BREAD = re.compile(r"zero bread|no bread|0 bread", re.IGNORECASE)
_CRISIS = re.compile(r"critically|starving|starvation|desperate|perish", re.IGNORECASE)
_STABLE = re.compile(r"surplus|stable|secured|sufficient|ample", re.IGNORECASE)

# Extract numbers
_BREAD_COUNT = re.compile(r"(\d+)\s*(?:bread|loaves|loaf)", re.IGNORECASE)
_FLOUR_COUNT = re.compile(r"(\d+)\s*flour", re.IGNORECASE)
_WATER_COUNT = re.compile(r"(\d+)\s*water", re.IGNORECASE)


def extract_resources(text: str) -> dict:
    """Extract resource levels mentioned in text."""
    resources = {}
    m = _BREAD_COUNT.search(text)
    if m:
        resources["bread"] = int(m.group(1))
    m = _FLOUR_COUNT.search(text)
    if m:
        resources["flour"] = int(m.group(1))
    m = _WATER_COUNT.search(text)
    if m:
        resources["water"] = int(m.group(1))
    resources["in_crisis"] = bool(_CRISIS.search(text))
    resources["is_stable"] = bool(_STABLE.search(text))
    resources["zero_bread"] = bool(_ZERO_BREAD.search(text))
    return resources


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


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    vectors = np.load(CACHE_VECS)["vectors"]
    print(f"Loaded {len(parsed)} entries\n")

    # Extract resources from each entry
    resources = [extract_resources(p["reasoning"]) for p in parsed]

    # Show resource trajectory
    print("Resource trajectory (entries with bread count):")
    bread_trajectory = [(i, r["bread"]) for i, r in enumerate(resources) if "bread" in r]
    crisis_entries = [i for i, r in enumerate(resources) if r["in_crisis"]]
    stable_entries = [i for i, r in enumerate(resources) if r["is_stable"]]
    print(f"  Crisis entries: {len(crisis_entries)}")
    print(f"  Stable entries: {len(stable_entries)}")
    print(f"  Entries with bread count: {len(bread_trajectory)}")
    if bread_trajectory:
        breads = [b for _, b in bread_trajectory]
        print(f"  Bread range: {min(breads)}-{max(breads)}")

    # Compute outcomes: for each entry, what's the state in the NEXT entry?
    outcomes = []
    for i in range(len(parsed) - 1):
        curr = resources[i]
        next_r = resources[i + 1]
        outcome = {
            "crisis_resolved": curr["in_crisis"] and not next_r["in_crisis"],
            "entered_crisis": not curr["in_crisis"] and next_r["in_crisis"],
            "stayed_crisis": curr["in_crisis"] and next_r["in_crisis"],
            "stayed_stable": curr["is_stable"] and next_r["is_stable"],
            "bread_improved": ("bread" in curr and "bread" in next_r and next_r["bread"] > curr["bread"]),
            "bread_worsened": ("bread" in curr and "bread" in next_r and next_r["bread"] < curr["bread"]),
        }
        outcomes.append(outcome)
    outcomes.append({k: False for k in ["crisis_resolved", "entered_crisis", "stayed_crisis",
                                         "stayed_stable", "bread_improved", "bread_worsened"]})

    # Condition+decision clustering (from 0037/0038)
    from conwai.embeddings import FastEmbedder
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")

    conditions = []
    decisions = []
    for p in parsed:
        cond, dec = split_first_last(p["reasoning"])
        conditions.append(cond)
        decisions.append(dec)

    cond_vecs = np.array(embedder.embed(conditions))
    dec_vecs = np.array(embedder.embed(decisions))

    cond_res = cond_vecs - np.mean(cond_vecs, axis=0)
    dec_res = dec_vecs - np.mean(dec_vecs, axis=0)
    cond_pca = pca_project(cond_res, 3)
    dec_pca = pca_project(dec_res, 3)

    # Cluster conditions into situations
    n_situations = 6
    cond_labels = KMeans(n_clusters=n_situations, random_state=42, n_init=10).fit_predict(cond_pca)

    # Within each situation, cluster decisions into branches
    print(f"\n{'='*70}")
    print("OUTCOME ANALYSIS BY SITUATION AND BRANCH")
    print(f"{'='*70}")

    for si in range(n_situations):
        sit_mask = cond_labels == si
        sit_indices = np.where(sit_mask)[0]
        if len(sit_indices) < 6:
            continue

        # Representative condition
        center = cond_pca[sit_indices].mean(axis=0)
        dists = np.linalg.norm(cond_pca[sit_indices] - center, axis=1)
        rep_idx = sit_indices[np.argmin(dists)]

        # Sub-cluster decisions
        dec_within = dec_pca[sit_indices]
        n_branches = min(3, len(sit_indices) // 3)
        if n_branches < 2:
            continue

        branch_labels = KMeans(n_clusters=n_branches, random_state=42, n_init=10).fit_predict(dec_within)

        print(f"\n  Situation {si+1} ({len(sit_indices)} entries):")
        print(f"    Condition: {conditions[rep_idx][:120]}")

        for bi in range(n_branches):
            branch_mask = branch_labels == bi
            branch_indices = sit_indices[branch_mask]

            # Representative decision
            dec_center = dec_within[branch_mask].mean(axis=0)
            dec_dists = np.linalg.norm(dec_within[branch_mask] - dec_center, axis=1)
            dec_rep = branch_indices[np.argmin(dec_dists)]

            # Outcome stats for this branch
            crisis_resolved = sum(1 for idx in branch_indices if outcomes[idx]["crisis_resolved"])
            stayed_crisis = sum(1 for idx in branch_indices if outcomes[idx]["stayed_crisis"])
            bread_improved = sum(1 for idx in branch_indices if outcomes[idx]["bread_improved"])
            bread_worsened = sum(1 for idx in branch_indices if outcomes[idx]["bread_worsened"])

            n = len(branch_indices)
            resolve_rate = crisis_resolved / n * 100 if n > 0 else 0
            improve_rate = bread_improved / n * 100 if n > 0 else 0

            action_counts: dict[str, int] = {}
            for idx in branch_indices:
                action_counts[parsed[idx]["action"]] = action_counts.get(parsed[idx]["action"], 0) + 1
            top_action = max(action_counts, key=action_counts.get) if action_counts else "?"

            print(f"\n    Branch {bi+1} ({n} entries, primary action: {top_action}):")
            print(f"      Decision: {decisions[dec_rep][:120]}")
            print(f"      Outcomes:")
            print(f"        Crisis resolved: {crisis_resolved}/{n} ({resolve_rate:.0f}%)")
            print(f"        Stayed in crisis: {stayed_crisis}/{n}")
            print(f"        Bread improved: {bread_improved}/{n} ({improve_rate:.0f}%)")
            print(f"        Bread worsened: {bread_worsened}/{n}")

    # Summary: which branches are most effective?
    print(f"\n{'='*70}")
    print("SUMMARY: DECISION EFFECTIVENESS")
    print(f"{'='*70}")
    print("(Which decision branches most often resolve crises or improve bread?)\n")

    for si in range(n_situations):
        sit_mask = cond_labels == si
        sit_indices = np.where(sit_mask)[0]
        if len(sit_indices) < 6:
            continue

        # Check if this is a crisis situation
        crisis_count = sum(1 for idx in sit_indices if resources[idx]["in_crisis"])
        if crisis_count < len(sit_indices) * 0.3:
            continue  # skip non-crisis situations

        center = cond_pca[sit_indices].mean(axis=0)
        dists = np.linalg.norm(cond_pca[sit_indices] - center, axis=1)
        rep_idx = sit_indices[np.argmin(dists)]

        dec_within = dec_pca[sit_indices]
        n_branches = min(3, len(sit_indices) // 3)
        if n_branches < 2:
            continue

        branch_labels = KMeans(n_clusters=n_branches, random_state=42, n_init=10).fit_predict(dec_within)

        print(f"  Crisis situation: {conditions[rep_idx][:100]}")
        for bi in range(n_branches):
            branch_indices = sit_indices[branch_labels == bi]
            n = len(branch_indices)
            resolved = sum(1 for idx in branch_indices if outcomes[idx]["crisis_resolved"])
            improved = sum(1 for idx in branch_indices if outcomes[idx]["bread_improved"])

            dec_center = dec_within[branch_labels == bi].mean(axis=0)
            dec_dists = np.linalg.norm(dec_within[branch_labels == bi] - dec_center, axis=1)
            dec_rep = branch_indices[np.argmin(dec_dists)]

            print(f"    Branch {bi+1} ({n} eps): resolve={resolved}/{n} improve={improved}/{n} → {decisions[dec_rep][:80]}")
        print()


if __name__ == "__main__":
    main()
