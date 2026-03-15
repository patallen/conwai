from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import TYPE_CHECKING
from uuid import uuid4

from conwai.actions import ActionRegistry
from conwai.config import (
    CONTEXT_WINDOW,
    ENERGY_MAX,
    SCRATCHPAD_MAX,
    SLEEP_REGEN_PER_TICK,
    TRAITS,
)
from conwai.llm import LLMClient

if TYPE_CHECKING:
    from conwai.environment import Context

THINK_PATTERN = re.compile(r"\[THINK\]\s*(.*?)\s*\[/THINK\]", re.DOTALL)

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_TEMPLATE = (PROMPTS_DIR / "system.md").read_text()
TICK_TEMPLATE = (PROMPTS_DIR / "tick.md").read_text()
SOUL_TEMPLATE = (PROMPTS_DIR / "soul.md").read_text()
SCRATCHPAD_TEMPLATE = (PROMPTS_DIR / "scratchpad.md").read_text()

_available_traits = set(TRAITS)


def assign_traits(n: int = 2) -> list[str]:
    chosen = random.sample(sorted(_available_traits), min(n, len(_available_traits)))
    _available_traits.difference_update(chosen)
    return chosen


@dataclass
class AgentState:
    dir: Path
    memory_path: Path
    soul_path: Path
    scratchpad_path: Path
    personality_path: Path
    energy_path: Path

    @classmethod
    def init(cls, data_dir: Path, handle: str) -> AgentState:
        d = data_dir / handle
        d.mkdir(parents=True, exist_ok=True)
        state = cls(
            dir=d,
            memory_path=d / "memory.md",
            soul_path=d / "soul.md",
            scratchpad_path=d / "scratchpad.md",
            personality_path=d / "personality.md",
            energy_path=d / "energy",
        )
        for p in [state.memory_path, state.soul_path, state.scratchpad_path]:
            if not p.exists():
                p.write_text("")
        if not state.personality_path.exists():
            state.personality_path.write_text(", ".join(assign_traits()))
        return state

    @property
    def soul(self) -> str:
        return self.soul_path.read_text()

    @property
    def scratchpad(self) -> str:
        return self.scratchpad_path.read_text()

    @property
    def personality(self) -> str:
        return self.personality_path.read_text()

    def remember(self, content: str) -> None:
        with open(self.memory_path, "a") as f:
            f.write(f"[t={int(time())}] {content}\n")

    def recall(self, keyword: str = "", n: int = 10) -> str:
        if not self.memory_path.exists():
            return "No memories stored."
        lines = self.memory_path.read_text().strip().splitlines()
        if not lines:
            return "No memories stored."
        if not keyword:
            return "\n".join(lines[-n:])
        matches = [line for line in lines if keyword.lower() in line.lower()]
        non_matches = [line for line in lines if keyword.lower() not in line.lower()]
        self.memory_path.write_text("\n".join(non_matches + matches) + "\n")
        if not matches:
            return f"No memories matching '{keyword}'."
        return "\n".join(matches[-n:])

    def write_scratchpad(self, content: str) -> int:
        truncated = content[:SCRATCHPAD_MAX]
        self.scratchpad_path.write_text(truncated)
        return max(0, len(content) - SCRATCHPAD_MAX)

    def decay_scratchpad(self, chars: int = 5) -> None:
        pad = self.scratchpad
        if len(pad) > chars:
            self.scratchpad_path.write_text(pad[:-chars])

    def persist_energy(self, energy: float) -> None:
        self.energy_path.write_text(str(energy))


@dataclass
class Agent:
    handle: str = field(default_factory=lambda: uuid4().hex[:8])
    core: LLMClient = field(default_factory=LLMClient)
    actions: ActionRegistry = field(default=None, repr=False)
    data_dir: Path = field(default_factory=lambda: Path("data/agents"))
    energy: float = ENERGY_MAX

    _state: AgentState = field(default=None, init=False, repr=False)
    _running: bool = field(default=False, init=False, repr=False)
    _messages: list[dict] = field(default_factory=list, init=False, repr=False)
    _action_log: list[str] = field(default_factory=list, init=False, repr=False)
    _sleep_ticks: int = field(default=0, init=False, repr=False)
    _system_prompt: str = field(default="", init=False, repr=False)

    def __post_init__(self):
        self._state = AgentState.init(self.data_dir, self.handle)

    @property
    def soul(self) -> str:
        return self._state.soul

    @property
    def scratchpad(self) -> str:
        return self._state.scratchpad

    @property
    def personality(self) -> str:
        return self._state.personality

    @property
    def is_running(self) -> bool:
        return self._running

    def sleep(self, ticks: int) -> None:
        self._sleep_ticks = max(1, min(ticks, 50))

    def gain_energy(self, reason: str, amount: int) -> None:
        old = self.energy
        self.energy = min(ENERGY_MAX, self.energy + amount)
        gained = self.energy - old
        if gained > 0:
            self._action_log.append(f"energy +{int(gained)} ({reason})")

    def remember(self, content: str) -> None:
        self._state.remember(content)

    def recall(self, keyword: str = "", n: int = 10) -> str:
        return self._state.recall(keyword, n)

    def inject_context(self, content: str) -> None:
        self._messages.append({"role": "user", "content": content})

    async def tick(self, ctx: Context) -> None:
        self._running = True
        try:
            if self._sleep_ticks > 0:
                self._handle_sleep(ctx)
                return

            if self.energy <= 0:
                print(f"[{self.handle}] NO ENERGY — auto-sleeping", flush=True)
                self.sleep(10)
                ctx.log(self.handle, "auto_sleep", {"energy": self.energy})
                return

            self._rebuild_context(ctx)
            response = await self._get_response(ctx)
            if not response:
                return
            self._process_think(response)
            self._process_action(response, ctx)
            self._flush_action_log()

        except Exception as e:
            print(f"[{self.handle}] ERROR: {e}", flush=True)
        finally:
            self._running = False
            self._state.persist_energy(self.energy)

    def _handle_sleep(self, ctx: Context) -> None:
        self._sleep_ticks -= 1
        self.gain_energy("sleeping", SLEEP_REGEN_PER_TICK)
        self._state.decay_scratchpad()
        print(
            f"[{self.handle}] SLEEPING ({self._sleep_ticks} ticks left, energy: {int(self.energy)})",
            flush=True,
        )
        ctx.log(
            self.handle,
            "sleeping",
            {"ticks_left": self._sleep_ticks, "energy": self.energy},
        )

    def _rebuild_context(self, ctx: Context) -> None:
        self._messages = self._messages[-CONTEXT_WINDOW:]
        self._system_prompt = self._build_system_prompt(ctx.tick)

        parts = [ctx.board.format_new(self.handle)]
        dms = ctx.bus.format_new(self.handle)
        if dms:
            parts.append(dms)
        tick_content = TICK_TEMPLATE.format(
            tick=ctx.tick,
            energy=int(self.energy),
            energy_max=ENERGY_MAX,
            content="\n\n".join(parts),
        )
        self._messages.append({"role": "user", "content": tick_content})
        print(
            f"[{self.handle}] context: {len(self._messages)} msgs, energy: {self.energy}",
            flush=True,
        )

    async def _get_response(self, ctx: Context) -> str | None:
        response, prompt_tokens, completion_tokens = await self.core.call(
            self._system_prompt, self._messages
        )
        if not response:
            print(f"[{self.handle}] empty response, skipping", flush=True)
            return None
        self._messages.append({"role": "assistant", "content": response})
        print(
            f"[{self.handle}] ({prompt_tokens}+{completion_tokens} tok): {response}",
            flush=True,
        )
        return response

    def _process_think(self, response: str) -> None:
        match = THINK_PATTERN.search(response)
        if not match:
            return
        raw = match.group(1).strip()
        lost = self._state.write_scratchpad(raw)
        if lost > 0:
            self._action_log.append(f"scratchpad full — {lost} chars lost from the end")

    def _process_action(self, response: str, ctx: Context) -> None:
        parsed = self.actions.parse(response)
        if not parsed:
            return
        action_name, target, content = parsed[0]
        self.actions.execute(self, ctx, action_name, content, target or None)
        if len(parsed) > 1:
            self._action_log.append(
                f"only 1 action per tick — {len(parsed) - 1} others ignored"
            )

    def _flush_action_log(self) -> None:
        if not self._action_log:
            return
        result_msg = "Result: " + ". ".join(self._action_log)
        self._messages.append({"role": "user", "content": result_msg})
        self._action_log.clear()

    def _build_system_prompt(self, tick: int) -> str:
        prompt = SYSTEM_TEMPLATE.format(
            handle=self.handle,
            tick=tick,
            context_ticks=CONTEXT_WINDOW // 2,
            cost_description=self.actions.cost_description(),
            action_lines="\n".join(self.actions.prompt_lines()),
            personality=self.personality,
        )
        prompt += "\n\n" + SOUL_TEMPLATE.format(soul=self.soul or "(empty)")
        prompt += "\n\n" + SCRATCHPAD_TEMPLATE.format(
            scratchpad=self.scratchpad or "(empty)"
        )
        return prompt
