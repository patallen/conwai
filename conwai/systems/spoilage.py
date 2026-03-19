from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import conwai.config as config

if TYPE_CHECKING:
    from conwai.app import Context

log = logging.getLogger("conwai")


class SpoilageSystem:
    name = "spoilage"

    def tick(self, ctx: Context) -> None:
        if config.BREAD_SPOIL_INTERVAL <= 0:
            return
        if ctx.tick % config.BREAD_SPOIL_INTERVAL != 0:
            return
        for agent in ctx.pool.alive():
            if agent.bread > 0:
                spoiled = min(agent.bread, config.BREAD_SPOIL_AMOUNT)
                agent.bread -= spoiled
                agent._energy_log.append(f"{spoiled} bread spoiled (bread left: {agent.bread})")
