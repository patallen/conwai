"""
Experiment 0035: Extract structured (condition, behavior) tuples, embed THOSE.

Instead of embedding raw prose, extract:
  condition: resource state (zero bread, surplus flour, etc)
  behavior: what the agent decided (forage, bake, reject offer, accept deal)

Then embed the TUPLE as a short string and cluster. Entries with the same
condition→behavior pattern should land together regardless of prose style.

The consolidated knowledge IS the recurring tuple.

Usage:
    PYTHONPATH=. uv run python experiments/0035-structured-tuples/run.py
"""

import json
import re
from collections import Counter
from pathlib import Path

import numpy as np

from conwai.llm import FastEmbedder

CACHE_PARSED = Path("experiments/helen_parsed.json")

# Resource state extraction
CRISIS_PATTERNS = [
    (r"zero bread", "zero_bread"),
    (r"critically (?:low|starving)", "crisis"),
    (r"starving", "starving"),
    (r"no bread", "zero_bread"),
    (r"zero flour", "zero_flour"),
    (r"zero water", "zero_water"),
    (r"only \d flour", "low_flour"),
    (r"only \d water", "low_water"),
    (r"only \d bread", "low_bread"),
]

STABILITY_PATTERNS = [
    (r"surplus (?:of )?(?:flour|water|bread)", "surplus"),
    (r"stable", "stable"),
    (r"secured", "secured"),
    (r"ample", "ample"),
    (r"sufficient", "sufficient"),
    (r"\d{2,}\s+flour", "high_flour"),
    (r"\d{2,}\s+water", "high_water"),
    (r"\d{2,}\s+bread", "high_bread"),
]

BEHAVIOR_PATTERNS = [
    (r"I will forage", "forage"),
    (r"I (?:will|must) (?:immediately )?bake", "bake"),
    (r"I will accept", "accept_trade"),
    (r"I will decline|I will reject|I will ignore|I will not accept", "reject_trade"),
    (r"I (?:will|must) (?:immediately )?(?:send|DM)", "send_message"),
    (r"I will offer|I will propose", "make_offer"),
    (r"I will inspect", "inspect"),
    (r"I will vote", "vote"),
    (r"I will post", "post_board"),
    (r"I will pay|I will use.*coins", "spend_coins"),
    (r"abandon(?:ing)? my (?:usual|skeptical)", "abandon_caution"),
    (r"prioritiz(?:e|ing) (?:immediate|survival)", "prioritize_survival"),
    (r"my strategy (?:demands|dictates|forbids|prioritizes)", "follow_strategy"),
]

REASON_PATTERNS = [
    (r"(?:because|since|as) .*(?:starving|zero bread|critical)", "because_starving"),
    (r"(?:because|since|as) .*(?:skeptical|verify|reliability)", "because_skeptical"),
    (r"(?:because|since|as) .*(?:surplus|ample|sufficient)", "because_surplus"),
    (r"(?:because|since|as) .*(?:unfavorable|predatory|bad rate)", "because_bad_rate"),
    (r"(?:because|since|as) .*(?:strategy|priorit)", "because_strategy"),
]


def extract_tuple(reasoning: str) -> dict:
    """Extract structured (condition, behavior, reason) from entry."""
    text = reasoning.lower()

    conditions = []
    for pattern, label in CRISIS_PATTERNS:
        if re.search(pattern, text):
            conditions.append(label)
    for pattern, label in STABILITY_PATTERNS:
        if re.search(pattern, text):
            conditions.append(label)

    behaviors = []
    for pattern, label in BEHAVIOR_PATTERNS:
        if re.search(pattern, text):
            behaviors.append(label)

    reasons = []
    for pattern, label in REASON_PATTERNS:
        if re.search(pattern, text):
            reasons.append(label)

    return {
        "conditions": sorted(set(conditions)),
        "behaviors": sorted(set(behaviors)),
        "reasons": sorted(set(reasons)),
    }


def tuple_to_string(t: dict) -> str:
    """Convert tuple to embeddable string."""
    parts = []
    if t["conditions"]:
        parts.append("WHEN " + " AND ".join(t["conditions"]))
    if t["behaviors"]:
        parts.append("DO " + " AND ".join(t["behaviors"]))
    if t["reasons"]:
        parts.append("BECAUSE " + " AND ".join(t["reasons"]))
    return " ".join(parts) if parts else "no_pattern_detected"


def pairwise_stats(vectors: np.ndarray) -> dict:
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sim = (vectors / norms) @ (vectors / norms).T
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {"mean": float(np.mean(upper)), "std": float(np.std(upper))}


def kmeans_cosine(vectors: np.ndarray, k: int, seed: int = 42) -> np.ndarray:
    from sklearn.cluster import KMeans

    km = KMeans(n_clusters=k, random_state=seed, n_init=10)
    return km.fit_predict(vectors)


def main() -> None:
    parsed = json.loads(CACHE_PARSED.read_text())
    print(f"Loaded {len(parsed)} entries\n")

    # Extract tuples
    tuples = [extract_tuple(p["reasoning"]) for p in parsed]
    tuple_strings = [tuple_to_string(t) for t in tuples]

    # Show distribution
    print("Sample tuples:")
    for i in [0, 18, 50, 77, 94, 150, 200, 243]:
        if i < len(parsed):
            print(f"  [{i:3d}] [{parsed[i]['action']}] {tuple_strings[i]}")
            print(f"         {parsed[i]['reasoning'][:80]}")
    print()

    # Count unique tuple strings
    tuple_counts = Counter(tuple_strings)
    print(f"Unique tuple strings: {len(tuple_counts)}")
    print("\nMost common tuples:")
    for ts, count in tuple_counts.most_common(20):
        print(f"  {count:3d}x  {ts}")

    # Entries with no pattern detected
    no_pattern = sum(1 for ts in tuple_strings if ts == "no_pattern_detected")
    print(f"\nNo pattern detected: {no_pattern}/{len(parsed)}")

    # THESE TUPLES ARE THE CONSOLIDATED KNOWLEDGE
    # If a tuple appears N times, it's a pattern reinforced by N episodes
    print(f"\n{'=' * 70}")
    print("CONSOLIDATED PATTERNS (tuples appearing 3+ times)")
    print(f"{'=' * 70}")
    for ts, count in tuple_counts.most_common():
        if count >= 3:
            # Find example entries
            examples = [i for i, s in enumerate(tuple_strings) if s == ts]
            print(f"\n  PATTERN ({count} episodes): {ts}")
            for idx in examples[:3]:
                print(f"    [{idx:3d}] {parsed[idx]['reasoning'][:100]}")

    # Embed tuples and see if they cluster
    print(f"\n{'=' * 70}")
    print("EMBEDDING TUPLE STRINGS")
    print(f"{'=' * 70}")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    # Only embed non-empty tuples
    valid_indices = [
        i for i, ts in enumerate(tuple_strings) if ts != "no_pattern_detected"
    ]
    valid_strings = [tuple_strings[i] for i in valid_indices]
    if valid_strings:
        vecs = np.array(embedder.embed(valid_strings))
        stats = pairwise_stats(vecs)
        print(f"Tuple embeddings: mean={stats['mean']:.4f} std={stats['std']:.4f}")
        print("(Compare: raw reasoning mean=0.7972)")

        from sklearn.metrics import silhouette_score

        for k in [5, 8, 10, 15]:
            labels = kmeans_cosine(vecs, k)
            sil = silhouette_score(vecs, labels, metric="cosine")
            sizes = sorted([int((labels == ki).sum()) for ki in range(k)], reverse=True)
            print(f"  K={k}: sil={sil:.4f} sizes={sizes}")


if __name__ == "__main__":
    main()
