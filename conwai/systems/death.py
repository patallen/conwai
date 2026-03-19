from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.app import Context

log = logging.getLogger("conwai")


class DeathSystem:
    name = "death"

    def __init__(self, on_spawn=None):
        self._on_spawn = on_spawn

    def tick(self, ctx: Context) -> None:
        # Check for starvation
        for agent in ctx.pool.alive():
            if agent.hunger == 0 and agent.bread == 0 and agent.flour == 0:
                agent.alive = False
                log.info(f"[{agent.handle}] DEAD — starved")
                ctx.log(agent.handle, "agent_died", {"reason": "starved"})

        # Replace dead agents
        new_agents = ctx.pool.replace_dead(ctx.board, ctx.events, ctx.tick)
        if self._on_spawn:
            for agent in new_agents:
                self._on_spawn(agent)
