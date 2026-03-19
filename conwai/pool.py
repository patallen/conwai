from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from conwai.agent import Agent
from conwai.config import STARTING_BREAD
from conwai.repository import AgentRepository

if TYPE_CHECKING:
    from conwai.bulletin_board import BulletinBoard
    from conwai.events import EventLog
    from conwai.messages import MessageBus

log = logging.getLogger("conwai")


class AgentPool:
    def __init__(self, repo: AgentRepository, bus: MessageBus):
        self._repo = repo
        self._bus = bus
        self._agents: dict[str, Agent] = {}

    # --- Queries ---

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def alive(self) -> list[Agent]:
        return [a for a in self._agents.values() if a.alive]

    def by_handle(self, handle: str) -> Agent | None:
        return self._agents.get(handle)

    def handles(self) -> list[str]:
        return [h for h, a in self._agents.items() if a.alive]

    # --- Lifecycle ---

    def load_or_create(self, handle: str, role: str, born_tick: int) -> Agent:
        if self._repo.exists(handle):
            agent = self._repo.load(handle)
        else:
            agent = Agent(handle=handle, role=role, born_tick=born_tick, bread=STARTING_BREAD)
            self._repo.create(agent)
        self._agents[handle] = agent
        if agent.alive:
            self._bus.register(handle)
        return agent

    def spawn(self, role: str, born_tick: int, prefix: str = "A") -> Agent:
        handle = self._generate_handle(prefix)
        agent = Agent(handle=handle, role=role, born_tick=born_tick, bread=STARTING_BREAD)
        self._repo.create(agent)
        self._agents[handle] = agent
        self._bus.register(handle)
        return agent

    def kill(self, handle: str) -> None:
        agent = self._agents.get(handle)
        if agent:
            agent.alive = False
            self._bus.unregister(handle)

    def replace_dead(self, board: BulletinBoard, events: EventLog, born_tick: int) -> list[Agent]:
        new_agents = []
        dead = [a for a in self._agents.values() if not a.alive]
        for agent in dead:
            self._bus.unregister(agent.handle)
            del self._agents[agent.handle]
            board.post("WORLD", f"{agent.handle} has died. A new member is joining.")
            log.info(f"[WORLD] {agent.handle} DIED")

            replacement = self.spawn(agent.role, born_tick, prefix=agent.handle[0])
            board.post("WORLD", f"New member {replacement.handle} has joined.")
            events.log("WORLD", "agent_spawned", {"handle": replacement.handle, "replaced": agent.handle})
            log.info(f"[WORLD] {replacement.handle} spawned (replacing {agent.handle})")
            new_agents.append(replacement)
        return new_agents

    # --- Persistence ---

    def save(self, handle: str) -> None:
        agent = self._agents.get(handle)
        if agent:
            self._repo.save(agent)

    def save_all(self) -> None:
        for agent in self._agents.values():
            self._repo.save(agent)

    # --- Internal ---

    def _generate_handle(self, prefix: str = "A") -> str:
        while True:
            handle = f"{prefix}{uuid4().hex[:3]}"
            if not self._repo.exists(handle):
                return handle
