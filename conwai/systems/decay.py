from __future__ import annotations

from typing import TYPE_CHECKING

import conwai.config as config

if TYPE_CHECKING:
    from conwai.app import Context


class DecaySystem:
    name = "decay"

    def tick(self, ctx: Context) -> None:
        for agent in ctx.pool.alive():
            agent.hunger = max(0, agent.hunger - config.HUNGER_DECAY_PER_TICK)
            agent.thirst = max(0, agent.thirst - config.THIRST_DECAY_PER_TICK)
            agent.water += config.PASSIVE_WATER_PER_TICK
