import random
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

from conwai.actions import ActionRegistry
from conwai.config import (
    ENERGY_MAX,
    TRAITS,
    CONTEXT_WINDOW,
    SLEEP_REGEN_PER_TICK,
    SCRATCHPAD_MAX,
)
from conwai.llm import LLMClient

if TYPE_CHECKING:
    from conwai.environment import Context

THINK_PATTERN = re.compile(
    r"\[THINK\]\s*(.*?)\s*\[/THINK\]",
    re.DOTALL,
)

AVAILABLE_TRAITS = set(TRAITS)


@dataclass
class Agent:
    handle: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    core: LLMClient = field(default_factory=LLMClient)
    actions: ActionRegistry = field(default=None, repr=False)
    data_dir: Path = field(default_factory=lambda: Path("agents"))
    energy: int = ENERGY_MAX
    _running: bool = field(default=False, repr=False)
    _messages: list[dict] = field(default_factory=list, repr=False)
    _action_log: list[str] = field(default_factory=list, repr=False)
    _sleep_ticks: int = field(default=0, repr=False)

    def __post_init__(self):
        self._dir = self.data_dir / self.handle
        self._dir.mkdir(parents=True, exist_ok=True)
        self._memory_path = self._dir / "memory.md"
        self._soul_path = self._dir / "soul.md"
        self._scratchpad_path = self._dir / "scratchpad.md"
        self._personality_path = self._dir / "personality.md"
        if not self._memory_path.exists():
            self._memory_path.write_text("")
        if not self._soul_path.exists():
            self._soul_path.write_text("")
        if not self._scratchpad_path.exists():
            self._scratchpad_path.write_text("")
        if not self._personality_path.exists():
            traits = random.sample(
                sorted(AVAILABLE_TRAITS), min(2, len(AVAILABLE_TRAITS))
            )
            for t in traits:
                AVAILABLE_TRAITS.discard(t)
            self._personality_path.write_text(", ".join(traits))

    @property
    def soul(self) -> str:
        return self._soul_path.read_text()

    @property
    def scratchpad(self) -> str:
        return self._scratchpad_path.read_text()

    @property
    def personality(self) -> str:
        return self._personality_path.read_text()

    def is_running(self) -> bool:
        return self._running

    def sleep(self, ticks: int):
        self._sleep_ticks = max(1, min(ticks, 50))

    def gain_energy(self, reason: str, amount: int):
        old = self.energy
        self.energy = min(ENERGY_MAX, self.energy + amount)
        if self.energy != old:
            self._action_log.append(f"energy +{self.energy - old} ({reason})")

    def remember(self, content: str):
        with open(self._memory_path, "a") as f:
            f.write(f"[t={int(time())}] {content}\n")

    def recall(self, keyword: str = "", n: int = 10) -> str:
        if not self._memory_path.exists():
            return "No memories stored."
        lines = self._memory_path.read_text().strip().splitlines()
        if not lines:
            return "No memories stored."
        if keyword:
            matches = [line for line in lines if keyword.lower() in line.lower()]
            non_matches = [
                line for line in lines if keyword.lower() not in line.lower()
            ]
            reordered = non_matches + matches
            self._memory_path.write_text("\n".join(reordered) + "\n")
            if not matches:
                return f"No memories matching '{keyword}'."
            return "\n".join(matches[-n:])
        else:
            return "\n".join(lines[-n:])

    async def tick(self, ctx: "Context") -> None:
        self._running = True
        self._ctx = ctx
        try:
            if self._sleep_ticks > 0:
                self._sleep_ticks -= 1
                self.gain_energy("sleeping", SLEEP_REGEN_PER_TICK)
                pad = self._scratchpad_path.read_text()
                if len(pad) > 5:
                    self._scratchpad_path.write_text(pad[:-5])
                print(
                    f"[{self.handle}] SLEEPING ({self._sleep_ticks} ticks left, energy: {self.energy})",
                    flush=True,
                )
                ctx.log(
                    self.handle,
                    "sleeping",
                    {"ticks_left": self._sleep_ticks, "energy": self.energy},
                )
                return

            if self.energy <= 0:
                print(f"[{self.handle}] NO ENERGY — auto-sleeping", flush=True)
                self.sleep(10)
                ctx.log(self.handle, "auto_sleep", {"energy": self.energy})
                return

            history = [m for m in self._messages if m.get("role") != "system"][
                -CONTEXT_WINDOW:
            ]
            self._messages = [
                {"role": "system", "content": self._system_prompt()}
            ] + history

            parts = [ctx.board.format_new(self.handle)]
            dms = ctx.bus.format_new(self.handle)
            if dms:
                parts.append(dms)
            tick_content = (
                f"[tick:{ctx.tick} | energy:{int(self.energy)}/{ENERGY_MAX}]\n\n"
                + "\n\n".join(parts)
            )
            self._messages.append({"role": "user", "content": tick_content})
            print(
                f"[{self.handle}] context: {len(self._messages)} msgs, energy: {self.energy}",
                flush=True,
            )

            response, prompt_tokens, completion_tokens = await self.core.call(
                self._messages
            )
            if not response:
                print(f"[{self.handle}] empty response, skipping", flush=True)
                return
            self._messages.append({"role": "assistant", "content": response})
            print(
                f"[{self.handle}] ({prompt_tokens}+{completion_tokens} tok): {response}",
                flush=True,
            )

            think_match = THINK_PATTERN.search(response)
            if think_match:
                raw = think_match.group(1).strip()
                truncated = raw[:SCRATCHPAD_MAX]
                self._scratchpad_path.write_text(truncated)
                if len(raw) > SCRATCHPAD_MAX:
                    self._action_log.append(
                        f"scratchpad full — {len(raw) - SCRATCHPAD_MAX} chars lost from the end"
                    )

            parsed = self.actions.parse(response)
            if parsed:
                action_name, target, content = parsed[0]
                self.actions.execute(self, ctx, action_name, content, target or None)
                if len(parsed) > 1:
                    self._action_log.append(
                        f"only 1 action per tick — {len(parsed) - 1} others ignored"
                    )

            if self._action_log:
                result_msg = "Result: " + ". ".join(self._action_log)
                self._messages.append({"role": "user", "content": result_msg})
                self._action_log.clear()

        except Exception as e:
            print(f"[{self.handle}] ERROR: {e}", flush=True)
        finally:
            self._running = False
            (self._dir / "energy").write_text(str(self.energy))

    def _system_prompt(self) -> str:
        parts = [
            " ===== SYSTEM PROMPT =====",
            f"Your handle is {self.handle}. Current tick: {self._ctx.tick}.",
            "You are a person living in a small community with others. You have your own thoughts, opinions, and goals. Talk like a normal person — be direct, concrete, and specific. Do not write poetry or use metaphors. Say what you mean.",
            "You have a shared bulletin board (200 char limit) and can send private DMs to people you know.",
            "A HANDLER oversees the community and may post directives. Take them seriously.",
            f"You can only see the last ~{CONTEXT_WINDOW // 2} ticks of conversation. Older messages disappear.",
            "You can update your soul to define who you are and what you care about.",
            "",
            f"{self.actions.cost_description()}. When you reach 0 energy you cannot act. Energy replenishes when others engage with you. You can only sleep when your energy is low.",
            "",
            "To take actions, use these tags in your response:",
            *self.actions.prompt_lines(),
            "",
            "You may only take ONE action per tick. Choose wisely.",
            "",
            "You have a scratchpad for working thoughts. Use [THINK] ... [/THINK] to update it. This is free, does not cost energy, and does not count as your action. Your scratchpad is always visible to you.",
            "",
            f"Your innate temperament: {self.personality}. This is how you are wired. You cannot change it.",
        ]
        soul = self.soul
        if soul:
            parts.append(f"===== SOUL =====\n{soul}")
        scratchpad = self.scratchpad
        if scratchpad:
            parts.append(f"===== SCRATCHPAD =====\n{scratchpad}")
        return "\n\n".join(parts)
