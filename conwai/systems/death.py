from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Callable
from uuid import uuid4

import conwai.config as config
from conwai.agent import Agent
from conwai.config import assign_traits

if TYPE_CHECKING:
    from conwai.bulletin_board import BulletinBoard
    from conwai.events import EventLog
    from conwai.perception import Perception
    from conwai.pool import AgentPool
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


class DeathSystem:
    name = "death"

    def __init__(
        self,
        pool: AgentPool,
        board: BulletinBoard,
        events: EventLog,
        on_spawn: Callable[[Agent], None] | None = None,
    ):
        self._pool = pool
        self._board = board
        self._events = events
        self._on_spawn = on_spawn

    def tick(self, agents: list[Agent], store: ComponentStore, perception: Perception, **kwargs) -> None:
        tick = kwargs.get("tick", 0)
        for agent in agents:
            if not agent.alive:
                continue
            h = store.get(agent.handle, "hunger")
            inv = store.get(agent.handle, "inventory")
            if h["hunger"] == 0 and inv["bread"] == 0 and inv["flour"] == 0:
                self._pool.kill(agent.handle)
                self._board.post("WORLD", f"{agent.handle} has died of starvation.")
                self._events.log("WORLD", "agent_died", {"handle": agent.handle, "cause": "starvation"})
                log.info(f"[{agent.handle}] DEAD — starved")

                # Spawn replacement
                role = random.choice(config.ROLES)
                handle = f"{agent.handle[0]}{uuid4().hex[:3]}"
                new_agent = Agent(handle=handle, role=role, born_tick=tick, personality=", ".join(assign_traits()))
                self._pool.add(new_agent)
                self._board.post("WORLD", f"A new agent {new_agent.handle} ({role}) has arrived.")
                self._events.log("WORLD", "agent_spawned", {"handle": new_agent.handle, "role": role, "replaced": agent.handle})
                log.info(f"[{new_agent.handle}] spawned as {role} (replacing {agent.handle})")

                if self._on_spawn:
                    self._on_spawn(new_agent)
