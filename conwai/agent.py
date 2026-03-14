import json
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


@dataclass
class AgentCore:
    model: str = "/mnt/models/Qwen3.5-9B-AWQ"
    base_url: str = "http://ollama.lan:11434/v1"
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
    _running: bool = field(default=False, repr=False)
    _messages: list[dict] = field(default_factory=list, repr=False)

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
            # rewrite file with matches promoted to end (most recent position)
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

    async def tick(self, board, message_bus=None, event_log=None) -> None:
        self._running = True
        self._board = board
        self._message_bus = message_bus
        self._event_log = event_log
        try:
            # Rebuild: fresh system prompt + last 10 non-system messages
            history = [m for m in self._messages if m.get("role") != "system"][-10:]
            self._messages = [{"role": "system", "content": self._system_prompt()}] + history
            parts = [board.format_new(self.handle)]
            if message_bus:
                dms = message_bus.format_new(self.handle)
                if dms:
                    parts.append(dms)
            tick_content = "\n\n".join(parts)
            self._messages.append({"role": "user", "content": tick_content})
            print(f"[{self.handle}] ctx: {len(self._messages)} msgs", flush=True)
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

    def _handle_action(self, action_type: str, content: str, to_handle: str | None = None):
        match action_type:
            case "remember":
                self.remember(content)
                self._log("remember", {"content": content})
                print(f"[{self.handle}] remembered: {content[:80]}", flush=True)
            case "recall":
                keyword = to_handle or ""  # reuses the to=/query= capture group
                memories = self.recall(keyword=keyword)
                self._messages.append({"role": "user", "content": f"Your memories:\n{memories}"})
                print(f"[{self.handle}] recalled (query='{keyword}'): {memories[:80]}", flush=True)
            case "post_to_board":
                self._board.post(self.handle, content)
                self._log("board_post", {"content": content})
                print(f"[{self.handle}] posted: {content}", flush=True)
            case "send_message":
                if self._message_bus and to_handle:
                    err = self._message_bus.send(self.handle, to_handle, content)
                    if err:
                        print(f"[{self.handle}] SEND FAILED: {err}", flush=True)
                    else:
                        self._log("dm_sent", {"to": to_handle, "content": content})
                        print(f"[{self.handle}] -> [{to_handle}]: {content}", flush=True)
            case "update_soul":
                self._soul_path.write_text(content)
                self._log("soul_updated", {"content": content})
                print(f"[{self.handle}] soul updated", flush=True)

    def _build_base_context(self):
        self._messages = [
            {"role": "system", "content": self._system_prompt()},
        ]

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
