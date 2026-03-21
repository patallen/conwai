from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.storage import Storage
    from conwai.store import ComponentStore


class AgentRepository:
    def __init__(self, storage: Storage):
        self._storage = storage

    def exists(self, handle: str) -> bool:
        return self._storage.load_component(handle, "_identity") is not None

    def list_handles(self) -> list[str]:
        return [e for e in self._storage.list_entities()
                if self._storage.load_component(e, "_identity") is not None]

    def save_agent(self, agent: Agent) -> None:
        self._storage.save_component(agent.handle, "_identity", {
            "handle": agent.handle,
            "alive": agent.alive,
            "born_tick": agent.born_tick,
        })

    def load_agent(self, handle: str) -> Agent | None:
        from conwai.agent import Agent
        data = self._storage.load_component(handle, "_identity")
        if data is None:
            return None
        for key in list(data.keys()):
            if key not in ("handle", "alive", "born_tick"):
                data.pop(key)
        return Agent(**data)

    def save_components(self, handle: str, store: ComponentStore) -> None:
        # No-op: ComponentStore now writes through to storage on set()
        pass

    def load_components(self, handle: str, store: ComponentStore) -> None:
        # No-op: ComponentStore loads everything on startup via load_all()
        pass
