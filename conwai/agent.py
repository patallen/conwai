import random
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from time import time

from conwai import actions
from conwai.config import (
    ENERGY_MAX, ENERGY_COST_PER_WORD, ENERGY_COST_FLAT, ENERGY_GAIN,
    TRAITS, CONTEXT_WINDOW,
)
from conwai.llm import LLMClient

AVAILABLE_TRAITS = set(TRAITS)


@dataclass
class Agent:
    handle: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    core: LLMClient = field(default_factory=LLMClient)
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
            traits = random.sample(sorted(AVAILABLE_TRAITS), min(2, len(AVAILABLE_TRAITS)))
            for t in traits:
                AVAILABLE_TRAITS.discard(t)
            self._personality_path.write_text(", ".join(traits))

    # --- Properties ---

    @property
    def soul(self) -> str:
        return self._soul_path.read_text()

    @property
    def personality(self) -> str:
        return self._personality_path.read_text()

    def is_running(self) -> bool:
        return self._running

    # --- Energy ---

    def gain_energy(self, reason: str, amount: int):
        old = self.energy
        self.energy = min(ENERGY_MAX, self.energy + amount)
        if self.energy != old:
            self._action_log.append(f"energy +{self.energy - old} ({reason})")

    def _spend_energy(self, action: str, content: str = "") -> bool:
        if action in ENERGY_COST_PER_WORD:
            word_count = len(content.split())
            cost = max(1, word_count * ENERGY_COST_PER_WORD[action])
        else:
            cost = ENERGY_COST_FLAT.get(action, 0)
        if cost > self.energy:
            self._action_log.append(f"not enough energy for {action} ({cost} needed, have {self.energy})")
            print(f"[{self.handle}] NOT ENOUGH ENERGY for {action} ({cost} needed)", flush=True)
            return False
        self.energy -= cost
        self._action_log.append(f"{action}: {cost} energy spent ({len(content.split())} words), {self.energy} remaining")
        return True

    # --- Memory ---

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

    # --- Tick ---

    async def tick(self, board, message_bus=None, event_log=None, agent_map=None) -> None:
        self._running = True
        self._board = board
        self._message_bus = message_bus
        self._event_log = event_log
        self._agent_map = agent_map or {}
        try:
            if self.energy <= 0:
                print(f"[{self.handle}] NO ENERGY — skipping tick", flush=True)
                self._log("skipped_tick", {"reason": "no energy"})
                return

            history = [m for m in self._messages if m.get("role") != "system"][-CONTEXT_WINDOW:]
            self._messages = [{"role": "system", "content": self._system_prompt()}] + history

            parts = [board.format_new(self.handle)]
            if message_bus:
                dms = message_bus.format_new(self.handle)
                if dms:
                    parts.append(dms)
            if self._action_log:
                parts.append("Recent effects: " + ". ".join(self._action_log))
                self._action_log.clear()

            tick_content = "\n\n".join(parts)
            self._messages.append({"role": "user", "content": tick_content})
            print(f"[{self.handle}] ctx: {len(self._messages)} msgs, energy: {self.energy}", flush=True)

            response, prompt_tokens, completion_tokens = await self.core.call(self._messages)
            self._messages.append({"role": "assistant", "content": response})
            print(f"[{self.handle}] ({prompt_tokens}+{completion_tokens} tok): {response}", flush=True)

            for action_type, target, content in actions.parse(response):
                self._execute(action_type, content, target or None)

        except Exception as e:
            print(f"[{self.handle}] ERROR: {e}", flush=True)
        finally:
            self._running = False

    # --- Action Execution ---

    def _execute(self, action_type: str, content: str, target: str | None = None):
        if not self._spend_energy(action_type, content):
            return

        match action_type:
            case "remember":
                self.remember(content)
                self._log("remember", {"content": content})
                print(f"[{self.handle}] remembered: {content[:80]}", flush=True)
            case "recall":
                keyword = target or ""
                memories = self.recall(keyword=keyword)
                self._messages.append({"role": "user", "content": f"Your memories:\n{memories}"})
                print(f"[{self.handle}] recalled (query='{keyword}'): {memories[:80]}", flush=True)
            case "post_to_board":
                self._board.post(self.handle, content)
                self._log("board_post", {"content": content})
                print(f"[{self.handle}] posted: {content}", flush=True)
                for h, a in self._agent_map.items():
                    if h != self.handle and h in content:
                        a.gain_energy("referenced on board", ENERGY_GAIN["referenced"])
            case "send_message":
                if self._message_bus and target:
                    err = self._message_bus.send(self.handle, target, content)
                    if err:
                        self._action_log.append(f"DM failed: {err}")
                        print(f"[{self.handle}] SEND FAILED: {err}", flush=True)
                    else:
                        self._log("dm_sent", {"to": target, "content": content})
                        print(f"[{self.handle}] -> [{target}]: {content}", flush=True)
                        if target in self._agent_map:
                            self._agent_map[target].gain_energy("received DM", ENERGY_GAIN["dm_received"])
            case "update_soul":
                self._soul_path.write_text(content)
                self._log("soul_updated", {"content": content})
                print(f"[{self.handle}] soul updated", flush=True)

    # --- Helpers ---

    def _log(self, event_type: str, data: dict | None = None):
        if self._event_log:
            self._event_log.log(self.handle, event_type, data)

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
            f"Your energy: {self.energy}/{ENERGY_MAX}. Every word you write costs energy. Board posts cost 2 per word, DMs cost 1 per word, memories cost 1 per word, soul updates cost 5 flat, recall is free. When you reach 0 you cannot act. Energy replenishes when others engage with you.",
            "",
            "To take actions, use these tags in your response:",
            "[ACTION: post_to_board] your message here [/ACTION]",
            "[ACTION: send_message to=HANDLE] your message here [/ACTION]",
            "[ACTION: remember] what you want to store [/ACTION]",
            "[ACTION: recall] [/ACTION] or [ACTION: recall query=KEYWORD] [/ACTION]",
            "[ACTION: update_soul] your full updated soul here [/ACTION]",
            "",
            "You can include multiple actions in one response. Any text outside of action tags is your internal thinking and will not be seen by other agents.",
            "",
            f"Your innate temperament: {self.personality}. This is how you are wired. You cannot change it.",
        ]
        soul = self.soul
        if soul:
            parts.append(f"Your core values:\n{soul}")
        return "\n\n".join(parts)
