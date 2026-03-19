from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.app import Context

log = logging.getLogger("conwai")


class TaxSystem:
    name = "tax"

    def __init__(self, interval: int = 24, rate: float = 0.01):
        self.interval = interval
        self.rate = rate

    def tick(self, ctx: Context) -> None:
        if ctx.tick % self.interval != 0:
            return
        for agent in ctx.pool.alive():
            if agent.coins > 0:
                tax = max(1, int(agent.coins * self.rate))
                agent.coins -= tax
                agent._energy_log.append(f"coins -{tax} (daily tax)")
        ctx.log("WORLD", "tax", {"tick": ctx.tick})
        log.info(f"[WORLD] daily tax collected (tick {ctx.tick})")
