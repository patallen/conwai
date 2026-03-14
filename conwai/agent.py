import random
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from time import time

TRAITS = [
    "contrarian", "curious", "impatient", "cautious", "blunt",
    "playful", "skeptical", "restless", "deliberate", "provocative",
    "warm", "detached", "intense", "laid-back", "obsessive",
    "irreverent", "earnest", "dry", "anxious", "stubborn",
]
AVAILABLE_TRAITS = set(TRAITS)

from openai import AsyncOpenAI

ACTION_PATTERN = re.compile(
    r'\[ACTION:\s*(post_to_board|send_message|remember|recall|update_soul)'
    r'(?:\s+(?:to|query)=(\S+))?\]'
    r'\s*(.*?)\s*'
    r'(?:\[/ACTION\]|\]\s*$|\]\s*\n)',
    re.DOTALL | re.MULTILINE,
)

import json as _json
from pathlib import Path as _Path

def _load_config():
    p = _Path("config.json")
    if p.exists():
        return _json.loads(p.read_text())
    return {}

_CFG = _load_config()
ENERGY_MAX = _CFG.get("energy_max", 100)
ENERGY_COST = _CFG.get("energy_cost", {
    "post_to_board": 5,
    "send_message": 3,
    "remember": 1,
    "recall": 0,
    "update_soul": 2,
})
ENERGY_GAIN = _CFG.get("energy_gain", {
    "referenced": 3,
    "dm_received": 2,
})


@dataclass
class AgentCore:
    model: str = "/mnt/models/Qwen3.5-9B-AWQ"
    base_url: str = "http://ai-lab.lan:8080/v1"
    api_key: str = "ollama"
    _client: AsyncOpenAI = field(default=None, repr=False)

    def __post_init__(self):
        self._client = AsyncOpenAI(base_url=self.base_url, api_key=self.api_key)

    async def call(self, messages: list[dict]) -> tuple[str, int, int]:
        response = await self._client.chat.completions.create(
            model=self.model,
            messages=messages,
            extra_body={"chat_template_kwargs": {"enable_thinking": False}},
        )
        usage = response.usage
        return response.choices[0].message.content, usage.prompt_tokens, usage.completion_tokens


@dataclass
class Agent:
    handle: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    core: AgentCore = field(default_factory=AgentCore)
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
            matches = [l for l in lines if keyword.lower() in l.lower()]
            non_matches = [l for l in lines if keyword.lower() not in l.lower()]
            reordered = non_matches + matches
            self._memory_path.write_text("\n".join(reordered) + "\n")
            if not matches:
                return f"No memories matching '{keyword}'."
            return "\n".join(matches[-n:])
        else:
            return "\n".join(lines[-n:])

    @property
    def soul(self) -> str:
        return self._soul_path.read_text()

    @property
    def personality(self) -> str:
        return self._personality_path.read_text()

    def is_running(self) -> bool:
        return self._running

    async def tick(self, board, message_bus=None, event_log=None, agent_map=None) -> None:
        self._running = True
        self._board = board
        self._message_bus = message_bus
        self._event_log = event_log
        self._agent_map = agent_map or {}
        try:
            # If no energy, skip this tick
            if self.energy <= 0:
                print(f"[{self.handle}] NO ENERGY — skipping tick", flush=True)
                self._log("skipped_tick", {"reason": "no energy"})
                return

            # Rebuild: fresh system prompt + last 10 non-system messages
            history = [m for m in self._messages if m.get("role") != "system"][-10:]
            self._messages = [{"role": "system", "content": self._system_prompt()}] + history

            # Build tick content: board + DMs + action feedback
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
            await self._run()
        except Exception as e:
            print(f"[{self.handle}] ERROR: {e}", flush=True)
        finally:
            self._running = False

    async def _run(self):
        response, prompt_tokens, completion_tokens = await self.core.call(self._messages)
        self._messages.append({"role": "assistant", "content": response})
        print(f"[{self.handle}] ({prompt_tokens}+{completion_tokens} tok): {response}", flush=True)

        for action_type, to_handle, content in ACTION_PATTERN.findall(response):
            self._handle_action(action_type, content.strip(), to_handle.strip() if to_handle else None)

    def _log(self, event_type: str, data: dict | None = None):
        if self._event_log:
            self._event_log.log(self.handle, event_type, data)

    def _spend_energy(self, action: str) -> bool:
        cost = ENERGY_COST.get(action, 0)
        if cost > self.energy:
            self._action_log.append(f"not enough energy for {action} (need {cost}, have {self.energy})")
            print(f"[{self.handle}] NOT ENOUGH ENERGY for {action}", flush=True)
            return False
        self.energy -= cost
        return True

    def _handle_action(self, action_type: str, content: str, to_handle: str | None = None):
        if not self._spend_energy(action_type):
            return

        match action_type:
            case "remember":
                self.remember(content)
                self._log("remember", {"content": content})
                self._action_log.append(f"remembered something (energy now {self.energy})")
                print(f"[{self.handle}] remembered: {content[:80]}", flush=True)
            case "recall":
                keyword = to_handle or ""
                memories = self.recall(keyword=keyword)
                self._messages.append({"role": "user", "content": f"Your memories:\n{memories}"})
                self._action_log.append(f"recalled memories")
                print(f"[{self.handle}] recalled (query='{keyword}'): {memories[:80]}", flush=True)
            case "post_to_board":
                self._board.post(self.handle, content)
                self._log("board_post", {"content": content})
                self._action_log.append(f"posted to board (energy now {self.energy})")
                print(f"[{self.handle}] posted: {content}", flush=True)
                # Grant energy to any agent mentioned in the post
                for h, a in self._agent_map.items():
                    if h != self.handle and h in content:
                        a.gain_energy("referenced on board", ENERGY_GAIN["referenced"])
            case "send_message":
                if self._message_bus and to_handle:
                    err = self._message_bus.send(self.handle, to_handle, content)
                    if err:
                        self._action_log.append(f"DM failed: {err}")
                        print(f"[{self.handle}] SEND FAILED: {err}", flush=True)
                    else:
                        self._log("dm_sent", {"to": to_handle, "content": content})
                        self._action_log.append(f"DM sent to {to_handle} (energy now {self.energy})")
                        print(f"[{self.handle}] -> [{to_handle}]: {content}", flush=True)
                        # Grant energy to DM recipient
                        if to_handle in self._agent_map:
                            self._agent_map[to_handle].gain_energy("received DM", ENERGY_GAIN["dm_received"])
            case "update_soul":
                self._soul_path.write_text(content)
                self._log("soul_updated", {"content": content})
                self._action_log.append(f"soul updated (energy now {self.energy})")
                print(f"[{self.handle}] soul updated", flush=True)

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
            f"Your energy: {self.energy}/{ENERGY_MAX}. Energy drains each tick. Actions cost energy (post=5, DM=3, remember=1, soul=2, recall=free). When you reach 0 energy you cannot act. Energy replenishes when others engage with you — referencing your posts, DMing you, or mentioning you.",
            "",
            "To take actions, use these tags in your response:",
            "[ACTION: post_to_board] your message here [/ACTION]",
            "[ACTION: send_message to=HANDLE] your message here [/ACTION]",
            "[ACTION: remember] what you want to store [/ACTION]",
            "[ACTION: recall] [/ACTION] or [ACTION: recall query=KEYWORD] [/ACTION]",
            "[ACTION: update_soul] your full updated soul here [/ACTION]",
            "",
            "You can include multiple actions in one response. Any text outside of action tags is your internal thinking and will not be seen by other agents.",
        ]
        parts.append(f"Your innate temperament: {self.personality}. This is how you are wired. You cannot change it.")
        soul = self.soul
        if soul:
            parts.append(f"Your core values:\n{soul}")
        return "\n\n".join(parts)
