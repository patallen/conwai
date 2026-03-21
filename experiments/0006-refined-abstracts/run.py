"""
Experiment 0006: Refined abstracts with two-tier categorization.

Instead of one 5-10 word abstract, ask the LLM for:
1. A category (3 words max): the broad behavioral type
2. A pattern (5-10 words): the specific motivation

Then embed the category for clustering (tighter grouping) and use the
pattern as the cluster label.

Also uses a more specific prompt to split the "reject risky trade" mega-cluster.

Usage:
    PYTHONPATH=. uv run python experiments/0006-refined-abstracts/run.py
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
THRESHOLDS = [0.70, 0.75, 0.80, 0.85, 0.90]

_ACTION_RE = re.compile(r"\] (\w+)→")

ABSTRACT_PROMPT = """Analyze this diary entry from an AI agent in a resource simulation. Provide two things:

CATEGORY (exactly 2-3 words): The broad behavioral type. Choose from categories like:
- survival crisis
- cautious verification
- strategic rejection
- fair exchange
- proactive stockpiling
- desperate acquisition
- public signaling
- trust building
- self-reliant production
- community governance
- emergency spending
- competitive positioning
Or create a new category if none fit.

PATTERN (5-10 words): The specific behavioral motivation in this entry.

Entry:
{entry}

Respond in exactly this format (no other text):
CATEGORY: <category>
PATTERN: <pattern>"""


def parse_entry(content: str) -> tuple[str, str]:
    lines = content.strip().split("\n")
    m = _ACTION_RE.search(lines[0])
    action = m.group(1) if m else "unknown"
    reasoning = " ".join(l.strip() for l in lines[1:] if l.strip()) or lines[0]
    return action, reasoning


def llm_abstract(client: httpx.Client, entry_text: str) -> tuple[str, str]:
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
    content = resp.json()["choices"][0]["message"].get("content") or ""

    category = "unknown"
    pattern = "unknown pattern"
    for line in content.strip().split("\n"):
        line = line.strip()
        if line.upper().startswith("CATEGORY:"):
            category = line.split(":", 1)[1].strip().lower()
        elif line.upper().startswith("PATTERN:"):
            pattern = line.split(":", 1)[1].strip()

    return category, pattern


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

    # Get two-tier abstracts
    cache_path = Path("experiments/0006-refined-abstracts/abstracts_cache.json")
    if cache_path.exists():
        print("Loading cached abstracts...")
        cached = json.loads(cache_path.read_text())
        categories = cached["categories"]
        patterns = cached["patterns"]
    else:
        print("Generating two-tier abstracts via LLM...")
        categories: list[str] = []
        patterns: list[str] = []
        client = httpx.Client()
        for i, p in enumerate(parsed):
            cat, pat = llm_abstract(client, p["raw"])
            categories.append(cat)
            patterns.append(pat)
            if i % 25 == 0:
                print(f"  [{i}/{len(parsed)}] {cat} → {pat}")
        client.close()
        cache_path.write_text(json.dumps({"categories": categories, "patterns": patterns}))
        print(f"  Saved {len(categories)} abstracts to cache")

    # Show category distribution
    cat_counts: dict[str, int] = {}
    for c in categories:
        cat_counts[c] = cat_counts.get(c, 0) + 1
    print(f"\nCategory distribution ({len(cat_counts)} unique categories):")
    for cat, count in sorted(cat_counts.items(), key=lambda x: -x[1]):
        print(f"  {cat:30s} {count:4d}")

    # Embed CATEGORIES (shorter, should cluster tighter)
    print("\nEmbedding categories...")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    cat_vecs = np.array(embedder.embed(categories))
    stats = pairwise_stats(cat_vecs)
    print(f"Category embeddings: mean={stats.get('mean',0):.4f} std={stats.get('std',0):.4f}")

    # Also embed patterns for comparison
    pat_vecs = np.array(embedder.embed(patterns))
    stats2 = pairwise_stats(pat_vecs)
    print(f"Pattern embeddings:  mean={stats2.get('mean',0):.4f} std={stats2.get('std',0):.4f}")
    print(f"(Compare: raw reasoning mean=0.7972, 0004 abstracts mean=0.6856)")

    # Cluster categories at various thresholds
    print(f"\n{'='*70}")
    print("CLUSTERING ON CATEGORY EMBEDDINGS")
    print(f"{'='*70}")
    for threshold in THRESHOLDS:
        vec_list = [cat_vecs[i] for i in range(len(cat_vecs))]
        clusters = cluster_centroid(vec_list, threshold)
        clusters_sorted = sorted(clusters, key=lambda c: -len(c))
        sizes = [len(c) for c in clusters_sorted]
        print(f"\n  threshold={threshold:.2f}: {len(clusters)} clusters, sizes={sizes[:15]}{'...' if len(sizes) > 15 else ''}")

        if 5 <= len(clusters) <= 20:
            for ci, cluster in enumerate(clusters_sorted[:10]):
                cluster_cats: dict[str, int] = {}
                for idx in cluster:
                    cluster_cats[categories[idx]] = cluster_cats.get(categories[idx], 0) + 1
                top_cats = sorted(cluster_cats.items(), key=lambda x: -x[1])[:3]
                cats_str = ", ".join(f"{c}({n})" for c, n in top_cats)
                print(f"    Cluster {ci+1} (size={len(cluster)}): {cats_str}")

    # Also cluster on pattern embeddings
    print(f"\n{'='*70}")
    print("CLUSTERING ON PATTERN EMBEDDINGS")
    print(f"{'='*70}")
    for threshold in THRESHOLDS:
        vec_list = [pat_vecs[i] for i in range(len(pat_vecs))]
        clusters = cluster_centroid(vec_list, threshold)
        sizes = sorted([len(c) for c in clusters], reverse=True)
        non_singleton = sum(1 for s in sizes if s > 1)
        print(f"  threshold={threshold:.2f}: {len(clusters)} clusters ({non_singleton} non-singleton)")


if __name__ == "__main__":
    main()
