from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.perception import Perception
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


class TaxSystem:
    name = "tax"

    def __init__(self, interval: int = 24, rate: float = 0.01):
        self.interval = interval
        self.rate = rate

    def tick(self, agents: list[Agent], store: ComponentStore, perception: Perception, tick: int = 0, **kwargs) -> None:
        if tick % self.interval != 0:
            return
        for agent in agents:
            eco = store.get(agent.handle, "economy")
            if eco["coins"] > 0:
                tax = max(1, int(eco["coins"] * self.rate))
                eco["coins"] -= tax
                store.set(agent.handle, "economy", eco)
                perception.notify(agent.handle, f"coins -{tax} (daily tax)")
        log.info(f"[WORLD] daily tax collected (tick {tick})")
