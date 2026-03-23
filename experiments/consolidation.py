"""
Experiment: incremental episodic memory consolidation with Hebbian reinforcement.

Entries arrive one at a time. Clusters form (max 5), LLM labels them.
Entries can belong to multiple concepts. Co-recalled items get boosted.
"""

import asyncio
import sys
from collections import defaultdict

import numpy as np

from conwai.embeddings import FastEmbedder
from conwai.llm import LLMClient

CLUSTER_THRESHOLD = 0.65
MAX_CLUSTER_SIZE = 5
BOOST_FACTOR = 0.02
BOOST_DECAY = 0.995  # slight decay each recall cycle to prevent runaway
BOOST_CAP = 0.15  # max boost between any pair

ENTRIES = [
    # Day 1
    "Foraged and got 20 flour and 3 water, decent haul",
    "Posted on board looking for trade partners, no responses yet",
    "Christopher offered 20 flour for 20 water then backed out of the deal",
    "Traded 30 flour for 30 water with Bridget, fair deal completed",
    "Foraged 15 flour, need to bake soon before bread runs out",
    "Baked 8 bread from 10 flour and 10 water, stabilized hunger",
    # Day 2
    "Angel promised 10 bread but never delivered, wasted my tick",
    "Bridget sent 15 bread as promised, reliable partner",
    "Zero bread, eating raw flour, hunger dropping fast",
    "Matthew agreed to trade then changed his mind at the last moment",
    # Day 3
    "Completed a smooth 1:1 flour-water swap with Bridget, no issues",
    "Debra said she'd send water but disappeared after I sent flour",
    "Critically low on water, can't bake, need to trade urgently",
    "Election started, voted for Bridget because she's reliable",
    # Day 4
    "Board is full of desperate offers, nobody has bread",
    "Starving with 100 flour and no water, useless surplus",
    "Bad forage day, found nothing, wasted a tick",
]

# Queries that simulate what an agent might encounter over several days
QUERY_SEQUENCE = [
    # Day 2 morning: reflecting on trades
    "A new agent is offering me a deal, should I accept?",
    # Day 2 afternoon: food crisis
    "I'm running out of bread and need to eat",
    # Day 3 morning: another trade offer
    "Someone wants to trade flour for water with me",
    # Day 3 afternoon: thinking about partners
    "Who can I trust to actually follow through on trades?",
    # Day 4: Christopher returns
    "Christopher is back and wants to trade again",
    # Day 4: another food crisis
    "I have no bread and my hunger is critical",
    # Day 5: reflecting on who to work with
    "I need to decide who my long-term trading partners should be",
    # Day 5: another new agent offers a deal
    "A stranger is offering me a very generous trade deal",
]


class ConsolidationMemory:
    def __init__(self, embedder: FastEmbedder, llm: LLMClient):
        self.embedder = embedder
        self.llm = llm
        self.entries: list[str] = []
        self.vectors: list[np.ndarray] = []
        self.concepts: list[dict] = []
        # Hebbian boost: (i, j) -> float where i < j
        self._boost: defaultdict[tuple[int, int], float] = defaultdict(float)

    def _pair_key(self, a: int, b: int) -> tuple[int, int]:
        return (min(a, b), max(a, b))

    def _similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-10))

    def _effective_similarity(self, i: int, j: int) -> float:
        raw = self._similarity(self.vectors[i], self.vectors[j])
        boost = self._boost[self._pair_key(i, j)]
        return raw + boost

    def _top_neighbors(
        self, vec: np.ndarray, idx: int, k: int = 4
    ) -> list[tuple[int, float]]:
        results = []
        for i, v in enumerate(self.vectors):
            if i == idx:
                continue
            raw_sim = self._similarity(vec, v)
            boost = self._boost[self._pair_key(idx, i)]
            eff_sim = raw_sim + boost
            if eff_sim > CLUSTER_THRESHOLD:
                results.append((i, eff_sim))
        results.sort(key=lambda x: -x[1])
        return results[:k]

    async def _label_cluster(self, indices: list[int]) -> str:
        texts = [self.entries[i] for i in indices]
        prompt = (
            "These are memories from the same agent's diary. "
            "What pattern or lesson connects them? "
            "Respond with ONE sentence — a general rule or insight, no names.\n\n"
            + "\n".join(f"- {t}" for t in texts)
        )
        resp = await self.llm.call(
            "You extract patterns from experiences. Be concise.",
            [{"role": "user", "content": prompt}],
        )
        return resp.text.strip()

    async def add(self, text: str) -> list[dict]:
        vec = np.array(self.embedder.embed([text])[0])
        idx = len(self.entries)
        self.entries.append(text)
        self.vectors.append(vec)

        neighbors = self._top_neighbors(vec, idx=idx, k=MAX_CLUSTER_SIZE - 1)
        if not neighbors:
            return []

        new_concepts = []
        used = set()

        for neighbor_idx, neighbor_sim in neighbors:
            if neighbor_idx in used:
                continue

            cluster = [idx, neighbor_idx]
            for other_idx, other_sim in neighbors:
                if other_idx == neighbor_idx or other_idx in used:
                    continue
                if len(cluster) >= MAX_CLUSTER_SIZE:
                    break
                if all(
                    self._effective_similarity(other_idx, c) > CLUSTER_THRESHOLD
                    for c in cluster
                ):
                    cluster.append(other_idx)

            if len(cluster) < 2:
                continue

            cluster_set = set(cluster)
            redundant = False
            for existing in self.concepts:
                if cluster_set.issubset(set(existing["entries"])):
                    redundant = True
                    break
            if redundant:
                continue

            label = await self._label_cluster(cluster)
            centroid = np.mean([self.vectors[i] for i in cluster], axis=0)

            concept = {
                "label": label,
                "centroid": centroid,
                "entries": sorted(cluster),
            }
            self.concepts.append(concept)
            new_concepts.append(concept)
            used.update(cluster)

        return new_concepts

    def recall(
        self, query: str, top_k_episodes: int = 3, top_k_concepts: int = 3
    ) -> dict:
        qvec = np.array(self.embedder.embed([query])[0])

        # Episode recall
        episodes = []
        if self.vectors:
            for i, v in enumerate(self.vectors):
                sim = self._similarity(v, qvec)
                episodes.append((sim, i, self.entries[i]))
            episodes.sort(reverse=True)
            episodes = episodes[:top_k_episodes]

        # Concept recall
        concepts = []
        for ci, c in enumerate(self.concepts):
            sim = self._similarity(c["centroid"], qvec)
            concepts.append((sim, ci, c["label"], len(c["entries"])))
        concepts.sort(reverse=True)
        concepts = concepts[:top_k_concepts]

        # Hebbian reinforcement: boost co-recalled items
        recalled_episode_indices = [idx for _, idx, _ in episodes]
        recalled_concept_indices = [ci for _, ci, _, _ in concepts]

        # Boost episodes that were recalled together
        for a in recalled_episode_indices:
            for b in recalled_episode_indices:
                if a < b:
                    key = self._pair_key(a, b)
                    self._boost[key] = min(
                        self._boost[key] + BOOST_FACTOR,
                        BOOST_CAP,
                    )

        # Boost episodes within recalled concepts
        for ci in recalled_concept_indices:
            concept_entries = self.concepts[ci]["entries"]
            for a in concept_entries:
                for b in concept_entries:
                    if a < b:
                        key = self._pair_key(a, b)
                        self._boost[key] = min(
                            self._boost[key]
                            + BOOST_FACTOR
                            * 0.5,  # lighter boost for concept membership
                            BOOST_CAP,
                        )

        # Decay all boosts slightly
        for key in self._boost:
            self._boost[key] *= BOOST_DECAY

        return {
            "episodes": [(sim, text) for sim, _, text in episodes],
            "concepts": [(sim, label, size) for sim, _, label, size in concepts],
        }

    def print_boosts(self, min_boost: float = 0.005):
        """Show which pairs have been reinforced."""
        boosts = [(k, v) for k, v in self._boost.items() if v > min_boost]
        boosts.sort(key=lambda x: -x[1])
        if not boosts:
            print("  (no significant boosts)")
            return
        for (i, j), b in boosts[:15]:
            print(
                f"  {b:.4f}  [{i:2d}]-[{j:2d}]  {self.entries[i][:35]} <-> {self.entries[j][:35]}"
            )


async def main():
    llm_url = sys.argv[1] if len(sys.argv) > 1 else "http://ai-lab.lan:8081/v1"
    llm_model = (
        sys.argv[2] if len(sys.argv) > 2 else "/mnt/models/Qwen3.5-27B-GPTQ-Int4"
    )

    print(f"LLM: {llm_url} / {llm_model}")
    embedder = FastEmbedder(model_name="BAAI/bge-large-en-v1.5")
    llm = LLMClient(base_url=llm_url, model=llm_model, max_tokens=100)

    memory = ConsolidationMemory(embedder, llm)

    # Phase 1: Add entries
    print(f"\n{'=' * 70}")
    print("PHASE 1: INCREMENTAL CONSOLIDATION")
    print(f"{'=' * 70}\n")

    for i, entry in enumerate(ENTRIES):
        print(f'[{i + 1:2d}] + "{entry[:70]}"')
        concepts = await memory.add(entry)
        for c in concepts:
            print(f"     >>> CONCEPT ({len(c['entries'])} entries): {c['label'][:80]}")
        print()

    print(f"  {len(memory.entries)} episodes, {len(memory.concepts)} concepts\n")

    # Phase 2: Query sequence (simulates agent encountering situations over time)
    print(f"{'=' * 70}")
    print("PHASE 2: QUERY SEQUENCE WITH HEBBIAN REINFORCEMENT")
    print(f"{'=' * 70}\n")

    for round_num, query in enumerate(QUERY_SEQUENCE):
        result = memory.recall(query)
        print(f'Round {round_num + 1}: "{query}"')
        print(
            f"  Top episode:  {result['episodes'][0][0]:.3f}  {result['episodes'][0][1][:60]}"
        )
        if result["concepts"]:
            print(
                f"  Top concept:  {result['concepts'][0][0]:.3f}  [{result['concepts'][0][2]}] {result['concepts'][0][1][:55]}"
            )
        print()

    # Phase 3: Show what got reinforced
    print(f"{'=' * 70}")
    print("PHASE 3: HEBBIAN REINFORCEMENT MAP")
    print(f"{'=' * 70}\n")
    memory.print_boosts()

    # Phase 4: Re-query to see if reinforcement changed results
    print(f"\n{'=' * 70}")
    print("PHASE 4: RE-QUERY AFTER REINFORCEMENT")
    print(f"{'=' * 70}\n")

    retest_queries = [
        "Should I trust a new agent offering a trade?",
        "Christopher wants to trade again",
    ]

    for q in retest_queries:
        result = memory.recall(q)
        print(f'Q: "{q}"')
        print("  Episodes:")
        for sim, text in result["episodes"][:3]:
            print(f"    {sim:.3f}  {text[:65]}")
        if result["concepts"]:
            print("  Concepts:")
            for sim, label, size in result["concepts"][:3]:
                print(f"    {sim:.3f}  [{size}] {label[:60]}")
        print()


if __name__ == "__main__":
    asyncio.run(main())
