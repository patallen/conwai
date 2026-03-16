from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from conwai.actions import ActionRegistry
from conwai.config import (
    CONTEXT_WINDOW,
    ENERGY_MAX,
    MEMORY_MAX,
    SLEEP_REGEN_PER_TICK,
    TRAITS,
)
from conwai.llm import LLMClient, LLMResponse

if TYPE_CHECKING:
    from conwai.app import Context

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_TEMPLATE = (PROMPTS_DIR / "system.md").read_text()
TICK_TEMPLATE = (PROMPTS_DIR / "tick.md").read_text()
SOUL_TEMPLATE = (PROMPTS_DIR / "soul.md").read_text()
MEMORY_TEMPLATE = (PROMPTS_DIR / "memory.md").read_text()

_available_traits = set(TRAITS)


def assign_traits(n: int = 2) -> list[str]:
    if len(_available_traits) < n:
        _available_traits.update(TRAITS)
    chosen = random.sample(sorted(_available_traits), n)
    _available_traits.difference_update(chosen)
    return chosen


MAX_REASONING = 200


@dataclass
class Agent:
    handle: str = field(default_factory=lambda: uuid4().hex[:8])
    core: LLMClient = field(default_factory=LLMClient)
    actions: ActionRegistry = field(default=None, repr=False)
    coins: float = ENERGY_MAX
    context_window: int = CONTEXT_WINDOW
    personality: str = ""
    soul: str = ""
    memory: str = ""
    alive: bool = True
    code_fragment: str | None = None

    messages: list[dict] = field(default_factory=list, repr=False)
    system_prompt: str = field(default="", repr=False)

    _running: bool = field(default=False, init=False, repr=False)
    _action_log: list[str] = field(default_factory=list, init=False, repr=False)
    _energy_log: list[str] = field(default_factory=list, init=False, repr=False)
    _sleep_ticks: int = field(default=0, init=False, repr=False)
    _compact_needed: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        if not self.personality:
            self.personality = ", ".join(assign_traits())

    @property
    def is_running(self) -> bool:
        return self._running

    def sleep(self, ticks: int) -> None:
        self._sleep_ticks = max(1, min(ticks, 50))

    def gain_coins(self, reason: str, amount: int) -> None:
        old = self.coins
        self.coins = self.coins + amount
        gained = self.coins - old
        if gained > 0:
            self._energy_log.append(f"coins +{int(gained)} ({reason})")

    def write_memory(self, content: str) -> int:
        self.memory = content[:MEMORY_MAX]
        return max(0, len(content) - MEMORY_MAX)

    def decay_memory(self, chars: int = 5) -> None:
        if len(self.memory) > chars:
            self.memory = self.memory[:-chars]

    async def tick(self, ctx: Context) -> None:
        self._running = True
        try:
            if self._sleep_ticks > 0:
                self._handle_sleep(ctx)
                return

            if self.coins <= 0:
                self.alive = False
                print(f"[{self.handle}] DEAD — no energy", flush=True)
                ctx.log(
                    self.handle,
                    "agent_died",
                    {"reason": "no_energy", "energy": self.coins},
                )
                return

            self._rebuild_context(ctx)
            llm_response = await self._get_response(ctx)
            if not llm_response:
                return
            self._process_tool_calls(llm_response, ctx)

        except Exception as e:
            print(f"[{self.handle}] ERROR: {e}", flush=True)
        finally:
            self._running = False

    def _handle_sleep(self, ctx: Context) -> None:
        self._sleep_ticks -= 1
        self.gain_coins("sleeping", SLEEP_REGEN_PER_TICK)
        self.decay_memory()
        print(
            f"[{self.handle}] SLEEPING ({self._sleep_ticks} ticks left, energy: {int(self.coins)})",
            flush=True,
        )
        ctx.log(
            self.handle,
            "sleeping",
            {"ticks_left": self._sleep_ticks, "energy": self.coins},
        )

    def _context_chars(self) -> int:
        return sum(len(m.get("content", "")) for m in self.messages)

    def _rebuild_context(self, ctx: Context) -> None:
        char_count = self._context_chars()

        # Warn at 60% of context window, hard trim at 100%
        warn_threshold = int(self.context_window * 0.6)
        if char_count >= warn_threshold and not self._compact_needed:
            self._compact_needed = True

        # Hard trim: drop oldest messages until under limit
        while self._context_chars() > self.context_window and len(self.messages) > 1:
            self.messages.pop(0)
        self.system_prompt = self._build_system_prompt()

        parts = [ctx.board.format_new(self.handle)]
        dms = ctx.bus.format_new(self.handle)
        if dms:
            parts.append(dms)
        if self._energy_log:
            parts.append("Coin changes: " + ". ".join(self._energy_log))
            self._energy_log.clear()
        if self.code_fragment:
            parts.append(f"YOUR CODE FRAGMENT: {self.code_fragment}")
        if self._compact_needed:
            parts.append(
                "WARNING: Your memory is almost full. Think through what matters "
                "in plain text first, then call compact() with your summary. "
                "Everything you don't save will be lost forever."
            )
        tick_content = TICK_TEMPLATE.format(
            tick=ctx.tick,
            coins=int(self.coins),
            content="\n\n".join(parts),
        )
        self.messages.append({"role": "user", "content": tick_content})
        print(
            f"[{self.handle}] context: {len(self.messages)} msgs ({self._context_chars()} chars), coins: {self.coins}{' [COMPACT NEEDED]' if self._compact_needed else ''}",
            flush=True,
        )

    async def _get_response(self, ctx: Context) -> LLMResponse | None:
        resp = await self.core.call(
            self.system_prompt,
            self.messages,
            tools=self.actions.tool_definitions(),
        )
        if not resp.text and not resp.tool_calls:
            print(f"[{self.handle}] empty response, skipping", flush=True)
            return None

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

        print(
            f"[{self.handle}] ({resp.prompt_tokens}+{resp.completion_tokens} tok): {resp.text[:200] if resp.text else '(no text)'}",
            flush=True,
        )
        if resp.tool_calls:
            names = [tc.name for tc in resp.tool_calls]
            print(f"[{self.handle}] tools: {names}", flush=True)
        return resp

    def _process_tool_calls(self, resp: LLMResponse, ctx: Context) -> None:
        for tc in resp.tool_calls:
            self.actions.execute(self, ctx, tc.name, tc.args)
            result = ". ".join(self._action_log) if self._action_log else "ok"
            self.messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tc.name,
                    "content": result,
                }
            )
            self._action_log.clear()

    def _build_system_prompt(self) -> str:
        prompt = SYSTEM_TEMPLATE.format(
            handle=self.handle,
            personality=self.personality,
        )
        return prompt + "\n\n" + self._build_state_block()

    def _build_state_block(self) -> str:
        parts = [SOUL_TEMPLATE.format(soul=self.soul or "(empty)")]
        if self.memory:
            parts.append(f"== Compacted Memory (your previous memories, preserved) ==\n{self.memory}")
        return "\n\n".join(parts)
