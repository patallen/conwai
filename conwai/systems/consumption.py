from __future__ import annotations

from typing import TYPE_CHECKING

import conwai.config as config

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.perception import Perception
    from conwai.store import ComponentStore


class ConsumptionSystem:
    name = "consumption"

    def tick(self, agents: list[Agent], store: ComponentStore, perception: Perception, **kwargs) -> None:
        for agent in agents:
            h = store.get(agent.handle, "hunger")
            inv = store.get(agent.handle, "inventory")
            eco = store.get(agent.handle, "economy")

            # Auto-eat (consume until above threshold or out of food)
            if h["hunger"] <= config.HUNGER_AUTO_EAT_THRESHOLD:
                bread_eaten = 0
                while h["hunger"] <= config.HUNGER_AUTO_EAT_THRESHOLD and inv["bread"] > 0:
                    inv["bread"] -= 1
                    h["hunger"] = min(config.HUNGER_MAX, h["hunger"] + config.HUNGER_EAT_RESTORE)
                    bread_eaten += 1
                if bread_eaten:
                    perception.notify(agent.handle, f"ate {bread_eaten} bread (hunger now {h['hunger']}, bread left: {inv['bread']})")

                flour_eaten = 0
                while h["hunger"] <= config.HUNGER_AUTO_EAT_THRESHOLD and inv["flour"] > 0:
                    inv["flour"] -= 1
                    h["hunger"] = min(config.HUNGER_MAX, h["hunger"] + config.HUNGER_EAT_RAW_RESTORE)
                    flour_eaten += 1
                if flour_eaten:
                    perception.notify(agent.handle, f"ate {flour_eaten} flour raw (hunger now {h['hunger']}, flour left: {inv['flour']})")

            if h["hunger"] == 0:
                eco["coins"] = max(0, eco["coins"] - config.HUNGER_STARVE_COIN_PENALTY)
                perception.notify(agent.handle, f"coins -{config.HUNGER_STARVE_COIN_PENALTY} (starving)")

            # Auto-drink
            if h["thirst"] <= config.THIRST_AUTO_DRINK_THRESHOLD:
                water_drunk = 0
                while h["thirst"] <= config.THIRST_AUTO_DRINK_THRESHOLD and inv["water"] > 0:
                    inv["water"] -= 1
                    h["thirst"] = min(config.HUNGER_MAX, h["thirst"] + config.THIRST_DRINK_RESTORE)
                    water_drunk += 1
                if water_drunk:
                    perception.notify(agent.handle, f"drank {water_drunk} water (thirst now {h['thirst']}, water left: {inv['water']})")

            if h["thirst"] == 0:
                eco["coins"] = max(0, eco["coins"] - config.THIRST_DEHYDRATION_COIN_PENALTY)
                perception.notify(agent.handle, f"coins -{config.THIRST_DEHYDRATION_COIN_PENALTY} (dehydrated)")

            store.set(agent.handle, "hunger", h)
            store.set(agent.handle, "inventory", inv)
            store.set(agent.handle, "economy", eco)
