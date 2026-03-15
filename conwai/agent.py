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
    SCRATCHPAD_MAX,
    SLEEP_REGEN_PER_TICK,
    TRAITS,
)
from conwai.llm import LLMClient, LLMResponse

if TYPE_CHECKING:
    from conwai.environment import Context

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
SYSTEM_TEMPLATE = (PROMPTS_DIR / "system.md").read_text()
TICK_TEMPLATE = (PROMPTS_DIR / "tick.md").read_text()
SOUL_TEMPLATE = (PROMPTS_DIR / "soul.md").read_text()
SCRATCHPAD_TEMPLATE = (PROMPTS_DIR / "scratchpad.md").read_text()
STRATEGY_TEMPLATE = (PROMPTS_DIR / "strategy.md").read_text()

_available_traits = set(TRAITS)


def assign_traits(n: int = 2) -> list[str]:
    if len(_available_traits) < n:
        _available_traits.update(TRAITS)
    chosen = random.sample(sorted(_available_traits), n)
    _available_traits.difference_update(chosen)
    return chosen


@dataclass
class AgentState:
    dir: Path
    memory_path: Path
    soul_path: Path
    scratchpad_path: Path
    personality_path: Path
    strategy_path: Path
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
            strategy_path=d / "strategy.md",
            energy_path=d / "energy",
        )
        for p in [
            state.memory_path,
            state.soul_path,
            state.scratchpad_path,
            state.strategy_path,
        ]:
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

    @property
    def strategy(self) -> str:
        return self.strategy_path.read_text()

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

    def persist_context(self, system_prompt: str, messages: list[dict]) -> None:
        data = {"system": system_prompt, "messages": messages}
        (self.dir / "context.json").write_text(json.dumps(data, indent=2))


@dataclass
class Agent:
    handle: str = field(default_factory=lambda: uuid4().hex[:8])
    core: LLMClient = field(default_factory=LLMClient)
    actions: ActionRegistry = field(default=None, repr=False)
    data_dir: Path = field(default_factory=lambda: Path("data/agents"))
    energy: float = ENERGY_MAX
    context_window: int = CONTEXT_WINDOW

    _state: AgentState = field(default=None, init=False, repr=False)
    _running: bool = field(default=False, init=False, repr=False)
    _messages: list[dict] = field(default_factory=list, init=False, repr=False)
    _action_log: list[str] = field(default_factory=list, init=False, repr=False)
    _energy_log: list[str] = field(default_factory=list, init=False, repr=False)
    _sleep_ticks: int = field(default=0, init=False, repr=False)
    _system_prompt: str = field(default="", init=False, repr=False)
    alive: bool = field(default=True, init=False, repr=False)
    code_fragment: str | None = field(default=None, init=False, repr=False)

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
    def strategy(self) -> str:
        return self._state.strategy

    @property
    def is_running(self) -> bool:
        return self._running

    def sleep(self, ticks: int) -> None:
        self._sleep_ticks = max(1, min(ticks, 50))

    def gain_energy(self, reason: str, amount: int) -> None:
        old = self.energy
        self.energy = self.energy + amount
        gained = self.energy - old
        if gained > 0:
            self._energy_log.append(f"energy +{int(gained)} ({reason})")

    async def tick(self, ctx: Context) -> None:
        self._running = True
        try:
            if self._sleep_ticks > 0:
                self._handle_sleep(ctx)
                return

            if self.energy <= 0:
                self.alive = False
                print(f"[{self.handle}] DEAD — no energy", flush=True)
                ctx.log(
                    self.handle,
                    "agent_died",
                    {"reason": "no_energy", "energy": self.energy},
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
            self._state.persist_energy(self.energy)
            self._state.persist_context(self._system_prompt, self._messages)

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
        turn_count = 0
        cut = 0
        for i in range(len(self._messages) - 1, -1, -1):
            if self._messages[i]["role"] == "user":
                turn_count += 1
                if turn_count > self.context_window:
                    cut = i
                    break
        self._messages = self._messages[cut:]
        self._system_prompt = self._build_system_prompt()

        parts = [ctx.board.format_new(self.handle)]
        dms = ctx.bus.format_new(self.handle)
        if dms:
            parts.append(dms)
        if self._energy_log:
            parts.append("Energy changes: " + ". ".join(self._energy_log))
            self._energy_log.clear()
        if self.code_fragment:
            parts.append(f"YOUR CODE FRAGMENT: {self.code_fragment}")
        if ctx.tick % 20 == 0:
            parts.append("What have you learned recently? Update your rules.")
        tick_content = TICK_TEMPLATE.format(
            tick=ctx.tick,
            energy=int(self.energy),
            content="\n\n".join(parts),
        )
        self._messages.append({"role": "user", "content": tick_content})
        print(
            f"[{self.handle}] context: {len(self._messages)} msgs, energy: {self.energy}",
            flush=True,
        )

    async def _get_response(self, ctx: Context) -> LLMResponse | None:
        resp = await self.core.call(
            self._system_prompt,
            self._messages,
            tools=self.actions.tool_definitions(),
        )
        if not resp.text and not resp.tool_calls:
            print(f"[{self.handle}] empty response, skipping", flush=True)
            return None

        MAX_REASONING = 200
        assistant_msg: dict = {"role": "assistant"}
        if resp.text:
            if len(resp.text) > MAX_REASONING:
                assistant_msg["content"] = (
                    resp.text[:MAX_REASONING]
                    + "... (truncated — use scratchpad to preserve important thoughts)"
                )
            else:
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
        self._messages.append(assistant_msg)

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
            self._messages.append(
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
            context_ticks=self.context_window // 2,
            personality=self.personality,
        )
        return prompt + "\n\n" + self._build_state_block()

    def _build_state_block(self) -> str:
        raw_rules = self.strategy.strip()
        if raw_rules:
            lines = [r.strip() for r in raw_rules.splitlines() if r.strip()]
            numbered = "\n".join(f"{i + 1}. {line}" for i, line in enumerate(lines))
        else:
            numbered = "(no rules yet)"
        parts = [
            STRATEGY_TEMPLATE.format(rules=numbered),
            SOUL_TEMPLATE.format(soul=self.soul or "(empty)"),
            SCRATCHPAD_TEMPLATE.format(scratchpad=self.scratchpad or "(empty)"),
        ]
        return "\n\n".join(parts)
