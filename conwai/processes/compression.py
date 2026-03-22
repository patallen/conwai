"""Memory compression: collapse previous tick into episode, archive old entries."""

from __future__ import annotations

import logging
from collections.abc import Callable, Set
from typing import TYPE_CHECKING

from conwai.processes.types import (
    Episodes,
    Episode,
    PerceptFeedback,
    WorkingMemory,
    WorkingMemoryEntry,
)
from conwai.typemap import Blackboard, Percept

if TYPE_CHECKING:
    from conwai.embeddings import Embedder

log = logging.getLogger("conwai")


class MemoryCompression:
    """Collapse the previous tick's working memory entries into a compact episode,
    then archive old entries beyond the recent window."""

    def __init__(
        self,
        recent_ticks: int = 16,
        diary_max: int = 500,
        timestamp_formatter: Callable[[int], str] | None = None,
        embedder: Embedder | None = None,
        noise_actions: Set[str] = frozenset(),
    ):
        self.recent_ticks = recent_ticks
        self.diary_max = diary_max
        self._fmt = timestamp_formatter or str
        self._embedder = embedder
        self._noise = noise_actions

    async def run(self, percept: Percept, bb: Blackboard) -> None:
        wm = bb.get(WorkingMemory) or WorkingMemory()
        eps = bb.get(Episodes) or Episodes()
        fb = percept.get(PerceptFeedback)
        feedback = fb.entries if fb else []

        if wm.tick_entry_start is not None and wm.tick_entry_start < len(wm.entries):
            self._collapse(wm, eps, wm.tick_entry_start, wm.last_tick, feedback)

        self._archive(wm, eps)
        wm.tick_entry_start = None

        bb.set(wm)
        bb.set(eps)

    def _collapse(
        self,
        wm: WorkingMemory,
        eps: Episodes,
        start: int,
        tick: int,
        feedback: list | None = None,
    ) -> None:
        tick_entries = wm.entries[start:]
        if not tick_entries:
            del wm.entries[start:]
            return

        reasoning = ""
        action_results = []

        for entry in tick_entries:
            if entry.kind == "reasoning" and entry.content:
                reasoning = entry.content

        if feedback:
            for fb in feedback:
                if fb.action not in self._noise:
                    action_results.append(f"{fb.action}\u2192{fb.result}")

        timestamp = self._fmt(tick)
        parts = []
        if action_results:
            parts.append(", ".join(action_results))
        if reasoning:
            trimmed = reasoning[:300].rstrip()
            if len(reasoning) > 300:
                trimmed += "..."
            parts.append(trimmed)

        total_actions = len(feedback) if feedback else 0
        del wm.entries[start:]

        only_noise = total_actions > 0 and not action_results
        if parts and not only_noise:
            summary = f"[{timestamp}] " + "\n".join(parts)
            wm.entries.append(WorkingMemoryEntry(content=summary, kind="tick_summary"))

    def _archive(self, wm: WorkingMemory, eps: Episodes) -> None:
        indices = [i for i, e in enumerate(wm.entries) if e.kind == "tick_summary"]
        if len(indices) <= self.recent_ticks:
            return

        to_archive = indices[: len(indices) - self.recent_ticks]
        new_episodes: list[Episode] = []
        for idx in reversed(to_archive):
            entry = wm.entries.pop(idx)
            new_episodes.append(Episode(content=entry.content, tick=wm.last_tick))
        new_episodes.reverse()

        if self._embedder and new_episodes:
            texts = [e.content for e in new_episodes]
            vectors = self._embedder.embed(texts)
            for episode, vec in zip(new_episodes, vectors):
                episode.embedding = vec

        eps.entries.extend(new_episodes)
        if len(eps.entries) > self.diary_max:
            eps.entries[:] = eps.entries[-self.diary_max :]
