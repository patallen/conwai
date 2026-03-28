"""Activation-based memory recall: ACT-R-inspired scoring with recency, frequency, and relevance."""

from __future__ import annotations

import re
from math import log as math_log
from typing import TYPE_CHECKING

import numpy as np
import structlog

from conwai.brain import BrainContext
from conwai.processes.types import (
    AgentHandle,
    Episode,
    Episodes,
    Observations,
    PerceptTick,
    RecalledMemories,
)

if TYPE_CHECKING:
    from conwai.llm import Embedder

log = structlog.get_logger()

_HANDLE_RE = re.compile(r"@(\w+)")


class ActivationRecall:
    """Surface episodes using activation scoring: recency + frequency + cosine similarity + importance."""

    def __init__(
        self,
        recall_limit: int = 5,
        reflection_limit: int = 2,
        embedder: Embedder | None = None,
        alpha: float = 0.25,
        beta: float = 0.05,
        gamma: float = 0.5,
        delta: float = 0.2,
        decay_rate: float = 0.01,
        freq_cap: int = 20,
    ):
        self.recall_limit = recall_limit
        self.reflection_limit = reflection_limit
        self._embedder = embedder
        self._alpha = alpha
        self._beta = beta
        self._gamma = gamma
        self._delta = delta
        self._decay_rate = decay_rate
        self._freq_cap = freq_cap
        self._log_freq_denom = math_log(1 + freq_cap)

    async def run(self, ctx: BrainContext) -> None:
        eps = ctx.state.get(Episodes)
        if not eps or not eps.entries:
            return

        obs = ctx.percept.get(Observations)
        perception_text = obs.text if obs else ""

        tick_entry = ctx.percept.get(PerceptTick)
        current_tick = tick_entry.value if tick_entry else 0

        if self._embedder:
            embedded = [e for e in eps.entries if e.embedding is not None]
            if embedded:
                handle = ctx.percept.get(AgentHandle)
                agent_id = handle.value if handle else "?"
                query_vec = self._embedder.embed([perception_text])[0]
                episodes = [
                    e for e in embedded if not e.content.startswith("[Reflection")
                ]
                reflections = [
                    e for e in embedded if e.content.startswith("[Reflection")
                ]
                recalled = self._activation_recall(
                    episodes,
                    query_vec,
                    current_tick,
                    agent_id=agent_id,
                    limit=self.recall_limit,
                )
                recalled += self._activation_recall(
                    reflections,
                    query_vec,
                    current_tick,
                    agent_id=agent_id,
                    limit=self.reflection_limit,
                )
                if recalled:
                    ctx.bb.set(RecalledMemories(entries=[e.content for e in recalled]))
                return

        # Fallback: @-mention matching (no metadata updates)
        matches = self._handle_recall(eps.entries, perception_text)
        if matches:
            ctx.bb.set(RecalledMemories(entries=matches))

    def _activation_recall(
        self,
        embedded: list[Episode],
        query_vec: list[float],
        current_tick: int,
        agent_id: str = "?",
        limit: int = 5,
        min_score: float = 0.1,
    ) -> list[Episode]:
        if not embedded:
            return []
        qv = np.array(query_vec)
        cv = np.array([e.embedding for e in embedded])
        cosine_sims = (
            cv @ qv / (np.linalg.norm(cv, axis=1) * np.linalg.norm(qv) + 1e-10)
        )

        scores = np.empty(len(embedded))
        for i, ep in enumerate(embedded):
            age = max(0, current_tick - ep.last_accessed)
            recency = 1.0 / (1.0 + self._decay_rate * age)
            freq = (
                math_log(1 + min(ep.access_count, self._freq_cap))
                / self._log_freq_denom
            )
            imp = ep.importance / 10.0 if ep.importance > 0 else 0.5
            scores[i] = (
                self._alpha * recency
                + self._beta * freq
                + self._gamma * cosine_sims[i]
                + self._delta * imp
            )

        top_indices = list(np.argsort(scores)[-limit:][::-1])
        recalled = []

        for idx in top_indices:
            if scores[idx] < min_score:
                continue
            ep = embedded[idx]
            age = max(0, current_tick - ep.last_accessed)
            recency = 1.0 / (1.0 + self._decay_rate * age)
            freq = (
                math_log(1 + min(ep.access_count, self._freq_cap))
                / self._log_freq_denom
            )
            cosine = float(cosine_sims[idx])

            imp = ep.importance / 10.0 if ep.importance > 0 else 0.5
            content_preview = ep.content[:60].replace("\n", " ")
            log.info(
                "recall",
                handle=agent_id,
                preview=content_preview,
                score=round(float(scores[idx]), 2),
                recency=round(recency, 2),
                freq=round(freq, 2),
                cosine=round(cosine, 2),
                importance=round(imp, 2),
            )

            ep.access_count += 1
            recalled.append(ep)

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
