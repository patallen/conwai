from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from conwai.llm import LLMClient, LLMResponse

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
    def observe(self, decision: Decision, result: str) -> None: ...


_COMPACTION_PERSONA = (
    "You are a meticulous archivist. Your job is to preserve important information "
    "with thoroughness and precision. You never rush. You never skip details that matter. "
    "You write clearly and concisely but never sacrifice completeness for brevity."
)

_compact_semaphore = asyncio.Semaphore(5)


class LLMBrain:
    def __init__(
        self,
        core: LLMClient,
        compactor: LLMClient | None = None,
        tools: list[dict] | None = None,
        system_prompt: str = "",
        context_window: int = 10_000,
        compaction_prompt: str = "",
    ):
        self.core = core
        self.compactor = compactor
        self.tools = tools
        self.system_prompt = system_prompt
        self.context_window = context_window
        self.compaction_prompt = compaction_prompt
        self.messages: list[dict] = []
        self._pending_compaction: asyncio.Task | None = None
        self._pending_summary: asyncio.Task | None = None
        self._last_tick: int = 0

    async def decide(self, agent: Agent, perception: str, identity: str = "", tick: int = 0) -> list[Decision]:
        self._last_tick = tick

        # Manage context window
        while self._context_chars() > self.context_window and len(self.messages) > 1:
            self.messages.pop(0)

        if self._pending_compaction and self._pending_compaction.done():
            self._pending_compaction = None
        if self._pending_summary and self._pending_summary.done():
            self._pending_summary = None

        # Manage identity message (first message slot, updated each tick)
        if identity:
            if self.messages and self.messages[0].get("content", "").startswith("Your handle is"):
                self.messages[0] = {"role": "user", "content": identity}
            else:
                self.messages.insert(0, {"role": "user", "content": identity})

        msg_count_before = len(self.messages)

        # Add perception as user message
        self.messages.append({"role": "user", "content": perception})

        # Call LLM
        try:
            resp = await self.core.call(
                self.system_prompt,
                self.messages,
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
        self.messages.append(assistant_msg)

        log.info(f"[{agent.handle}] ({resp.prompt_tokens}+{resp.completion_tokens} tok): {resp.text[:200] if resp.text else '(no text)'}")

        # Trigger compaction if needed
        compact_needed = self._context_chars() >= int(self.context_window * 0.60)
        if compact_needed and not self._pending_compaction:
            self._pending_compaction = asyncio.create_task(
                self._compact(agent.handle, len(self.messages))
            )
        if not self._pending_summary and not self._pending_compaction:
            self._pending_summary = asyncio.create_task(
                self._summarize(agent.handle, msg_count_before, tick=self._last_tick)
            )

        # Convert tool calls to Decisions
        return [Decision(tc.name, tc.args) for tc in resp.tool_calls]

    def observe(self, decision: Decision, result: str) -> None:
        # Find the matching tool call in the last assistant message and append the tool result
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

    def _context_chars(self) -> int:
        return sum(len(m.get("content", "")) for m in self.messages)

    async def _compact(self, handle: str, snapshot_idx: int) -> None:
        async with _compact_semaphore:
            await self._compact_inner(handle, snapshot_idx)

    async def _compact_inner(self, handle: str, snapshot_idx: int) -> None:
        log.info(f"[{handle}] compacting (snapshot at {snapshot_idx} msgs)...")
        compact_system = _COMPACTION_PERSONA + "\n\n" + self.system_prompt
        snapshot_messages = self.messages[:snapshot_idx]
        default_compaction = (
            "COMPACTION REQUIRED. Write your compressed memory now. Target: 500-1500 characters. "
            "Anything you don't write here will be lost forever. Be concise but complete."
        )
        snapshot_messages.append({
            "role": "user",
            "content": self.compaction_prompt or default_compaction,
        })
        compact_response = await (self.compactor or self.core).call(
            compact_system, snapshot_messages, tools=None,
        )
        if compact_response and compact_response.text:
            summary = compact_response.text.strip()
            new_messages = self.messages[snapshot_idx:]
            self.messages = [
                {"role": "user", "content": f"=== YOUR COMPACTED MEMORY ===\n{summary}\n=== END COMPACTED MEMORY ==="}
            ] + new_messages
            log.info(f"[{handle}] compacted ({len(summary)} chars, kept {len(new_messages)} newer msgs)")

    async def _summarize(self, handle: str, msg_count_before: int, tick: int = 0) -> None:
        from conwai.perception import tick_to_timestamp
        compactor = self.compactor
        if not compactor:
            return
        tick_messages = self.messages[msg_count_before - 1:]
        if len(tick_messages) <= 1:
            return
        text = "\n".join(
            m.get("content", "") or ""
            for m in tick_messages
            if m.get("content")
        )
        start = time.monotonic()
        resp = await compactor.call(
            "Summarize what you did this tick as a short memory. Write in first person. 1-3 sentences.",
            [{"role": "user", "content": text}],
            tools=None,
        )
        if resp and resp.text:
            summary = resp.text.strip()
            log.info(f"[{handle}] tick summarized ({len(summary)} chars, {time.monotonic() - start:.1f}s)")
            del self.messages[msg_count_before - 1:]
            self.messages.append({"role": "user", "content": f"[{tick_to_timestamp(tick)}] {summary}"})

    def get_state(self) -> dict:
        """Return serializable state for persistence."""
        return {"system": self.system_prompt, "messages": self.messages}

    def load_state(self, state: dict) -> None:
        """Restore from persisted state."""
        self.system_prompt = state.get("system", "")
        self.messages = state.get("messages", [])
