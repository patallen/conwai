"""
Experiment 0007: Batch LLM abstracts — 10 entries per call.

Same approach as 0004 but sending 10 entries per LLM call to reduce
API calls from 251 to 26. Tests whether batch abstracts are as good
as individual ones.

Usage:
    PYTHONPATH=. uv run python experiments/0007-batch-abstracts/run.py
"""

import json
import re
from pathlib import Path

import httpx
import numpy as np

from conwai.llm import FastEmbedder
from conwai.storage import SQLiteStorage

DB_PATH = "data.pre-abliterated.bak/state.db"
AGENT = "Helen"
LLM_BASE = "http://ai-lab.lan:8081/v1"
LLM_MODEL = "/mnt/models/Qwen3.5-27B-GPTQ-Int4"
BATCH_SIZE = 10
THRESHOLDS = [0.65, 0.70, 0.75, 0.80]

_ACTION_RE = re.compile(r"\] (\w+)→")

BATCH_PROMPT = """You are analyzing diary entries from an AI agent in a resource management simulation. For EACH entry below, describe the BEHAVIORAL PATTERN in exactly 5-10 words. Focus on the underlying strategy or motivation, not the specific resources or agent names.

Examples of good abstracts:
- "Desperate survival trade under starvation pressure"
- "Cautious inspection before committing to trade"
- "Routine resource gathering to maintain surplus"

Entries:
{entries}

For each entry, respond with ONLY the entry number and abstract, one per line:
1: <abstract>
2: <abstract>
...

No other text."""


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def llm_batch(client: httpx.Client, entries: list[str]) -> list[str]:
    formatted = "\n".join(f"{i + 1}. {e[:200]}" for i, e in enumerate(entries))
    resp = client.post(
        f"{LLM_BASE}/chat/completions",
        json={
            "model": LLM_MODEL,
            "messages": [
                {"role": "user", "content": BATCH_PROMPT.format(entries=formatted)}
            ],
            "max_tokens": 1000,
            "temperature": 0.3,
            "chat_template_kwargs": {"enable_thinking": False},
        },
        timeout=60,
    )
    resp.raise_for_status()
    content = resp.json()["choices"][0]["message"].get("content") or ""

    # Parse numbered responses
    abstracts = ["unknown pattern"] * len(entries)
    for line in content.strip().split("\n"):
        line = line.strip()
        if ":" in line:
            parts = line.split(":", 1)
            try:
                num = int(parts[0].strip().rstrip("."))
                if 1 <= num <= len(entries):
                    abstracts[num - 1] = parts[1].strip().strip('"')
            except ValueError:
                pass

    return abstracts


def cluster_centroid(vectors: list[np.ndarray], threshold: float) -> list[list[int]]:
    clusters: list[list[int]] = []
    centroids: list[np.ndarray] = []
    for idx, vec in enumerate(vectors):
        best_ci, best_sim = -1, -1.0
        for ci, c in enumerate(centroids):
            sim = float(
                np.dot(vec, c) / (np.linalg.norm(vec) * np.linalg.norm(c) + 1e-10)
            )
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
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    sim = (vectors / norms) @ (vectors / norms).T
    upper = sim[np.triu_indices(len(vectors), k=1)]
    return {"mean": float(np.mean(upper)), "std": float(np.std(upper))}


def main() -> None:
    storage = SQLiteStorage(path=Path(DB_PATH))
    brain = storage.load_component(AGENT, "brain")
    diary = brain.get("diary", [])
    print(f"Loaded {len(diary)} entries\n")

    parsed = []
    for e in diary:
        action, reasoning = parse_entry(e["content"])
        parsed.append({"action": action, "reasoning": reasoning, "raw": e["content"]})

    # Get batch abstracts
    cache_path = Path("experiments/0007-batch-abstracts/abstracts_cache.json")
    if cache_path.exists():
        print("Loading cached abstracts...")
        abstracts = json.loads(cache_path.read_text())
    else:
        print(f"Generating batch abstracts ({BATCH_SIZE} per call)...")
        abstracts: list[str] = []
        client = httpx.Client()
        n_calls = 0
        for batch_start in range(0, len(parsed), BATCH_SIZE):
            batch = [
                p["raw"][:300] for p in parsed[batch_start : batch_start + BATCH_SIZE]
            ]
            batch_abstracts = llm_batch(client, batch)
            abstracts.extend(batch_abstracts)
            n_calls += 1
            print(
                f"  Call {n_calls}: entries {batch_start}-{batch_start + len(batch) - 1}"
            )
            for i, a in enumerate(batch_abstracts[:3]):
                print(f"    [{batch_start + i}] {a}")

        client.close()
        cache_path.write_text(json.dumps(abstracts))
        print(f"\n  Total LLM calls: {n_calls} (vs 251 for individual)")

    # Compare with 0004's individual abstracts
    individual_cache = Path(
        "experiments/0004-llm-behavioral-abstract/abstracts_cache.json"
    )
    if individual_cache.exists():
        individual = json.loads(individual_cache.read_text())
        print("\nComparison (batch vs individual, first 10):")
        for i in range(min(10, len(abstracts))):
            print(f"  [{i}] batch:      {abstracts[i][:80]}")
            print(f"       individual: {individual[i][:80]}")
    print()

    # Embed abstracts
    print("Embedding batch abstracts...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    raw_vecs = embedder.embed(abstracts)
    vectors = np.array(raw_vecs)

    stats = pairwise_stats(vectors)
    print(f"Pairwise similarity: mean={stats['mean']:.4f} std={stats['std']:.4f}")
    print("(Compare: 0004 individual mean=0.6856 std=0.0913)")
    print()

    # Cluster at multiple thresholds
    for threshold in THRESHOLDS:
        vec_list = [vectors[i] for i in range(len(vectors))]
        clusters = cluster_centroid(vec_list, threshold)
        clusters_sorted = sorted(clusters, key=lambda c: -len(c))
        sizes = [len(c) for c in clusters_sorted]
        non_singleton = sum(1 for s in sizes if s > 1)

        print(f"{'=' * 70}")
        print(
            f"THRESHOLD {threshold:.2f}: {len(clusters)} clusters ({non_singleton} non-singleton)"
        )
        print(f"{'=' * 70}")
        print(f"  Sizes: {sizes[:15]}{'...' if len(sizes) > 15 else ''}")

        if 5 <= len(clusters) <= 20:
            for ci, cluster in enumerate(clusters_sorted[:10]):
                abs_counts: dict[str, int] = {}
                for idx in cluster:
                    a = abstracts[idx]
                    abs_counts[a] = abs_counts.get(a, 0) + 1
                top = sorted(abs_counts.items(), key=lambda x: -x[1])[:3]
                top_str = "; ".join(f"{a}({n})" for a, n in top)
                print(f"  Cluster {ci + 1} (size={len(cluster)}): {top_str}")
        print()


if __name__ == "__main__":
    main()
