"""
Experiment 0004: LLM-extracted behavioral abstracts.

For each diary entry, ask the LLM to describe the behavioral pattern in 5-10
words, then embed and cluster the abstracts.

Hypothesis: LLM-generated abstracts capture the WHY (behavioral pattern) rather
than the WHAT (specific resources/agents), producing embeddings that cluster
into meaningful behavioral categories.

Usage:
    PYTHONPATH=. uv run python experiments/0004-llm-behavioral-abstract/run.py
"""

import json
import re
from pathlib import Path

import httpx
import numpy as np

from conwai.embeddings import FastEmbedder
from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"
LLM_BASE = "http://ai-lab.lan:8081/v1"
LLM_MODEL = "/mnt/models/Qwen3.5-27B-GPTQ-Int4"
THRESHOLDS = [0.60, 0.65, 0.70, 0.75, 0.80]

_ACTION_RE = re.compile(r"\] (\w+)→")

ABSTRACT_PROMPT = """You are analyzing diary entries from an AI agent in a resource management simulation. For the entry below, describe the BEHAVIORAL PATTERN in exactly 5-10 words. Focus on the underlying strategy or motivation, not the specific resources or agent names.

Examples of good abstracts:
- "Desperate survival trade under starvation pressure"
- "Cautious inspection before committing to trade"
- "Routine resource gathering to maintain surplus"
- "Rejecting unfair offer to preserve negotiating position"
- "Building public reputation through board communication"

Diary entry:
{entry}

Respond with ONLY the 5-10 word behavioral pattern, nothing else. Do not use quotes."""


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def llm_abstract(client: httpx.Client, entry_text: str) -> str:
    """Get a 5-10 word behavioral abstract from the LLM."""
    resp = client.post(
        f"{LLM_BASE}/chat/completions",
        json={
            "model": LLM_MODEL,
            "messages": [{"role": "user", "content": ABSTRACT_PROMPT.format(entry=entry_text)}],
            "max_tokens": 200,
            "temperature": 0.3,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout=30,
    )
    resp.raise_for_status()
    data = resp.json()
    content = data["choices"][0]["message"].get("content") or ""
    # Qwen3.5 may use reasoning_content; fall back to that
    if not content:
        content = data["choices"][0]["message"].get("reasoning_content") or "unknown pattern"
    return content.strip().strip('"')


def cluster_centroid(vectors: list[np.ndarray], threshold: float) -> list[list[int]]:
    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []
    for idx, vec in enumerate(vectors):
        best_ci, best_sim = -1, -1.0
        for ci, c in enumerate(centroids):
            sim = float(np.dot(vec, c) / (np.linalg.norm(vec) * np.linalg.norm(c) + 1e-10))
            if sim > best_sim:
                best_sim = sim
                best_ci = ci
        if best_ci >= 0 and best_sim >= threshold:
            clusters[best_ci].append(idx)
            n = len(clusters[best_ci])
            centroids[best_ci] = centroids[best_ci] * ((n - 1) / n) + vec / n
        else:
            clusters.append([idx])
            centroids.append(vec.copy())
    return clusters


def pairwise_stats(vectors: np.ndarray) -> dict:
    if len(vectors) < 2:
        return {}
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sim = (vectors / norms) @ (vectors / norms).T
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {
        "mean": float(np.mean(upper)),
        "std": float(np.std(upper)),
        "min": float(np.min(upper)),
        "max": float(np.max(upper)),
    }


def main() -> None:
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries\n")

    # Parse entries
    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning, "raw": e["content"]})

    # Get LLM abstracts for all entries
    print("Generating behavioral abstracts via LLM...")
    abstracts: list[str] = []
    client = httpx.Client()

    # Cache file to avoid re-running LLM on subsequent runs
    cache_path = Path("experiments/0004-llm-behavioral-abstract/abstracts_cache.json")
    if cache_path.exists():
        print("  Loading from cache...")
        with open(cache_path) as f:
            abstracts = json.load(f)
        print(f"  Loaded {len(abstracts)} cached abstracts")
    else:
        for i, p in enumerate(parsed):
            abstract = llm_abstract(client, p["raw"])
            abstracts.append(abstract)
            if i % 25 == 0:
                print(f"  [{i}/{len(parsed)}] {abstract}")

        # Save cache
        with open(cache_path, "w") as f:
            json.dump(abstracts, f, indent=2)
        print(f"  Saved {len(abstracts)} abstracts to cache")

    client.close()

    # Show sample abstracts
    print(f"\nSample abstracts (every 25th):")
    for i in range(0, len(abstracts), 25):
        print(f"  [{i:3d}] {parsed[i]['action']:15s} → {abstracts[i]}")
    print()

    # Embed the abstracts
    print("Embedding abstracts...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    raw_vecs = embedder.embed(abstracts)
    vectors = np.array(raw_vecs)
    print(f"Shape: {vectors.shape}\n")

    # Pairwise stats on abstracts
    stats = pairwise_stats(vectors)
    print(f"Pairwise similarity of abstracts:")
    print(f"  mean={stats['mean']:.4f} std={stats['std']:.4f} "
          f"min={stats['min']:.4f} max={stats['max']:.4f}")
    print(f"  (Compare to raw reasoning: mean=0.7972 std=0.0745)")
    print()

    # Cluster at multiple thresholds
    for threshold in THRESHOLDS:
        vec_list = [vectors[i] for i in range(len(vectors))]
        clusters = cluster_centroid(vec_list, threshold)
        clusters_sorted = sorted(clusters, key=lambda c: -len(c))
        sizes = [len(c) for c in clusters_sorted]

        print(f"{'='*70}")
        print(f"THRESHOLD {threshold:.2f}: {len(clusters)} clusters")
        print(f"{'='*70}")
        print(f"  Sizes: {sizes[:20]}{'...' if len(sizes) > 20 else ''}")

        # Show clusters with their abstracts
        for ci, cluster in enumerate(clusters_sorted[:10]):
            # Group abstracts in this cluster
            cluster_abstracts: dict[str, int] = {}
            for idx in cluster:
                a = abstracts[idx]
                cluster_abstracts[a] = cluster_abstracts.get(a, 0) + 1
            top_abstracts = sorted(cluster_abstracts.items(), key=lambda x: -x[1])

            print(f"\n  Cluster {ci+1} (size={len(cluster)}):")
            for abstract, count in top_abstracts[:5]:
                print(f"    [{count:2d}x] {abstract}")
            if len(top_abstracts) > 5:
                print(f"    ... and {len(top_abstracts)-5} more unique abstracts")
        print()

    # Find the best threshold (5-15 clusters, non-trivial)
    print(f"\n{'='*70}")
    print("BEST THRESHOLD ANALYSIS")
    print(f"{'='*70}")
    for threshold in THRESHOLDS:
        vec_list = [vectors[i] for i in range(len(vectors))]
        clusters = cluster_centroid(vec_list, threshold)
        non_singleton = [c for c in clusters if len(c) > 1]
        print(f"  {threshold:.2f}: {len(clusters)} total, {len(non_singleton)} non-singleton")


if __name__ == "__main__":
    main()
