"""
Experiment 0025: Sentiment-resource feature extraction.

Extract (quantity_descriptor, resource) pairs from entries:
  "zero bread" → crisis signal
  "surplus flour" → stability signal
  "critically low water" → danger signal

These features capture the CONTEXT of domain words, which is what
distinguishes behavioral patterns. A forage entry with "zero bread"
is fundamentally different from one with "surplus bread."

No embedding model needed — pure feature engineering.

Usage:
    PYTHONPATH=. uv run python experiments/0025-sentiment-resource-features/run.py
"""

import re
from pathlib import Path

import numpy as np

from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"

_ACTION_RE = re.compile(r"\] (\w+)→")

# Resources
RESOURCES = {"flour", "water", "bread", "coins", "coin", "loaves", "loaf"}

# Quantity descriptors (grouped by sentiment)
CRISIS_WORDS = {
    "zero",
    "critically",
    "starving",
    "desperate",
    "crisis",
    "depleted",
    "empty",
    "nothing",
    "perish",
    "dying",
    "starvation",
    "low",
    "dangerously",
    "vulnerable",
    "risk",
    "critical",
}
STABILITY_WORDS = {
    "surplus",
    "sufficient",
    "ample",
    "stable",
    "secured",
    "reserves",
    "stockpile",
    "buffer",
    "safety",
    "comfortable",
    "plenty",
    "excess",
    "abundant",
}
NEGATIVE_TRADE_WORDS = {
    "unfavorable",
    "predatory",
    "reject",
    "refuse",
    "decline",
    "overpriced",
    "exploitative",
    "bad",
    "poor",
    "terrible",
    "greedy",
    "aggressive",
    "inflated",
}
POSITIVE_TRADE_WORDS = {
    "fair",
    "reliable",
    "accept",
    "beneficial",
    "favorable",
    "reasonable",
    "confirmed",
    "successful",
    "trust",
    "verified",
}
ACTION_URGENCY = {
    "immediately",
    "must",
    "urgent",
    "now",
    "rush",
    "emergency",
    "forced",
    "abandon",
    "desperate",
}
DELIBERATE_WORDS = {
    "cautious",
    "careful",
    "verify",
    "assess",
    "evaluate",
    "deliberate",
    "strategic",
    "prioritize",
    "maintain",
}


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def extract_features(text: str) -> dict[str, float]:
    """Extract behavioral features from entry text."""
    words = set(re.findall(r"[a-z]+", text.lower()))
    features: dict[str, float] = {}

    # Resource-context features
    words & RESOURCES
    has_crisis = words & CRISIS_WORDS
    has_stability = words & STABILITY_WORDS

    features["crisis_level"] = len(has_crisis) / max(len(CRISIS_WORDS), 1)
    features["stability_level"] = len(has_stability) / max(len(STABILITY_WORDS), 1)

    # Trade sentiment
    has_neg_trade = words & NEGATIVE_TRADE_WORDS
    has_pos_trade = words & POSITIVE_TRADE_WORDS
    features["trade_negative"] = len(has_neg_trade) / max(len(NEGATIVE_TRADE_WORDS), 1)
    features["trade_positive"] = len(has_pos_trade) / max(len(POSITIVE_TRADE_WORDS), 1)

    # Action urgency
    has_urgent = words & ACTION_URGENCY
    has_deliberate = words & DELIBERATE_WORDS
    features["urgency"] = len(has_urgent) / max(len(ACTION_URGENCY), 1)
    features["deliberation"] = len(has_deliberate) / max(len(DELIBERATE_WORDS), 1)

    # Specific resource states
    for resource in ["bread", "flour", "water", "coins"]:
        if resource in words:
            features[f"has_{resource}"] = 1.0
            if has_crisis:
                features[f"crisis_{resource}"] = 1.0
            if has_stability:
                features[f"stable_{resource}"] = 1.0
        else:
            features[f"has_{resource}"] = 0.0

    # Social features
    # Count agent name mentions (any capitalized word not at sentence start)
    agent_mentions = len(re.findall(r"(?<!\. )(?<!\n)[A-Z][a-z]+", text))
    features["social_mentions"] = min(agent_mentions / 5.0, 1.0)

    return features


def features_to_vector(
    features: dict[str, float], feature_names: list[str]
) -> np.ndarray:
    return np.array([features.get(name, 0.0) for name in feature_names])


def kmeans(
    vectors: np.ndarray, k: int, max_iter: int = 100, seed: int = 42
) -> np.ndarray:
    rng = np.random.RandomState(seed)
    n = len(vectors)
    indices = rng.choice(n, k, replace=False)
    centroids = vectors[indices].copy()
    for _ in range(max_iter):
        dists = np.zeros((n, k))
        for ki in range(k):
            dists[:, ki] = np.linalg.norm(vectors - centroids[ki], axis=1)
        labels = dists.argmin(axis=1)
        new_centroids = np.zeros_like(centroids)
        for ki in range(k):
            mask = labels == ki
            if mask.sum() > 0:
                new_centroids[ki] = vectors[mask].mean(axis=0)
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

    # Extract features
    all_features = [extract_features(p["reasoning"]) for p in parsed]
    feature_names = sorted(set().union(*[f.keys() for f in all_features]))
    print(f"Features extracted: {len(feature_names)}")
    print(f"Feature names: {feature_names}\n")

    # Build feature matrix
    matrix = np.array([features_to_vector(f, feature_names) for f in all_features])
    print(f"Feature matrix shape: {matrix.shape}")

    # Show feature distributions
    print("\nFeature means across all entries:")
    for i, name in enumerate(feature_names):
        mean = matrix[:, i].mean()
        std = matrix[:, i].std()
        if mean > 0.01:
            print(f"  {name:25s} mean={mean:.3f} std={std:.3f}")

    # Show some sample feature vectors
    print("\nSample feature vectors:")
    for i in [0, 18, 50, 94, 193]:
        if i < len(parsed):
            feats = all_features[i]
            interesting = {k: v for k, v in feats.items() if v > 0.01}
            print(f"  [{i:3d}] [{parsed[i]['action']}] {interesting}")
            print(f"         {parsed[i]['reasoning'][:80]}")

    # K-means on features
    print(f"\n{'=' * 70}")
    print("K-MEANS ON BEHAVIORAL FEATURES")
    print(f"{'=' * 70}")
    for k in [5, 8, 10]:
        labels = kmeans(matrix, k)
        sizes = sorted([int((labels == ki).sum()) for ki in range(k)], reverse=True)
        print(f"\n  K={k}: sizes={sizes}")

        for ki in range(k):
            mask = labels == ki
            indices = np.where(mask)[0]
            # Mean features in cluster
            cluster_means = matrix[mask].mean(axis=0)
            top_features = [
                (feature_names[fi], cluster_means[fi])
                for fi in np.argsort(cluster_means)[::-1]
                if cluster_means[fi] > 0.01
            ][:5]
            feat_str = ", ".join(f"{n}={v:.2f}" for n, v in top_features)

            action_counts: dict[str, int] = {}
            for idx in indices:
                action_counts[parsed[idx]["action"]] = (
                    action_counts.get(parsed[idx]["action"], 0) + 1
                )
            top_actions = sorted(action_counts.items(), key=lambda x: -x[1])[:3]
            action_str = ", ".join(f"{a}:{c}" for a, c in top_actions)

            print(f"    Cluster {ki} ({int(mask.sum())}) [{action_str}]")
            print(f"      Features: {feat_str}")
            for idx in indices[:2]:
                print(f"      [{idx:3d}] {parsed[idx]['reasoning'][:90]}")


if __name__ == "__main__":
    main()
