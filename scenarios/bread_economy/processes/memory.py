"""Memory processes: compression of old ticks and recall of relevant diary entries."""

from __future__ import annotations

import re
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from conwai.embeddings import Embedder

_HANDLE_RE = re.compile(r"\b[A-Z](?=[a-z0-9]*\d)[a-z0-9]{1,5}\b")


class MemoryCompression:
    """Collapse the previous tick's raw messages into a compact diary entry,
    then archive old entries beyond the recent window."""

    def __init__(
        self,
        recent_ticks: int = 16,
        diary_max: int = 500,
        timestamp_formatter: Callable[[int], str] | None = None,
        embedder: Embedder | None = None,
    ):
        self.recent_ticks = recent_ticks
        self.diary_max = diary_max
        self._fmt = timestamp_formatter or str
        self._embedder = embedder

    async def run(self, board: dict[str, Any]) -> None:
        state = board.setdefault("state", {})
        messages: list[dict] = state.setdefault("messages", [])
        diary: list[dict] = state.setdefault("diary", [])

        tick_msg_start: int | None = state.get("tick_msg_start")
        prev_tick: int = state.get("last_tick", 0)

        # Get action feedback from percept (results of previous tick's actions)
        percept = board.get("percept")
        feedback = getattr(percept, "action_feedback", [])

        if tick_msg_start is not None and tick_msg_start < len(messages):
            self._collapse(messages, diary, tick_msg_start, prev_tick, feedback)

        self._archive(messages, diary)

        state["tick_msg_start"] = None

    def _collapse(
        self,
        messages: list[dict],
        diary: list[dict],
        start: int,
        tick: int,
        feedback: list | None = None,
    ) -> None:
        tick_messages = messages[start:]
        if not tick_messages:
            del messages[start:]
            return

        reasoning = ""
        action_results = []
        for msg in tick_messages:
            if msg.get("role") == "assistant" and msg.get("content"):
                reasoning = msg["content"]
            elif msg.get("role") == "tool":
                name = msg.get("name", "?")
                result = msg.get("content", "ok")
                action_results.append(f"{name}→{result}")

        # Include deferred action feedback (from BrainPhase)
        if feedback:
            for fb in feedback:
                action_results.append(f"{fb.action}→{fb.result}")

        timestamp = self._fmt(tick)
        parts = []
        if action_results:
            parts.append(", ".join(action_results))
        if reasoning:
            trimmed = reasoning[:150].rstrip()
            if len(reasoning) > 150:
                trimmed += "..."
            parts.append(trimmed)

        del messages[start:]

        if parts:
            summary = f"[{timestamp}] " + "\n".join(parts)
            messages.append({"role": "user", "content": summary, "_tick_summary": True})

    def _archive(self, messages: list[dict], diary: list[dict]) -> None:
        indices = [i for i, m in enumerate(messages) if m.get("_tick_summary")]
        if len(indices) <= self.recent_ticks:
            return
        to_archive = indices[: len(indices) - self.recent_ticks]
        new_entries = []
        for idx in reversed(to_archive):
            msg = messages.pop(idx)
            content = msg["content"]
            handles = sorted(set(_HANDLE_RE.findall(content)))
            new_entries.append({"content": content, "handles": handles})
        new_entries.reverse()  # restore chronological order

        # Batch-embed new entries
        if self._embedder and new_entries:
            texts = [e["content"] for e in new_entries]
            vectors = self._embedder.embed(texts)
            for entry, vec in zip(new_entries, vectors):
                entry["embedding"] = vec

        diary.extend(new_entries)
        if len(diary) > self.diary_max:
            diary[:] = diary[-self.diary_max :]


class MemoryRecall:
    """Surface diary entries relevant to the current percept."""

    def __init__(self, recall_limit: int = 5, embedder: Embedder | None = None):
        self.recall_limit = recall_limit
        self._embedder = embedder

    async def run(self, board: dict[str, Any]) -> None:
        state = board.setdefault("state", {})
        diary: list[dict] = state.get("diary", [])
        if not diary:
            return

        percept = board.get("percept")
        perception_text = getattr(percept, "to_prompt", lambda: "")()

        # Vector recall: embed perception, find most similar diary entries
        if self._embedder:
            candidates = [e for e in diary if "embedding" in e]
            if candidates:
                from conwai.embeddings import cosine_topk

                query_vec = self._embedder.embed([perception_text])[0]
                candidate_vecs = [e["embedding"] for e in candidates]
                top_indices = cosine_topk(query_vec, candidate_vecs, k=self.recall_limit)
                board["recalled"] = [candidates[i]["content"] for i in top_indices]
                return

        # Fallback: handle-based recall
        triggers = set(_HANDLE_RE.findall(perception_text))
        if not triggers:
            return

        matches = []
        for entry in reversed(diary):
            entry_handles = set(entry.get("handles", []))
            if entry_handles & triggers:
                matches.append(entry["content"])
                if len(matches) >= self.recall_limit:
                    break
        matches.reverse()
        board["recalled"] = matches
