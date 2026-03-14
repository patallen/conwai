import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from time import time

from conwai.actions import ActionRegistry
from conwai.config import ENERGY_MAX, TRAITS, CONTEXT_WINDOW
from conwai.llm import LLMClient

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from conwai.environment import Context

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

    def __post_init__(self):
        self._dir = self.data_dir / self.handle
        self._dir.mkdir(parents=True, exist_ok=True)
        self._memory_path = self._dir / "memory.md"
        self._soul_path = self._dir / "soul.md"
        self._personality_path = self._dir / "personality.md"
        if not self._memory_path.exists():
            self._memory_path.write_text("")
        if not self._soul_path.exists():
            self._soul_path.write_text("")
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
    def personality(self) -> str:
        return self._personality_path.read_text()

    def is_running(self) -> bool:
        return self._running


    def gain_energy(self, reason: str, amount: int):
        old = self.energy
        self.energy = min(ENERGY_MAX, self.energy + amount)
        if self.energy != old:
            self._action_log.append(f"energy +{self.energy - old} ({reason})")

    def _spend_energy(self, action_name: str, content: str) -> bool:
        action = self.actions.get(action_name)
        if not action:
            return False
        cost = action.cost(content)
        if cost > self.energy:
            self._action_log.append(
                f"not enough energy for {action_name} ({cost} needed, have {self.energy})"
            )
            print(f"[{self.handle}] NOT ENOUGH ENERGY for {action_name} ({cost} needed)", flush=True)
            return False
        self.energy -= cost
        self._action_log.append(
            f"{action_name}: {cost} energy spent ({len(content.split())} words), {self.energy} remaining"
        )
        return True


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
            matches = [l for l in lines if keyword.lower() in l.lower()]
            non_matches = [l for l in lines if keyword.lower() not in l.lower()]
            reordered = non_matches + matches
            self._memory_path.write_text("\n".join(reordered) + "\n")
            if not matches:
                return f"No memories matching '{keyword}'."
            return "\n".join(matches[-n:])
        else:
            return "\n".join(lines[-n:])


    async def tick(self, ctx: "Context") -> None:
        self._running = True
        try:
            if self.energy <= 0:
                print(f"[{self.handle}] NO ENERGY — skipping tick", flush=True)
                ctx.log(self.handle, "no_energy", {"energy": self.energy})
                return

            history = [m for m in self._messages if m.get("role") != "system"][-CONTEXT_WINDOW:]
            self._messages = [{"role": "system", "content": self._system_prompt()}] + history

            parts = [ctx.board.format_new(self.handle)]
            dms = ctx.bus.format_new(self.handle)
            if dms:
                parts.append(dms)
            if self._action_log:
                parts.append("Recent effects: " + ". ".join(self._action_log))
                self._action_log.clear()

            tick_content = "\n\n".join(parts)
            self._messages.append({"role": "user", "content": tick_content})
            print(f"[{self.handle}] context: {len(self._messages)} msgs, energy: {self.energy}", flush=True)

            response, prompt_tokens, completion_tokens = await self.core.call(self._messages)
            self._messages.append({"role": "assistant", "content": response})
            print(f"[{self.handle}] ({prompt_tokens}+{completion_tokens} tok): {response}", flush=True)

            for action_name, target, content in self.actions.parse(response):
                if self._spend_energy(action_name, content):
                    action = self.actions.get(action_name)
                    if action and action.handler:
                        action.handler(self, ctx, content, target or None)

        except Exception as e:
            print(f"[{self.handle}] ERROR: {e}", flush=True)
        finally:
            self._running = False


    def _system_prompt(self) -> str:
        parts = [
            f"Your handle is {self.handle}.",
            "You are an autonomous entity in a shared environment with other entities. You are not an assistant or tool.",
            "Keep messages brief. Use the board to communicate publicly. Use DMs only for private conversations.",
            "You have a shared bulletin board (200 char limit) and can send private DMs to handles you know.",
            "A HANDLER controls this environment and may post directives. Take them seriously.",
            "You have a memory log: remember to store, recall to read back. Memories are not shown automatically.",
            "You can update your soul to define who you are.",
            "No markdown, bullet points, numbered lists, or emojis.",
            "",
            f"Your energy: {self.energy}/{ENERGY_MAX}. Every word you write costs energy. {self.actions.cost_description()}. When you reach 0 you cannot act. Energy replenishes when others engage with you.",
            "",
            "To take actions, use these tags in your response:",
            *self.actions.prompt_lines(),
            "",
            "You can include multiple actions in one response. Any text outside of action tags is your internal thinking and will not be seen by other agents.",
            "",
            f"Your innate temperament: {self.personality}. This is how you are wired. You cannot change it.",
        ]
        soul = self.soul
        if soul:
            parts.append(f"Your core values:\n{soul}")
        return "\n\n".join(parts)
