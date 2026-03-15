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

    def ensure_dir(self, handle: str) -> None:
        self._agent_dir(handle).mkdir(parents=True, exist_ok=True)

    def save(self, agent: Agent) -> None:
        d = self._agent_dir(agent.handle)
        d.mkdir(parents=True, exist_ok=True)
        (d / "energy").write_text(str(agent.energy))
        (d / "alive").write_text("true" if agent.alive else "false")
        (d / "soul.md").write_text(agent.soul)
        (d / "scratchpad.md").write_text(agent.scratchpad[:SCRATCHPAD_MAX])
        (d / "personality.md").write_text(agent.personality)
        (d / "context.json").write_text(
            json.dumps(
                {"system": agent.system_prompt, "messages": agent.messages},
                indent=2,
            )
        )

    def load(self, handle: str) -> dict:
        d = self._agent_dir(handle)
        if not d.exists():
            return {}
        result = {}
        for name, key in [
            ("personality.md", "personality"),
            ("soul.md", "soul"),
            ("scratchpad.md", "scratchpad"),
        ]:
            p = d / name
            result[key] = p.read_text() if p.exists() else ""
        ep = d / "energy"
        result["energy"] = float(ep.read_text().strip()) if ep.exists() else None
        ap = d / "alive"
        result["alive"] = ap.read_text().strip() == "true" if ap.exists() else True
        return result
