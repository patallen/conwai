from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import conwai.config as config

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.perception import Perception
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


class SpoilageSystem:
    name = "spoilage"

    def tick(self, agents: list[Agent], store: ComponentStore, perception: Perception, tick: int = 0, **kwargs) -> None:
        if config.BREAD_SPOIL_INTERVAL <= 0:
            return
        if tick % config.BREAD_SPOIL_INTERVAL != 0:
            return
        for agent in agents:
            inv = store.get(agent.handle, "inventory")
            if inv["bread"] > 0:
                spoiled = min(inv["bread"], config.BREAD_SPOIL_AMOUNT)
                inv["bread"] -= spoiled
                store.set(agent.handle, "inventory", inv)
                perception.notify(agent.handle, f"{spoiled} bread spoiled (bread left: {inv['bread']})")
