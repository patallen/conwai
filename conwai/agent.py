from __future__ import annotations

import asyncio
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
    STATE_BOARD_LENGTH,
    STATE_INTERACTIONS_LENGTH,
    STATE_LEDGER_LENGTH,
    TRAITS,
)
import logging

from conwai.llm import LLMClient, LLMResponse

log = logging.getLogger("conwai")

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
    compactor: LLMClient | None = field(default=None, repr=False)
    actions: ActionRegistry = field(default=None, repr=False)
    coins: float = ENERGY_MAX
    role: str = ""  # flour_forager, water_forager, baker
    flour: int = 0
    water: int = 0
    bread: int = 0
    hunger: int = HUNGER_MAX
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
    _board_history: list[str] = field(default_factory=list, init=False, repr=False)
    _dm_history: list[str] = field(default_factory=list, init=False, repr=False)
    _ledger: list[str] = field(default_factory=list, init=False, repr=False)
    _compact_needed: bool = field(default=False, init=False, repr=False)
    _dm_sent_this_tick: bool = field(default=False, init=False, repr=False)
    _foraging: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        if not self.personality:
            self.personality = ", ".join(assign_traits())

    @property
    def is_running(self) -> bool:
        return self._running

    def _stamp(self, tick: int, entry: str) -> str:
        return f"[{self._tick_to_timestamp(tick)}] {entry}"

    def record_board(self, tick: int, entry: str) -> None:
        self._board_history.append(self._stamp(tick, entry))
        self._board_history = self._board_history[-STATE_BOARD_LENGTH:]

    def record_dm(self, tick: int, entry: str) -> None:
        self._dm_history.append(self._stamp(tick, entry))
        self._dm_history = self._dm_history[-STATE_INTERACTIONS_LENGTH:]

    def record_ledger(self, tick: int, entry: str) -> None:
        self._ledger.append(self._stamp(tick, entry))
        self._ledger = self._ledger[-STATE_LEDGER_LENGTH:]

    def _format_state_sections(self) -> str:
        sections = []
        if self._board_history:
            sections.append("== Active Board Posts ==\n" + "\n".join(self._board_history))
        if self._dm_history:
            sections.append("== Recent Interactions ==\n" + "\n".join(self._dm_history))
        if self._ledger:
            sections.append("== Ledger ==\n" + "\n".join(self._ledger))
        return "\n\n".join(sections)

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
            if self.coins <= 0:
                self.alive = False
                log.info(f"[{self.handle}] DEAD — no coins")
                ctx.log(
                    self.handle,
                    "agent_died",
                    {"reason": "no_coins", "coins": self.coins},
                )
                return

            # Hunger ticks down, auto-eat bread if available
            self.hunger = max(0, self.hunger - HUNGER_DECAY_PER_TICK)
            if self.hunger <= HUNGER_AUTO_EAT_THRESHOLD and self.bread > 0:
                self.bread -= 1
                self.hunger = min(HUNGER_MAX, self.hunger + HUNGER_EAT_RESTORE)
            if self.hunger == 0:
                self.coins = max(0, self.coins - HUNGER_STARVE_COIN_PENALTY)
                self._energy_log.append(f"coins -{HUNGER_STARVE_COIN_PENALTY} (starving — no bread)")

            self._rebuild_context(ctx)
            msg_count_before = len(self.messages)
            llm_response = await self._get_response(ctx)
            if not llm_response:
                return
            self._process_tool_calls(llm_response, ctx)

            await self._summarize_tick(ctx, msg_count_before)

            if self._compact_needed:
                await self._do_compaction(ctx)

        except Exception as e:
            log.error(f"[{self.handle}] ERROR: {e}")
        finally:
            self._running = False


    async def _summarize_tick(self, ctx: Context, msg_count_before: int) -> None:
        """Use the compactor model to condense this tick's messages into a brief summary."""
        compactor = self.compactor
        if not compactor:
            return
        # Collect the tick input + all assistant/tool messages from this tick
        tick_messages = self.messages[msg_count_before - 1:]  # include the tick user msg
        if len(tick_messages) <= 1:
            return
        text = "\n".join(
            m.get("content", "") or ""
            for m in tick_messages
            if m.get("content")
        )
        resp = await compactor.call(
            "Summarize what you did this tick as a short memory. Write in first person. 1-3 sentences. Include actions, results, and anything important you learned.",
            [{"role": "user", "content": text}],
            tools=None,
        )
        if resp and resp.text:
            summary = resp.text.strip()
            # Replace tick messages with the summary
            del self.messages[msg_count_before - 1:]
            self.messages.append({"role": "user", "content": f"[{self._tick_to_timestamp(ctx.tick)}] {summary}"})
            log.info(f"[{self.handle}] tick summarized ({len(summary)} chars)")

    _COMPACTION_PERSONA = (
        "You are a meticulous archivist. Your job is to preserve important information "
        "with thoroughness and precision. You never rush. You never skip details that matter. "
        "You write clearly and concisely but never sacrifice completeness for brevity."
    )

    async def _do_compaction(self, ctx: Context) -> None:
        """Single-pass compaction: ask for summary as text, then programmatically compact."""
        log.info(f"[{self.handle}] compacting...")

        compact_system = self._COMPACTION_PERSONA + "\n\n" + self.system_prompt

        self.messages.append({
            "role": "user",
            "content": (
                "COMPACTION REQUIRED. Write your compressed memory now. Target: 500-1500 characters. "
                "The system already provides your coins, food, hunger, recent transactions, board posts, and DMs each tick — do NOT repeat any of that. "
                "Write ONLY: AGENTS (who you trust/distrust and why, 1 sentence each), "
                "DEALS (active promises or debts), LESSONS (hard-won knowledge), GOALS (current plans). "
                "Anything you don't write here will be lost forever. Be concise but complete."
            ),
        })
        compact_response = await (self.compactor or self.core).call(
            compact_system,
            self.messages,
            tools=None,
        )
        if compact_response and compact_response.text:
            summary = compact_response.text.strip()
            from conwai.default_actions import _compact
            _compact(self, ctx, {"summary": summary})
            log.info(f"[{self.handle}] compacted ({len(summary)} chars)")

    def _context_chars(self) -> int:
        return sum(len(m.get("content", "")) for m in self.messages)

    def _rebuild_context(self, ctx: Context) -> None:
        char_count = self._context_chars()

        # Compact at 60% of context window, hard trim at 100%
        if char_count >= int(self.context_window * 0.60) and not self._compact_needed:
            self._compact_needed = True

        # Hard trim: drop oldest messages if over limit
        while self._context_chars() > self.context_window and len(self.messages) > 1:
            self.messages.pop(0)
        self.system_prompt = self._build_system_prompt()

        # Record board posts and DMs into rolling history
        new_posts = ctx.board.read_new(self.handle)
        for p in new_posts:
            self.record_board(ctx.tick, f"{p.handle}: {p.content}")
        new_dms = ctx.bus.receive(self.handle)
        for dm in new_dms:
            self.record_dm(ctx.tick, f"{dm.from_handle}: {dm.content}")

        # Build tick message with new items
        if new_posts:
            parts = ["New on the board:\n" + "\n".join(f"{p.handle}: {p.content}" for p in new_posts)]
        else:
            parts = ["No new activity on the board."]
        if new_dms:
            parts.append("\n".join(f"DM from {dm.from_handle}: {dm.content}" for dm in new_dms))
        if self._energy_log:
            parts.append("Coin changes: " + ". ".join(self._energy_log))
            self._energy_log.clear()
        if self.code_fragment:
            parts.append(f"YOUR CODE FRAGMENT: {self.code_fragment}")
        if self.hunger <= 30:
            parts.append(f"WARNING: You are hungry (hunger: {self.hunger}/100, bread: {self.bread}). If hunger reaches 0 you starve and lose {HUNGER_STARVE_COIN_PENALTY} coins per tick. You eat bread automatically but need to bake or trade for more.")
        tick_content = TICK_TEMPLATE.format(
            timestamp=self._tick_to_timestamp(ctx.tick),
            coins=int(self.coins),
            hunger=self.hunger,
            flour=self.flour,
            water=self.water,
            bread=self.bread,
            content="\n\n".join(parts),
        )
        self.messages.append({"role": "user", "content": tick_content})
        log.info(f"[{self.handle}] context: {len(self.messages)} msgs ({self._context_chars()} chars), coins: {self.coins}{' [COMPACT NEEDED]' if self._compact_needed else ''}")

    async def _get_response(self, ctx: Context) -> LLMResponse | None:
        resp = await self.core.call(
            self.system_prompt,
            self.messages,
            tools=self.actions.tool_definitions(),
        )
        if not resp.text and not resp.tool_calls:
            log.info(f"[{self.handle}] empty response, skipping")
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

        log.info(f"[{self.handle}] ({resp.prompt_tokens}+{resp.completion_tokens} tok): {resp.text[:200] if resp.text else '(no text)'}")
        if resp.completion_tokens >= 2000:
            log.warning(f"[{self.handle}] RUNAWAY ({resp.completion_tokens} tok): {resp.text[:500]}")
        if resp.tool_calls:
            names = [tc.name for tc in resp.tool_calls]
            log.info(f"[{self.handle}] tools: {names}")
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
        from conwai.config import FORAGE_SKILL_BY_ROLE
        fs = FORAGE_SKILL_BY_ROLE
        role_descriptions = {
            "flour_forager": f"You are a flour forager. When you forage you find 0-{fs['flour_forager']['flour']} flour and 0-{fs['flour_forager']['water']} water. You cannot bake.",
            "water_forager": f"You are a water forager. When you forage you find 0-{fs['water_forager']['flour']} flour and 0-{fs['water_forager']['water']} water. You cannot bake.",
            "baker": f"You are a baker. You turn 1 flour + 1 water into 2 bread (the only food that satisfies hunger). You forage poorly (0-{fs['baker']['flour']} flour, 0-{fs['baker']['water']} water).",
        }
        prompt = SYSTEM_TEMPLATE.format(
            handle=self.handle,
            personality=self.personality,
            role_description=role_descriptions.get(self.role, "unknown role"),
        )
        parts = [prompt, self._build_state_block()]
        state = self._format_state_sections()
        if state:
            parts.append(state)
        return "\n\n".join(parts)

    def _build_state_block(self) -> str:
        return SOUL_TEMPLATE.format(soul=self.soul or "(empty)")
