from __future__ import annotations

from typing import TYPE_CHECKING

import conwai.config as config
from conwai.config import HUNGER_MAX

if TYPE_CHECKING:
    from conwai.app import Context


class ConsumptionSystem:
    name = "consumption"

    def tick(self, ctx: Context) -> None:
        for agent in ctx.pool.alive():
            # Auto-eat
            if agent.hunger <= config.HUNGER_AUTO_EAT_THRESHOLD:
                if agent.bread > 0:
                    agent.bread -= 1
                    agent.hunger = min(HUNGER_MAX, agent.hunger + config.HUNGER_EAT_RESTORE)
                    agent._energy_log.append(f"ate 1 bread (hunger now {agent.hunger}, bread left: {agent.bread})")
                elif agent.flour > 0:
                    agent.flour -= 1
                    agent.hunger = min(HUNGER_MAX, agent.hunger + config.HUNGER_EAT_RAW_RESTORE)
                    agent._energy_log.append(f"ate 1 flour raw (hunger now {agent.hunger}, flour left: {agent.flour})")
            if agent.hunger == 0:
                agent.coins = max(0, agent.coins - config.HUNGER_STARVE_COIN_PENALTY)
                agent._energy_log.append(f"coins -{config.HUNGER_STARVE_COIN_PENALTY} (starving)")

            # Auto-drink
            if agent.thirst <= config.THIRST_AUTO_DRINK_THRESHOLD and agent.water > 0:
                agent.water -= 1
                agent.thirst = min(HUNGER_MAX, agent.thirst + config.THIRST_DRINK_RESTORE)
                agent._energy_log.append(f"drank 1 water (thirst now {agent.thirst}, water left: {agent.water})")
            if agent.thirst == 0:
                agent.coins = max(0, agent.coins - config.THIRST_DEHYDRATION_COIN_PENALTY)
                agent._energy_log.append(f"coins -{config.THIRST_DEHYDRATION_COIN_PENALTY} (dehydrated)")
