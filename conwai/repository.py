from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.store import ComponentStore


class AgentRepository:
    def __init__(self, base_dir: Path = Path("data/agents")):
        self._base_dir = base_dir

    def _agent_dir(self, handle: str) -> Path:
        return self._base_dir / handle

    def exists(self, handle: str) -> bool:
        return self._agent_dir(handle).exists()

    def save_agent(self, agent: Agent) -> None:
        d = self._agent_dir(agent.handle)
        d.mkdir(parents=True, exist_ok=True)
        (d / "identity.json").write_text(json.dumps({
            "handle": agent.handle,
            "role": agent.role,
            "alive": agent.alive,
            "born_tick": agent.born_tick,
            "personality": agent.personality,
        }))

    def load_agent(self, handle: str) -> Agent | None:
        from conwai.agent import Agent
        d = self._agent_dir(handle)
        if not d.exists():
            return None
        id_path = d / "identity.json"
        if not id_path.exists():
            return None
        data = json.loads(id_path.read_text())
        data.pop("soul", None)
        return Agent(**data)

    def save_components(self, handle: str, store: ComponentStore) -> None:
        store.save(handle, self._agent_dir(handle))

    def load_components(self, handle: str, store: ComponentStore) -> None:
        store.load(handle, self._agent_dir(handle))

    def save_brain_state(self, handle: str, state: dict) -> None:
        d = self._agent_dir(handle)
        d.mkdir(parents=True, exist_ok=True)
        (d / "context.json").write_text(json.dumps(state, indent=2))

    def load_brain_state(self, handle: str) -> dict | None:
        ctx_path = self._agent_dir(handle) / "context.json"
        if not ctx_path.exists():
            return None
        return json.loads(ctx_path.read_text())
