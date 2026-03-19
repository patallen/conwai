from __future__ import annotations

from typing import TYPE_CHECKING

import conwai.config as config

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.perception import Perception
    from conwai.store import ComponentStore


class DecaySystem:
    name = "decay"

    def tick(self, agents: list[Agent], store: ComponentStore, perception: Perception, **kwargs) -> None:
        for agent in agents:
            h = store.get(agent.handle, "hunger")
            h["hunger"] = max(0, h["hunger"] - config.HUNGER_DECAY_PER_TICK)
            h["thirst"] = max(0, h["thirst"] - config.THIRST_DECAY_PER_TICK)
            store.set(agent.handle, "hunger", h)
            inv = store.get(agent.handle, "inventory")
            inv["water"] += config.PASSIVE_WATER_PER_TICK
            store.set(agent.handle, "inventory", inv)
