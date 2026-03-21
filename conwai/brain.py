from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from conwai.llm import LLMClient

if TYPE_CHECKING:
    from conwai.agent import Agent

log = logging.getLogger("conwai")


@dataclass
class Decision:
    action: str
    args: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Brain(Protocol):
    async def decide(self, agent: Agent, perception: str, identity: str = "", tick: int = 0) -> list[Decision]: ...
    async def observe(self, decision: Decision, result: str) -> None: ...


# Pattern to match agent handles like A1, A19, Abc3
_HANDLE_RE = re.compile(r"\b[A-Z][a-z0-9]{1,5}\b")


class LLMBrain:
    def __init__(
        self,
        core: LLMClient,
        tools: list[dict] | None = None,
        system_prompt: str = "",
        context_window: int = 10_000,
        recent_ticks: int = 16,
        diary_max: int = 500,
        recall_limit: int = 5,
        timestamp_formatter: Any = None,
    ):
        self.core = core
        self.tools = tools
        self.system_prompt = system_prompt
        self.context_window = context_window
        self.recent_ticks = recent_ticks
        self.diary_max = diary_max
        self.recall_limit = recall_limit
        self._timestamp_formatter = timestamp_formatter or str
        self.messages: list[dict] = []
        self._diary: list[dict] = []  # {tick, content, handles}
        self._message_lock = asyncio.Lock()
        self._last_tick: int = 0
        self._tick_msg_start: int | None = None

    async def decide(self, agent: Agent, perception: str, identity: str = "", tick: int = 0) -> list[Decision]:
        prev_tick = self._last_tick
        self._last_tick = tick

        async with self._message_lock:
            # Collapse previous tick's raw messages into a diary entry
            if self._tick_msg_start is not None:
                self._collapse_tick(prev_tick)

            # Move old diary entries from messages to long-term diary
            self._trim_diary()

            # Recall relevant old memories based on current perception
            recalled = self._recall(perception)

            # Safety: drop oldest messages if still over context window
            while self._context_chars() > self.context_window and len(self.messages) > 1:
                self.messages.pop(0)

            # Identity message (first slot, updated each tick)
            if identity:
                if self.messages and self.messages[0].get("_identity"):
                    self.messages[0] = {"role": "user", "content": identity, "_identity": True}
                else:
                    self.messages.insert(0, {"role": "user", "content": identity, "_identity": True})

            # Inject recalled memories before perception
            if recalled:
                recall_text = "=== RECALLED MEMORIES ===\n" + "\n".join(recalled) + "\n=== END ==="
                self.messages.append({"role": "user", "content": recall_text, "_recalled": True})

            # Add perception and mark where this tick's messages start
            self.messages.append({"role": "user", "content": perception})
            self._tick_msg_start = len(self.messages) - 1

            messages_snapshot = list(self.messages)

            # Remove the recalled block after snapshot — it's ephemeral
            self.messages = [m for m in self.messages if not m.get("_recalled")]
            # Fix tick_msg_start after removal
            self._tick_msg_start = next(
                (i for i in range(len(self.messages) - 1, -1, -1)
                 if self.messages[i].get("role") == "user" and not self.messages[i].get("_identity") and not self.messages[i].get("_tick_summary")),
                len(self.messages) - 1,
            )

        # Call LLM (outside lock — this awaits network I/O)
        try:
            resp = await self.core.call(
                self.system_prompt,
                messages_snapshot,
                tools=self.tools,
            )
        except Exception as e:
            log.error(f"[{agent.handle}] LLM call failed: {e}")
            return []

        if not resp.text and not resp.tool_calls:
            return []

        # Record assistant message
        assistant_msg: dict = {"role": "assistant"}
        if resp.text:
            assistant_msg["content"] = resp.text
        if resp.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                }
                for tc in resp.tool_calls
            ]

        async with self._message_lock:
            self.messages.append(assistant_msg)
            log.info(f"[{agent.handle}] ({resp.prompt_tokens}+{resp.completion_tokens} tok): {resp.text[:200] if resp.text else '(no text)'}")

        return [Decision(tc.name, tc.args) for tc in resp.tool_calls]

    async def observe(self, decision: Decision, result: str) -> None:
        async with self._message_lock:
            for msg in reversed(self.messages):
                if msg.get("role") == "assistant" and "tool_calls" in msg:
                    for tc in msg["tool_calls"]:
                        if tc["function"]["name"] == decision.action:
                            self.messages.append({
                                "role": "tool",
                                "tool_call_id": tc["id"],
                                "name": decision.action,
                                "content": result,
                            })
                            return
                    break

    def _collapse_tick(self, tick: int) -> None:
        """Replace the previous tick's raw messages with a compact diary entry."""
        start = self._tick_msg_start
        self._tick_msg_start = None
        if start is None or start >= len(self.messages):
            return

        tick_messages = self.messages[start:]
        if not tick_messages:
            return

        # Extract the agent's reasoning and structured action results
        reasoning = ""
        action_results = []
        for msg in tick_messages:
            if msg.get("role") == "assistant" and msg.get("content"):
                reasoning = msg["content"]
            elif msg.get("role") == "tool":
                name = msg.get("name", "?")
                result = msg.get("content", "ok")
                action_results.append(f"{name}→{result}")

        # Build compact entry — actions first, then reasoning
        timestamp = self._timestamp_formatter(tick)
        parts = []
        if action_results:
            parts.append(", ".join(action_results))
        if reasoning:
            trimmed = reasoning[:150].rstrip()
            if len(reasoning) > 150:
                trimmed += "..."
            parts.append(trimmed)

        if not parts:
            del self.messages[start:]
            return

        summary = f"[{timestamp}] " + "\n".join(parts)
        del self.messages[start:]
        self.messages.append({"role": "user", "content": summary, "_tick_summary": True})

    def _trim_diary(self) -> None:
        """Move old diary entries from messages to the long-term diary store."""
        indices = [i for i, m in enumerate(self.messages) if m.get("_tick_summary")]
        if len(indices) <= self.recent_ticks:
            return
        # Move oldest entries to diary
        to_archive = indices[: len(indices) - self.recent_ticks]
        for idx in reversed(to_archive):
            msg = self.messages.pop(idx)
            content = msg["content"]
            handles = set(_HANDLE_RE.findall(content))
            self._diary.append({"content": content, "handles": handles})
        # Cap the diary size
        if len(self._diary) > self.diary_max:
            self._diary = self._diary[-self.diary_max:]

    def _recall(self, perception: str) -> list[str]:
        """Retrieve diary entries relevant to the current perception."""
        if not self._diary:
            return []
        # Extract handles mentioned in perception
        triggers = set(_HANDLE_RE.findall(perception))
        if not triggers:
            return []
        # Find diary entries that mention any of the triggered handles
        matches = []
        for entry in reversed(self._diary):
            if entry["handles"] & triggers:
                matches.append(entry["content"])
                if len(matches) >= self.recall_limit:
                    break
        matches.reverse()  # chronological order
        return matches

    def _context_chars(self) -> int:
        return sum(len(m.get("content", "")) for m in self.messages)

    def get_state(self) -> dict:
        """Return serializable state for persistence."""
        # Convert handle sets to lists for JSON
        diary = [{"content": e["content"], "handles": sorted(e["handles"])} for e in self._diary]
        return {"system": self.system_prompt, "messages": list(self.messages), "diary": diary}

    def load_state(self, state: dict) -> None:
        """Restore from persisted state."""
        self.system_prompt = state.get("system", "")
        self.messages = state.get("messages", [])
        self._diary = [
            {"content": e["content"], "handles": set(e.get("handles", []))}
            for e in state.get("diary", [])
        ]
