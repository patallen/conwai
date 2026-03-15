from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from conwai.config import ENERGY_MAX, MEMORY_MAX

if TYPE_CHECKING:
    from conwai.agent import Agent


class AgentRepository:
    def __init__(self, base_dir: Path = Path("data/agents")):
        self._base_dir = base_dir

    def _agent_dir(self, handle: str) -> Path:
        return self._base_dir / handle

    def create(self, agent: Agent) -> Agent:
        if self.exists(agent.handle):
            raise ValueError(f"Agent {agent.handle} already exists")
        self.save(agent)
        return agent

    def exists(self, handle: str) -> bool:
        return self._agent_dir(handle).exists()

    def load(self, handle: str) -> Agent | None:
        from conwai.agent import Agent

        if not self.exists(handle):
            return None
        d = self._agent_dir(handle)
        ctx_path = d / "context.json"
        if ctx_path.exists():
            context = json.loads(ctx_path.read_text())
        else:
            context = {"system": "", "messages": []}
        energy_path = d / "energy"
        alive_path = d / "alive"
        return Agent(
            handle=handle,
            energy=float(energy_path.read_text().strip())
            if energy_path.exists()
            else ENERGY_MAX,
            alive=alive_path.read_text().strip() == "true"
            if alive_path.exists()
            else True,
            system_prompt=context["system"],
            messages=context["messages"],
            soul=(d / "soul.md").read_text() if (d / "soul.md").exists() else "",
            memory=(d / "memory.md").read_text() if (d / "memory.md").exists() else "",
            personality=(d / "personality.md").read_text()
            if (d / "personality.md").exists()
            else "",
        )

    def save(self, agent: Agent) -> None:
        d = self._agent_dir(agent.handle)
        d.mkdir(parents=True, exist_ok=True)
        (d / "energy").write_text(str(agent.energy))
        (d / "alive").write_text("true" if agent.alive else "false")
        (d / "soul.md").write_text(agent.soul)
        (d / "memory.md").write_text(agent.memory[:MEMORY_MAX])
        (d / "personality.md").write_text(agent.personality)
        (d / "context.json").write_text(
            json.dumps(
                {"system": agent.system_prompt, "messages": agent.messages},
                indent=2,
            )
        )
