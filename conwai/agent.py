from __future__ import annotations

import asyncio
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

import conwai.config as config
from conwai.config import (
    CONTEXT_WINDOW,
    ENERGY_MAX,
    HUNGER_MAX,
    TRAITS,
)
import logging

log = logging.getLogger("conwai")

if TYPE_CHECKING:
    from conwai.app import Context
    from conwai.brain import Brain

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_TEMPLATE = (PROMPTS_DIR / "system.md").read_text()
IDENTITY_TEMPLATE = (PROMPTS_DIR / "identity.md").read_text()
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
    brain: Brain | None = field(default=None, repr=False)
    coins: float = ENERGY_MAX
    role: str = ""  # flour_forager, water_forager, baker
    flour: int = 0
    water: int = 0
    bread: int = 0
    hunger: int = HUNGER_MAX
    thirst: int = HUNGER_MAX
    context_window: int = CONTEXT_WINDOW
    personality: str = ""
    soul: str = ""
    memory: str = ""
    alive: bool = True
    born_tick: int = 0
    code_fragment: str | None = None

    messages: list[dict] = field(default_factory=list, repr=False)
    system_prompt: str = field(default="", repr=False)

    _inbox: list[tuple[str, str, int]] = field(default_factory=list, init=False, repr=False)  # (from_handle, resource, amount)
    _running: bool = field(default=False, init=False, repr=False)
    _pending_summary: asyncio.Task | None = field(default=None, init=False, repr=False)
    _pending_compaction: asyncio.Task | None = field(default=None, init=False, repr=False)
    _action_log: list[str] = field(default_factory=list, init=False, repr=False)
    _energy_log: list[str] = field(default_factory=list, init=False, repr=False)
    _board_history: list[str] = field(default_factory=list, init=False, repr=False)
    _dm_history: list[str] = field(default_factory=list, init=False, repr=False)
    _ledger: list[str] = field(default_factory=list, init=False, repr=False)
    _compact_needed: bool = field(default=False, init=False, repr=False)
    _dm_sent_this_tick: int = field(default=0, init=False, repr=False)
    _foraging: bool = field(default=False, init=False, repr=False)

    def __post_init__(self):
        if not self.personality:
            self.personality = ", ".join(assign_traits())

    @property
    def is_running(self) -> bool:
        return self._running

    def begin_tick(self) -> None:
        self._running = True
        self._dm_sent_this_tick = 0
        self._foraging = False
        self._llm_failed = False

    def end_tick(self) -> None:
        self._running = False

    def _stamp(self, tick: int, entry: str) -> str:
        return f"[{self._tick_to_timestamp(tick)}] {entry}"

    def record_board(self, tick: int, entry: str) -> None:
        self._board_history.append(self._stamp(tick, entry))
        self._board_history = self._board_history[-config.STATE_BOARD_LENGTH:]

    def record_dm(self, tick: int, entry: str) -> None:
        self._dm_history.append(self._stamp(tick, entry))
        self._dm_history = self._dm_history[-config.STATE_INTERACTIONS_LENGTH:]

    def record_ledger(self, tick: int, entry: str) -> None:
        self._ledger.append(self._stamp(tick, entry))
        self._ledger = self._ledger[-config.STATE_LEDGER_LENGTH:]

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
        self.memory = content[:config.MEMORY_MAX]
        return max(0, len(content) - config.MEMORY_MAX)

    def decay_memory(self, chars: int = 5) -> None:
        if len(self.memory) > chars:
            self.memory = self.memory[:-chars]

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

        # Ensure identity message is always first
        identity = self._build_identity_message()
        if self.messages and self.messages[0].get("content", "").startswith("Your handle is"):
            self.messages[0] = {"role": "user", "content": identity}
        else:
            self.messages.insert(0, {"role": "user", "content": identity})

        # Record board posts and DMs into rolling history
        new_posts = ctx.board.read_new(self.handle)
        for p in new_posts:
            self.record_board(ctx.tick, f"{p.handle}: {p.content}")
        new_dms = ctx.bus.receive(self.handle)
        for dm in new_dms:
            self.record_dm(ctx.tick, f"{dm.from_handle}: {dm.content}")

        # Flush inbox — resources received from other agents last tick
        if self._inbox:
            for from_handle, resource, amount in self._inbox:
                if resource == "flour":
                    self.flour += amount
                elif resource == "water":
                    self.water += amount
                elif resource == "bread":
                    self.bread += amount
                self.record_ledger(ctx.tick, f"received {amount} {resource} from {from_handle}")
            self._inbox.clear()

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
            parts.append(f"WARNING: You are hungry (hunger: {self.hunger}/100, bread: {self.bread}). Eat bread or raw flour to restore hunger.")
        if self.thirst <= 30:
            parts.append(f"WARNING: You are thirsty (thirst: {self.thirst}/100, water: {self.water}). Drink water to restore thirst.")

        # Include rolling history in tick message
        state = self._format_state_sections()
        if state:
            parts.append(state)

        tick_content = TICK_TEMPLATE.format(
            timestamp=self._tick_to_timestamp(ctx.tick),
            coins=int(self.coins),
            hunger=self.hunger,
            thirst=self.thirst,
            flour=self.flour,
            water=self.water,
            bread=self.bread,
            content="\n\n".join(parts),
        )
        self.messages.append({"role": "user", "content": tick_content})
        log.info(f"[{self.handle}] context: {len(self.messages)} msgs ({self._context_chars()} chars), coins: {self.coins}{' [COMPACT NEEDED]' if self._compact_needed else ''}")

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
        return SYSTEM_TEMPLATE

    def _build_identity_message(self) -> str:
        from conwai.config import FORAGE_SKILL_BY_ROLE
        fs = FORAGE_SKILL_BY_ROLE
        role_descriptions = {
            "flour_forager": f"You are a flour forager. When you forage you find 0-{fs['flour_forager']['flour']} flour and 0-{fs['flour_forager']['water']} water. You cannot bake.",
            "water_forager": f"You are a water forager. When you forage you find 0-{fs['water_forager']['flour']} flour and 0-{fs['water_forager']['water']} water. You cannot bake.",
            "baker": f"You are a baker. You turn {config.BAKE_COST['flour']} flour + {config.BAKE_COST['water']} water into {config.BAKE_YIELD} bread. You forage poorly (0-{fs['baker']['flour']} flour, 0-{fs['baker']['water']} water).",
        }
        soul_block = SOUL_TEMPLATE.format(soul=self.soul or "(empty)")
        return IDENTITY_TEMPLATE.format(
            handle=self.handle,
            personality=self.personality,
            role_description=role_descriptions.get(self.role, "unknown role"),
            soul=soul_block,
        )
