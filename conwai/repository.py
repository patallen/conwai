from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from conwai.config import ENERGY_MAX, HUNGER_MAX, MEMORY_MAX

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

    def _read(self, d: Path, name: str, default: str = "") -> str:
        p = d / name
        return p.read_text().strip() if p.exists() else default

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
        return Agent(
            handle=handle,
            coins=float(self._read(d, "energy", str(ENERGY_MAX))),
            role=self._read(d, "role"),
            flour=int(self._read(d, "flour", "0")),
            water=int(self._read(d, "water", "0")),
            bread=int(self._read(d, "bread", "0")),
            hunger=int(self._read(d, "hunger", str(HUNGER_MAX))),
            alive=self._read(d, "alive", "true") == "true",
            system_prompt=context["system"],
            messages=context["messages"],
            soul=self._read(d, "soul.md"),
            memory=self._read(d, "memory.md"),
            personality=self._read(d, "personality.md"),
        )

    def save(self, agent: Agent) -> None:
        d = self._agent_dir(agent.handle)
        d.mkdir(parents=True, exist_ok=True)
        (d / "energy").write_text(str(agent.coins))
        (d / "role").write_text(agent.role)
        (d / "flour").write_text(str(agent.flour))
        (d / "water").write_text(str(agent.water))
        (d / "bread").write_text(str(agent.bread))
        (d / "hunger").write_text(str(agent.hunger))
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
