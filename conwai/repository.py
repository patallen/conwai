from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from conwai.config import SCRATCHPAD_MAX

if TYPE_CHECKING:
    from conwai.agent import Agent


class AgentRepository:
    def __init__(self, base_dir: Path = Path("data/agents")):
        self._base_dir = base_dir

    def _agent_dir(self, handle: str) -> Path:
        return self._base_dir / handle

    def init(self, agent: Agent) -> None:
        d = self._agent_dir(agent.handle)
        d.mkdir(parents=True, exist_ok=True)
        for name in ["soul.md", "scratchpad.md"]:
            p = d / name
            if not p.exists():
                p.write_text("")
        personality_path = d / "personality.md"
        if not personality_path.exists():
            from conwai.agent import assign_traits

            personality_path.write_text(", ".join(assign_traits()))

    def save(self, agent: Agent) -> None:
        d = self._agent_dir(agent.handle)
        d.mkdir(parents=True, exist_ok=True)
        (d / "energy").write_text(str(agent.energy))
        (d / "alive").write_text("true" if agent.alive else "false")
        (d / "context.json").write_text(
            json.dumps(
                {"system": agent._system_prompt, "messages": agent._messages},
                indent=2,
            )
        )

    def load_personality(self, handle: str) -> str:
        p = self._agent_dir(handle) / "personality.md"
        return p.read_text() if p.exists() else ""

    def load_soul(self, handle: str) -> str:
        p = self._agent_dir(handle) / "soul.md"
        return p.read_text() if p.exists() else ""

    def save_soul(self, handle: str, content: str) -> None:
        (self._agent_dir(handle) / "soul.md").write_text(content)

    def load_scratchpad(self, handle: str) -> str:
        p = self._agent_dir(handle) / "scratchpad.md"
        return p.read_text() if p.exists() else ""

    def save_scratchpad(self, handle: str, content: str) -> int:
        truncated = content[:SCRATCHPAD_MAX]
        (self._agent_dir(handle) / "scratchpad.md").write_text(truncated)
        return max(0, len(content) - SCRATCHPAD_MAX)

    def decay_scratchpad(self, handle: str, chars: int = 5) -> None:
        pad = self.load_scratchpad(handle)
        if len(pad) > chars:
            (self._agent_dir(handle) / "scratchpad.md").write_text(pad[:-chars])
