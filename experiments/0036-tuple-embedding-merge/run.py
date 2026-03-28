"""
Experiment 0036: Embed structured tuples and cluster to merge near-duplicates.

0035 showed that regex-extracted tuples are conceptually right but too
fragmented (160 unique from 251 entries). Here we embed the tuple strings
and use residual+PCA clustering to merge near-duplicate tuples into
consolidated patterns.

The output: a small set of merged patterns, each backed by N episodes.
THAT is the consolidated knowledge.

Usage:
    PYTHONPATH=. uv run python experiments/0036-tuple-embedding-merge/run.py
"""

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

CACHE_PARSED = Path("experiments/helen_parsed.json")

# Simplified extraction — fewer, broader categories
CONDITION_EXTRACTORS = [
    (r"zero bread|no bread", "no_bread"),
    (r"zero flour|no flour", "no_flour"),
    (r"critically|starving|starvation|perish|dying|desperate", "crisis"),
    (r"surplus|ample|stable|secured|sufficient|comfortable", "stable"),
    (r"coin surplus|coin reserves|\d{2,} coins", "has_coins"),
    (r"pending offer|unanswered|waiting", "waiting_on_trade"),
    (
        r"unfavorable|predatory|bad rate|poor rate|overpriced|1:1|1\.5:1|2:1",
        "bad_offer_present",
    ),
]

BEHAVIOR_EXTRACTORS = [
    (r"I will forage|I must forage|forage immediately", "will_forage"),
    (r"I will bake|I must bake|bake immediately", "will_bake"),
    (r"I will accept|accept.*offer", "will_accept"),
    (
        r"I will decline|I will reject|I will ignore|I will not accept|refuse",
        "will_reject",
    ),
    (r"I will send|I will DM|send.*message", "will_message"),
    (r"I will offer|I will propose|offer.*trade", "will_offer"),
    (r"I will inspect", "will_inspect"),
    (r"I will vote", "will_vote"),
    (r"I will pay|use.*coins to", "will_pay"),
    (r"abandon.*(?:skeptic|deliberate|cautious|usual)", "abandon_caution"),
    (r"strategy.*(?:demands|dictates|forbids|prioritizes)", "follow_strategy"),
    (r"eating raw flour", "eating_raw"),
]


def extract_pattern(reasoning: str) -> str:
    text = reasoning.lower()
    conditions = []
    behaviors = []

    for pattern, label in CONDITION_EXTRACTORS:
        if re.search(pattern, text):
            conditions.append(label)
    for pattern, label in BEHAVIOR_EXTRACTORS:
        if re.search(pattern, text):
            behaviors.append(label)

    parts = []
    if conditions:
        parts.append("WHEN " + "+".join(sorted(set(conditions))))
    if behaviors:
        parts.append("DO " + "+".join(sorted(set(behaviors))))
    return " ".join(parts) if parts else "unclassified"


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    print(f"Loaded {len(parsed)} entries\n")

    # Extract patterns
    patterns = [extract_pattern(p["reasoning"]) for p in parsed]

    # Count unique patterns
    pattern_counts = Counter(patterns)
    print(f"Unique patterns: {len(pattern_counts)}")
    print("\nTop 25 patterns:")
    for p, count in pattern_counts.most_common(25):
        print(f"  {count:3d}x  {p}")

    # Now embed the UNIQUE patterns and cluster to merge near-duplicates
    unique_patterns = list(pattern_counts.keys())
    print(f"\nEmbedding {len(unique_patterns)} unique pattern strings...")
    from conwai.llm import FastEmbedder

    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    pattern_vecs = np.array(embedder.embed(unique_patterns))

    # Residual + PCA on pattern embeddings
    centroid = np.mean(pattern_vecs, axis=0)
    residuals = pattern_vecs - centroid
    _, _, Vt = np.linalg.svd(residuals - residuals.mean(axis=0), full_matrices=False)
    projected = (residuals - residuals.mean(axis=0)) @ Vt[:5].T

    # Find best K for merging
    print("\nClustering pattern embeddings:")
    for k in [5, 8, 10, 15, 20]:
        if k >= len(unique_patterns):
            continue
        labels = KMeans(n_clusters=k, random_state=42, n_init=10).fit_predict(projected)
        sil = (
            silhouette_score(projected, labels, metric="cosine")
            if k < len(unique_patterns)
            else 0
        )
        print(f"  K={k}: sil={sil:.4f}")

    # Use K=10 for merging
    merge_k = min(10, len(unique_patterns) - 1)
    labels = KMeans(n_clusters=merge_k, random_state=42, n_init=10).fit_predict(
        projected
    )

    # Map each entry to its merged cluster
    pattern_to_cluster = {p: labels[i] for i, p in enumerate(unique_patterns)}
    entry_clusters = [pattern_to_cluster[p] for p in patterns]

    print(f"\n{'=' * 70}")
    print(f"MERGED CONSOLIDATED PATTERNS (K={merge_k})")
    print(f"{'=' * 70}")
    for ki in range(merge_k):
        # Which patterns merged into this cluster?
        cluster_patterns = [
            (p, pattern_counts[p])
            for i, p in enumerate(unique_patterns)
            if labels[i] == ki
        ]
        cluster_patterns.sort(key=lambda x: -x[1])
        total_episodes = sum(c for _, c in cluster_patterns)

        # Most common pattern is the "representative"
        representative = cluster_patterns[0][0]

        # Entry indices in this cluster
        entry_indices = [i for i, c in enumerate(entry_clusters) if c == ki]
        action_counts: dict[str, int] = {}
        for idx in entry_indices:
            action_counts[parsed[idx]["action"]] = (
                action_counts.get(parsed[idx]["action"], 0) + 1
            )
        top_actions = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
        action_str = ", ".join(f"{a}:{c}" for a, c in top_actions)

        print(f"\n  CONCEPT {ki + 1} ({total_episodes} episodes) [{action_str}]")
        print(f"    Representative: {representative}")
        print(f"    Merged patterns ({len(cluster_patterns)}):")
        for p, c in cluster_patterns[:5]:
            print(f"      {c:3d}x  {p}")
        if len(cluster_patterns) > 5:
            print(f"      ... and {len(cluster_patterns) - 5} more variants")
        print("    Example entries:")
        for idx in entry_indices[:3]:
            print(f"      [{idx:3d}] {parsed[idx]['reasoning'][:100]}")


if __name__ == "__main__":
    main()
