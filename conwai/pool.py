from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from conwai.agent import Agent

if TYPE_CHECKING:
    from conwai.messages import MessageBus
    from conwai.repository import AgentRepository
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


class AgentPool:
    def __init__(self, repo: AgentRepository, store: ComponentStore, bus: MessageBus | None = None):
        self._repo = repo
        self._bus = bus
        self._store = store
        self._agents: dict[str, Agent] = {}

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def alive(self) -> list[Agent]:
        return [a for a in self._agents.values() if a.alive]

    def by_handle(self, handle: str) -> Agent | None:
        return self._agents.get(handle)

    def handles(self) -> list[str]:
        return [h for h, a in self._agents.items() if a.alive]

    def load_or_create(
        self, agent: Agent,
        component_overrides: dict[str, dict] | None = None,
    ) -> Agent:
        if self._repo.exists(agent.handle):
            agent = self._repo.load_agent(agent.handle)
            # Components already loaded by store.load_all() -- no need to load here
        else:
            self._store.init_agent(agent.handle, overrides=component_overrides)
            self._repo.save_agent(agent)
        self._agents[agent.handle] = agent
        if agent.alive and self._bus:
            self._bus.register(agent.handle)
        return agent

    def add(
        self, agent: Agent,
        component_overrides: dict[str, dict] | None = None,
    ) -> Agent:
        self._store.init_agent(agent.handle, overrides=component_overrides)
        self._agents[agent.handle] = agent
        if self._bus:
            self._bus.register(agent.handle)
        self._repo.save_agent(agent)
        return agent

    def kill(self, handle: str) -> None:
        agent = self._agents.get(handle)
        if agent:
            agent.alive = False
            if self._bus:
                self._bus.unregister(handle)
            self._repo.save_agent(agent)  # persist the death

    def save(self, handle: str) -> None:
        agent = self._agents.get(handle)
        if agent:
            self._repo.save_agent(agent)
            # Components already persisted on set() -- no need to save here

    def save_all(self) -> None:
        for handle in self._agents:
            self.save(handle)
