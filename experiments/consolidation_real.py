"""
Run consolidation experiment on real diary data.

Changes from v1:
- Embed only the reasoning portion (after the action results line)
- Compare new cluster centroids against existing concept centroids to avoid duplicates
- Reinforce existing concepts instead of creating duplicates
- Track concept strength (reinforcement count)

Usage:
    PYTHONPATH=. uv run python experiments/consolidation_real.py [DB_PATH] [AGENT] [LLM_URL] [MODEL]
"""

import asyncio
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

from conwai.embeddings import FastEmbedder
from conwai.llm import LLMClient
from conwai.storage import SQLiteStorage


CLUSTER_THRESHOLD = 0.70  # tighter than before
CONCEPT_MERGE_THRESHOLD = 0.80  # if new cluster centroid is this close to existing concept, reinforce instead
MAX_CLUSTER_SIZE = 5
BOOST_FACTOR = 0.02
BOOST_DECAY = 0.995
BOOST_CAP = 0.15


def extract_reasoning(entry: str) -> str:
    """Pull out just the reasoning/intent portion of a diary entry.

    Diary entries look like:
        [Day 1, 9:00 AM] forage→foraged 7 flour, 2 water
        I am skeptical of doing nothing and will forage to build reserves...

    We want just the reasoning line(s), not the timestamp or action results.
    """
    lines = entry.strip().split("\n")
    # Skip the first line (timestamp + action results)
    reasoning_lines = []
    for line in lines[1:]:
        line = line.strip()
        if line:
            reasoning_lines.append(line)
    if reasoning_lines:
        return " ".join(reasoning_lines)
    # Fallback: use the whole thing if no reasoning found
    return entry


class ConsolidationMemory:
    def __init__(self, embedder: FastEmbedder, llm: LLMClient):
        self.embedder = embedder
        self.llm = llm
        self.entries: list[str] = []           # full diary text
        self.reasoning: list[str] = []         # reasoning-only (for embedding)
        self.vectors: list[np.ndarray] = []    # embeddings of reasoning
        self.concepts: list[dict] = []         # {label, centroid, entries, strength}
        self._boost: defaultdict[tuple[int, int], float] = defaultdict(float)

    def _pair_key(self, a: int, b: int) -> tuple[int, int]:
        return (min(a, b), max(a, b))

    def _sim(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))

    def _eff_sim(self, i: int, j: int) -> float:
        return self._sim(self.vectors[i], self.vectors[j]) + self._boost[self._pair_key(i, j)]

    def _top_neighbors(self, vec: np.ndarray, idx: int, k: int = 4) -> list[tuple[int, float]]:
        results = []
        for i, v in enumerate(self.vectors):
            if i == idx:
                continue
            eff = self._sim(vec, v) + self._boost[self._pair_key(idx, i)]
            if eff > CLUSTER_THRESHOLD:
                results.append((i, eff))
        results.sort(key=lambda x: -x[1])
        return results[:k]

    async def _label_cluster(self, indices: list[int]) -> str:
        texts = [self.reasoning[i] for i in indices]
        prompt = (
            "These are an agent's thoughts from different moments. "
            "What pattern or lesson connects them? "
            "ONE sentence — a general insight, no specific names or numbers.\n\n"
            + "\n".join(f"- {t[:200]}" for t in texts)
        )
        resp = await self.llm.call(
            "You extract behavioral patterns from experiences. Be concise and general.",
            [{"role": "user", "content": prompt}],
        )
        return resp.text.strip()

    def _find_matching_concept(self, centroid: np.ndarray) -> dict | None:
        """Find existing concept whose centroid is very close to this one."""
        for c in self.concepts:
            if self._sim(centroid, c["centroid"]) > CONCEPT_MERGE_THRESHOLD:
                return c
        return None

    async def add(self, full_text: str) -> dict | None:
        """Add an entry. Returns new or reinforced concept, or None."""
        reasoning = extract_reasoning(full_text)
        vec = np.array(self.embedder.embed([reasoning])[0])
        idx = len(self.entries)
        self.entries.append(full_text)
        self.reasoning.append(reasoning)
        self.vectors.append(vec)

        neighbors = self._top_neighbors(vec, idx=idx, k=MAX_CLUSTER_SIZE - 1)
        if not neighbors:
            return None

        # Build tightest cluster
        cluster = [idx, neighbors[0][0]]
        for other_idx, _ in neighbors[1:]:
            if len(cluster) >= MAX_CLUSTER_SIZE:
                break
            if all(self._eff_sim(other_idx, c) > CLUSTER_THRESHOLD for c in cluster):
                cluster.append(other_idx)

        if len(cluster) < 2:
            return None

        # Compute centroid of this cluster
        centroid = np.mean([self.vectors[i] for i in cluster], axis=0)

        # Check if this cluster matches an existing concept
        existing = self._find_matching_concept(centroid)
        if existing:
            # Reinforce: bump strength, update centroid toward new data
            existing["strength"] += 1
            # Running average of centroid
            n = existing["strength"]
            existing["centroid"] = existing["centroid"] * ((n - 1) / n) + centroid * (1 / n)
            # Add new entry indices (dedup)
            for i in cluster:
                if i not in existing["entries"]:
                    existing["entries"].append(i)
            return existing

        # New concept
        label = await self._label_cluster(cluster)
        concept = {
            "label": label,
            "centroid": centroid,
            "entries": sorted(cluster),
            "strength": 1,
        }
        self.concepts.append(concept)
        return concept

    def recall(self, query: str, top_k: int = 3) -> dict:
        qvec = np.array(self.embedder.embed([query])[0])

        episodes = []
        for i, v in enumerate(self.vectors):
            sim = self._sim(v, qvec)
            episodes.append((sim, i, self.entries[i]))
        episodes.sort(reverse=True)
        episodes = episodes[:top_k]

        concepts = []
        for c in self.concepts:
            raw_sim = self._sim(c["centroid"], qvec)
            # Strength boosts recall priority
            boosted_sim = raw_sim * (1 + 0.05 * min(c["strength"], 10))
            concepts.append((boosted_sim, raw_sim, c["label"], c["strength"], len(c["entries"])))
        concepts.sort(reverse=True)
        concepts = concepts[:top_k]

        # Hebbian reinforcement on co-recalled episodes
        recalled = [idx for _, idx, _ in episodes]
        for a in recalled:
            for b in recalled:
                if a < b:
                    key = self._pair_key(a, b)
                    self._boost[key] = min(self._boost[key] + BOOST_FACTOR, BOOST_CAP)
        for key in self._boost:
            self._boost[key] *= BOOST_DECAY

        return {
            "episodes": [(sim, text) for sim, _, text in episodes],
            "concepts": [(bsim, label, strength, size) for bsim, _, label, strength, size in concepts],
        }


async def main():
    db_path = sys.argv[1] if len(sys.argv) > 1 else "data.removed-auto.bak/state.db"
    agent = sys.argv[2] if len(sys.argv) > 2 else "Jeffery"
    llm_url = sys.argv[3] if len(sys.argv) > 3 else "http://ai-lab.lan:8081/v1"
    llm_model = sys.argv[4] if len(sys.argv) > 4 else "/mnt/models/Qwen3.5-27B-GPTQ-Int4"

    print(f"DB: {db_path}  Agent: {agent}")
    print(f"LLM: {llm_url} / {llm_model}")

    storage = SQLiteStorage(path=Path(db_path))
    brain_data = storage.load_component(agent, "brain")
    if not brain_data:
        print(f"No brain data for {agent}")
        return

    diary = brain_data.get("diary", [])
    raw_entries = [e["content"] for e in diary]
    print(f"Diary: {len(raw_entries)} entries\n")

    # Show what reasoning extraction does
    print("Sample reasoning extraction:")
    for i in range(min(3, len(raw_entries))):
        r = extract_reasoning(raw_entries[i])
        print(f"  [{i}] FULL: {raw_entries[i][:70]}")
        print(f"      REASONING: {r[:70]}")
    print()

    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    llm = LLMClient(base_url=llm_url, model=llm_model, max_tokens=100)
    memory = ConsolidationMemory(embedder, llm)

    # Phase 1: Add entries
    print(f"{'='*70}")
    print(f"ADDING {len(raw_entries)} ENTRIES")
    print(f"{'='*70}\n")

    for i, entry in enumerate(raw_entries):
        result = await memory.add(entry)
        if result:
            is_new = result["strength"] == 1
            tag = "NEW" if is_new else f"REINFORCED (x{result['strength']})"
            print(f"  [{i:2d}] {tag}: \"{result['label'][:80]}\"")

    print(f"\n  {len(memory.entries)} episodes → {len(memory.concepts)} concepts\n")

    # Phase 2: Show concepts sorted by strength
    print(f"{'='*70}")
    print(f"CONCEPTS (sorted by strength)")
    print(f"{'='*70}\n")

    by_strength = sorted(memory.concepts, key=lambda c: -c["strength"])
    for c in by_strength:
        print(f"  [strength={c['strength']:2d}, entries={len(c['entries']):2d}] \"{c['label'][:85]}\"")
    print()

    # Phase 3: Query test
    print(f"{'='*70}")
    print("QUERY TEST")
    print(f"{'='*70}\n")

    queries = [
        "Someone wants to trade with me, should I trust them?",
        "I'm starving and need food urgently",
        "Who has been reliable in past trades?",
        "Should I forage or try to trade?",
        "Christopher wants to trade again",
        "I have surplus flour but need water",
    ]

    for q in queries:
        result = memory.recall(q)
        print(f"Q: \"{q}\"")
        if result["episodes"]:
            print(f"  Episode: {result['episodes'][0][0]:.3f}  {result['episodes'][0][1][:60]}")
        if result["concepts"]:
            c = result["concepts"][0]
            print(f"  Concept: {c[0]:.3f}  [str={c[2]}, {c[3]} entries] {c[1][:55]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
