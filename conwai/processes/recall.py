"""Memory recall: surface relevant episodes for the current perception."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

import structlog

from conwai.brain import BrainContext
from conwai.processes.types import AgentHandle, Episode, Episodes, Observations, RecalledMemories

if TYPE_CHECKING:
    from conwai.llm import Embedder

log = structlog.get_logger()

_HANDLE_RE = re.compile(r"@(\w+)")


class MemoryRecall:
    """Surface episodes relevant to the current percept."""

    def __init__(
        self,
        recall_limit: int = 5,
        reflection_limit: int = 2,
        embedder: Embedder | None = None,
    ):
        self.recall_limit = recall_limit
        self.reflection_limit = reflection_limit
        self._embedder = embedder

    async def run(self, ctx: BrainContext) -> None:
        eps = ctx.state.get(Episodes)
        if not eps or not eps.entries:
            return

        obs = ctx.percept.get(Observations)
        perception_text = obs.text if obs else ""

        if self._embedder:
            embedded = [e for e in eps.entries if e.embedding is not None]
            if embedded:
                handle = ctx.percept.get(AgentHandle)
                agent_id = handle.value if handle else "?"
                query_vec = self._embedder.embed([perception_text])[0]

                recalled = self._split_recall(embedded, query_vec, agent_id)

                if recalled:
                    ctx.bb.set(RecalledMemories(entries=recalled))
                return

        matches = self._handle_recall(eps.entries, perception_text)
        if matches:
            ctx.bb.set(RecalledMemories(entries=matches))

    def _split_recall(
        self, embedded: list[Episode], query_vec: list[float], agent_id: str = "?"
    ) -> list[str]:
        episodes = [e for e in embedded if not e.content.startswith("[Reflection")]
        reflections = [e for e in embedded if e.content.startswith("[Reflection")]
        recalled = []
        if episodes:
            recalled.extend(self._topk(episodes, query_vec, self.recall_limit, agent_id=agent_id))
        if reflections:
            recalled.extend(self._topk(reflections, query_vec, self.reflection_limit, agent_id=agent_id))
        return recalled

    def _handle_recall(
        self, episodes: list[Episode], perception_text: str
    ) -> list[str]:
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
    def _topk(
        entries: list[Episode], query_vec: list[float], k: int, min_sim: float = 0.3, agent_id: str = "?"
    ) -> list[str]:
        if not entries:
            return []
        import numpy as np

        qv = np.array(query_vec)
        vecs = np.array([e.embedding for e in entries])
        sims = vecs @ qv / (np.linalg.norm(vecs, axis=1) * np.linalg.norm(qv) + 1e-10)
        top = list(np.argsort(sims)[-k:][::-1])
        recalled = []
        for i in top:
            if sims[i] < min_sim:
                continue
            content_preview = entries[i].content[:60].replace("\n", " ")
            log.info("recall", handle=agent_id, preview=content_preview, cosine=round(float(sims[i]), 2))
            recalled.append(entries[i].content)
        return recalled
