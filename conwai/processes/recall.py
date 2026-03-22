"""Memory recall: surface relevant episodes for the current perception."""

from __future__ import annotations

import logging
import re
from typing import TYPE_CHECKING

from conwai.processes.types import Episodes, Episode, Observations, RecalledMemories
from conwai.typemap import Blackboard, Percept

if TYPE_CHECKING:
    from conwai.embeddings import Embedder

log = logging.getLogger("conwai")

_HANDLE_RE = re.compile(r"@(\w+)")


class MemoryRecall:
    """Surface episodes relevant to the current percept."""

    def __init__(
        self,
        recall_limit: int = 5,
        reflection_limit: int | None = None,
        embedder: Embedder | None = None,
    ):
        self.recall_limit = recall_limit
        self.reflection_limit = reflection_limit
        self._embedder = embedder

    async def run(self, percept: Percept, bb: Blackboard) -> None:
        eps = bb.get(Episodes)
        if not eps or not eps.entries:
            return

        obs = percept.get(Observations)
        perception_text = obs.text if obs else ""

        if self._embedder:
            embedded = [e for e in eps.entries if e.embedding is not None]
            if embedded:
                query_vec = self._embedder.embed([perception_text])[0]

                if self.reflection_limit is not None:
                    recalled = self._split_recall(embedded, query_vec)
                else:
                    recalled = self._boosted_recall(embedded, query_vec)

                if recalled:
                    bb.set(RecalledMemories(entries=recalled))
                return

        matches = self._handle_recall(eps.entries, perception_text)
        if matches:
            bb.set(RecalledMemories(entries=matches))

    def _split_recall(self, embedded: list[Episode], query_vec: list[float]) -> list[str]:
        episodes = [e for e in embedded if not e.content.startswith("[Reflection]")]
        reflections = [e for e in embedded if e.content.startswith("[Reflection]")]
        recalled = []
        if episodes:
            recalled.extend(self._topk(episodes, query_vec, self.recall_limit))
        if reflections:
            recalled.extend(self._topk(reflections, query_vec, self.reflection_limit))
        return recalled

    def _boosted_recall(self, embedded: list[Episode], query_vec: list[float], min_sim: float = 0.3) -> list[str]:
        import numpy as np

        qv = np.array(query_vec)
        cv = np.array([e.embedding for e in embedded])
        sims = cv @ qv / (np.linalg.norm(cv, axis=1) * np.linalg.norm(qv) + 1e-10)
        for i, e in enumerate(embedded):
            if e.content.startswith("[Reflection]"):
                sims[i] *= 1.5
        top = list(np.argsort(sims)[-self.recall_limit :][::-1])
        return [embedded[i].content for i in top if sims[i] >= min_sim]

    def _handle_recall(self, episodes: list[Episode], perception_text: str) -> list[str]:
        triggers = set(_HANDLE_RE.findall(perception_text))
        if not triggers:
            return []

        matches = []
        for ep in reversed(episodes):
            ep_handles = set(_HANDLE_RE.findall(ep.content))
            if ep_handles & triggers:
                matches.append(ep.content)
                if len(matches) >= self.recall_limit:
                    break
        matches.reverse()
        return matches

    @staticmethod
    def _topk(entries: list[Episode], query_vec: list[float], k: int, min_sim: float = 0.3) -> list[str]:
        if not entries:
            return []
        import numpy as np

        qv = np.array(query_vec)
        vecs = np.array([e.embedding for e in entries])
        sims = vecs @ qv / (np.linalg.norm(vecs, axis=1) * np.linalg.norm(qv) + 1e-10)
        top = list(np.argsort(sims)[-k:][::-1])
        return [entries[i].content for i in top if sims[i] >= min_sim]
