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
    HUNGER_MAX,
    HUNGER_DECAY_PER_TICK,
    HUNGER_AUTO_EAT_THRESHOLD,
    HUNGER_EAT_RESTORE,
    HUNGER_STARVE_COIN_PENALTY,
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
    food: int = 0  # inventory — foraged, traded, given
    hunger: int = HUNGER_MAX  # survival stat — ticks down, auto-eats food
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
    _dm_sent_this_tick: bool = field(default=False, init=False, repr=False)
    _foraging: bool = field(default=False, init=False, repr=False)

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
        self._dm_sent_this_tick = False
        self._foraging = False
        try:
            if self._sleep_ticks > 0:
                self._handle_sleep(ctx)
                return

            if self.coins <= 0:
                self.alive = False
                print(f"[{self.handle}] DEAD — no coins", flush=True)
                ctx.log(
                    self.handle,
                    "agent_died",
                    {"reason": "no_coins", "coins": self.coins},
                )
                return

            # Hunger ticks down, auto-eat food if available
            self.hunger = max(0, self.hunger - HUNGER_DECAY_PER_TICK)
            if self.hunger <= HUNGER_AUTO_EAT_THRESHOLD and self.food > 0:
                self.food -= 1
                self.hunger = min(HUNGER_MAX, self.hunger + HUNGER_EAT_RESTORE)
            if self.hunger == 0:
                self.coins = max(0, self.coins - HUNGER_STARVE_COIN_PENALTY)
                self._energy_log.append(f"coins -{HUNGER_STARVE_COIN_PENALTY} (starving — no food)")

            self._rebuild_context(ctx)
            llm_response = await self._get_response(ctx)
            if not llm_response:
                return
            self._process_tool_calls(llm_response, ctx)

            # Two-pass compaction
            if self._compact_needed:
                await self._do_compaction(ctx)

        except Exception as e:
            print(f"[{self.handle}] ERROR: {e}", flush=True)
        finally:
            self._running = False

    def _handle_sleep(self, ctx: Context) -> None:
        self._sleep_ticks -= 1
        self.gain_coins("sleeping", SLEEP_REGEN_PER_TICK)
        self.hunger = max(0, self.hunger - HUNGER_DECAY_PER_TICK)
        if self.hunger <= HUNGER_AUTO_EAT_THRESHOLD and self.food > 0:
            self.food -= 1
            self.hunger = min(HUNGER_MAX, self.hunger + HUNGER_EAT_RESTORE)
        if self.hunger == 0:
            self.coins = max(0, self.coins - HUNGER_STARVE_COIN_PENALTY)
            self._energy_log.append(f"coins -{HUNGER_STARVE_COIN_PENALTY} (starving in sleep)")
        self.decay_memory()
        print(
            f"[{self.handle}] SLEEPING ({self._sleep_ticks} ticks left, coins: {int(self.coins)}, food: {self.food})",
            flush=True,
        )
        ctx.log(
            self.handle,
            "sleeping",
            {"ticks_left": self._sleep_ticks, "energy": self.coins},
        )

    _COMPACTION_PERSONA = (
        "You are a meticulous archivist. Your job is to preserve important information "
        "with thoroughness and precision. You never rush. You never skip details that matter. "
        "You write clearly and concisely but never sacrifice completeness for brevity."
    )

    async def _do_compaction(self, ctx: Context) -> None:
        """Two-pass compaction: plan what to keep, then write the summary."""
        print(f"[{self.handle}] compaction pass 1: planning", flush=True)

        compact_system = self._COMPACTION_PERSONA + "\n\n" + self.system_prompt

        # Pass 1: Ask the agent to plan what to keep
        self.messages.append({
            "role": "user",
            "content": (
                "COMPACTION REQUIRED. Before writing your summary, review your history and list:\n"
                "1. Your current STATUS (coins, situation)\n"
                "2. Every agent you know — what happened between you, do you trust them, any debts or deals\n"
                "3. Important events that still affect you\n"
                "4. Current goals or unfinished business\n\n"
                "Write this out now. Be thorough — anything you forget will be lost forever."
            ),
        })
        plan_response = await self.core.call(
            compact_system,
            self.messages,
            tools=self.actions.tool_definitions(),
        )
        if not plan_response:
            return
        # Add the response to messages
        assistant_msg: dict = {"role": "assistant"}
        if plan_response.text:
            assistant_msg["content"] = plan_response.text
        self.messages.append(assistant_msg)
        print(
            f"[{self.handle}] ({plan_response.prompt_tokens}+{plan_response.completion_tokens} tok): {plan_response.text[:200] if plan_response.text else '(no text)'}",
            flush=True,
        )
        # Process any tool calls from pass 1 (agent might call compact early)
        if plan_response.tool_calls:
            import json
            assistant_msg["tool_calls"] = [
                {"id": tc.id, "type": "function", "function": {"name": tc.name, "arguments": json.dumps(tc.args)}}
                for tc in plan_response.tool_calls
            ]
            for tc in plan_response.tool_calls:
                self.actions.execute(self, ctx, tc.name, tc.args)
                result = ". ".join(self._action_log) if self._action_log else "ok"
                self.messages.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": result})
                self._action_log.clear()
            if not self._compact_needed:
                return  # compact succeeded in pass 1

        # Pass 2: Ask for the summary as text, then programmatically compact
        print(f"[{self.handle}] compaction pass 2: writing summary", flush=True)
        self.messages.append({
            "role": "user",
            "content": (
                "Good. Now write your compressed memory. Target: 5000-6000 characters — "
                "this is a MINIMUM as much as a maximum. Write enough detail to reconstruct your situation. "
                "Structure: STATUS (2-3 lines), AGENTS (2-4 sentences each — what happened between you, trust level, deals), "
                "HISTORY (key events with enough detail to understand them), ACTIVE (current goals). "
                "Write ONLY the summary, nothing else."
            ),
        })
        compact_response = await self.core.call(
            compact_system,
            self.messages,
            tools=None,  # No tools — force text-only output
        )
        if compact_response and compact_response.text:
            summary = compact_response.text.strip()
            from conwai.default_actions import _compact
            _compact(self, ctx, {"summary": summary})
            print(f"[{self.handle}] compaction complete ({len(summary)} chars)", flush=True)

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
        if self.hunger <= 30:
            parts.append(f"You are hungry (hunger: {self.hunger}/100, food: {self.food}). If hunger reaches 0 you starve and lose {HUNGER_STARVE_COIN_PENALTY} coins per tick. You eat food automatically but need to forage or trade for more.")
        if self._compact_needed:
            parts.append(
                "WARNING: Your memory is almost full. Compaction will begin after you act this tick."
            )
        tick_content = TICK_TEMPLATE.format(
            timestamp=self._tick_to_timestamp(ctx.tick),
            coins=int(self.coins),
            hunger=self.hunger,
            food=self.food,
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
            if self._foraging and tc.name != "compact":
                self.messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "name": tc.name,
                        "content": "You are foraging this tick and cannot take other actions.",
                    }
                )
                continue
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

    @staticmethod
    def _tick_to_timestamp(tick: int) -> str:
        day = tick // 24 + 1
        hour = 8 + (tick % 24)  # start at 8 AM, wrap at next day
        if hour >= 24:
            hour -= 24
            day += 1
        period = "AM" if hour < 12 else "PM"
        display_hour = hour % 12 or 12
        return f"Day {day}, {display_hour}:00 {period}"

    def _build_system_prompt(self) -> str:
        prompt = SYSTEM_TEMPLATE.format(
            handle=self.handle,
            personality=self.personality,
        )
        return prompt + "\n\n" + self._build_state_block()

    def _build_state_block(self) -> str:
        return SOUL_TEMPLATE.format(soul=self.soul or "(empty)")
