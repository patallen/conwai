from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

import scenarios.bread_economy.config as config

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext

log = logging.getLogger("conwai")


class DecaySystem:
    name = "decay"

    async def run(self, ctx: TickContext) -> None:
        for agent in ctx.pool.alive():
            h = ctx.store.get(agent.handle, "hunger")
            h["hunger"] = max(0, h["hunger"] - config.HUNGER_DECAY_PER_TICK)
            h["thirst"] = max(0, h["thirst"] - config.THIRST_DECAY_PER_TICK)
            ctx.store.set(agent.handle, "hunger", h)
            inv = ctx.store.get(agent.handle, "inventory")
            inv["water"] += config.PASSIVE_WATER_PER_TICK
            ctx.store.set(agent.handle, "inventory", inv)


class TaxSystem:
    name = "tax"

    def __init__(self, interval: int = 24, rate: float = 0.01):
        self.interval = interval
        self.rate = rate

    async def run(self, ctx: TickContext) -> None:
        if ctx.tick % self.interval != 0:
            return
        for agent in ctx.pool.alive():
            eco = ctx.store.get(agent.handle, "economy")
            if eco["coins"] > 0:
                tax = max(1, int(eco["coins"] * self.rate))
                eco["coins"] -= tax
                ctx.store.set(agent.handle, "economy", eco)
                ctx.perception.notify(agent.handle, f"coins -{tax} (daily tax)")
        log.info(f"[WORLD] daily tax collected (tick {ctx.tick})")


class SpoilageSystem:
    name = "spoilage"

    async def run(self, ctx: TickContext) -> None:
        if config.BREAD_SPOIL_INTERVAL <= 0:
            return
        if ctx.tick % config.BREAD_SPOIL_INTERVAL != 0:
            return
        for agent in ctx.pool.alive():
            inv = ctx.store.get(agent.handle, "inventory")
            if inv["bread"] > 0:
                spoiled = min(inv["bread"], config.BREAD_SPOIL_AMOUNT)
                inv["bread"] -= spoiled
                ctx.store.set(agent.handle, "inventory", inv)
                ctx.perception.notify(agent.handle, f"{spoiled} bread spoiled (bread left: {inv['bread']})")


class AutoForageSystem:
    """Automatically forages for each agent every tick. Agents don't choose to forage."""
    name = "auto_forage"

    async def run(self, ctx: TickContext) -> None:
        import random
        for agent in ctx.pool.alive():
            info = ctx.store.get(agent.handle, "agent_info")
            skills = config.FORAGE_SKILL_BY_ROLE.get(info["role"], {"flour": 1, "water": 1})
            inv = ctx.store.get(agent.handle, "inventory")
            cap = config.INVENTORY_CAP
            flour = random.randint(0, skills["flour"])
            water = random.randint(0, skills["water"])
            flour = min(flour, max(0, cap - inv["flour"]))
            water = min(water, max(0, cap - inv["water"]))
            inv["flour"] += flour
            inv["water"] += water
            ctx.store.set(agent.handle, "inventory", inv)


class AutoBakeSystem:
    """Automatically bakes bread when agent has enough ingredients and bread is low."""
    name = "auto_bake"

    async def run(self, ctx: TickContext) -> None:
        flour_cost = config.BAKE_COST["flour"]
        water_cost = config.BAKE_COST["water"]
        bread_yield = config.BAKE_YIELD
        cap = config.INVENTORY_CAP

        for agent in ctx.pool.alive():
            inv = ctx.store.get(agent.handle, "inventory")
            # Bake when bread is low and we have ingredients
            while inv["bread"] < 20 and inv["flour"] >= flour_cost and inv["water"] >= water_cost:
                inv["flour"] -= flour_cost
                inv["water"] -= water_cost
                actual = min(bread_yield, max(0, cap - inv["bread"]))
                inv["bread"] += actual
                if actual == 0:
                    break
            ctx.store.set(agent.handle, "inventory", inv)


class ConsumptionSystem:
    name = "consumption"

    async def run(self, ctx: TickContext) -> None:
        for agent in ctx.pool.alive():
            h = ctx.store.get(agent.handle, "hunger")
            inv = ctx.store.get(agent.handle, "inventory")
            eco = ctx.store.get(agent.handle, "economy")

            # Auto-eat bread
            if h["hunger"] <= config.HUNGER_AUTO_EAT_THRESHOLD:
                bread_eaten = 0
                while h["hunger"] <= config.HUNGER_AUTO_EAT_THRESHOLD and inv["bread"] > 0:
                    inv["bread"] -= 1
                    h["hunger"] = min(config.HUNGER_MAX, h["hunger"] + config.HUNGER_EAT_RESTORE)
                    bread_eaten += 1
                if bread_eaten:
                    ctx.perception.notify(agent.handle, f"ate {bread_eaten} bread (hunger now {h['hunger']}, bread left: {inv['bread']})")

                # Fall back to raw flour only if no bread
                flour_eaten = 0
                while h["hunger"] <= config.HUNGER_AUTO_EAT_THRESHOLD and inv["flour"] > 0:
                    inv["flour"] -= 1
                    h["hunger"] = min(config.HUNGER_MAX, h["hunger"] + config.HUNGER_EAT_RAW_RESTORE)
                    flour_eaten += 1
                if flour_eaten:
                    ctx.perception.notify(agent.handle, f"ate {flour_eaten} flour raw (hunger now {h['hunger']}, flour left: {inv['flour']})")

            if h["hunger"] == 0:
                eco["coins"] = max(0, eco["coins"] - config.HUNGER_STARVE_COIN_PENALTY)
                ctx.perception.notify(agent.handle, f"coins -{config.HUNGER_STARVE_COIN_PENALTY} (starving)")

            # Auto-drink
            if h["thirst"] <= config.THIRST_AUTO_DRINK_THRESHOLD:
                water_drunk = 0
                while h["thirst"] <= config.THIRST_AUTO_DRINK_THRESHOLD and inv["water"] > 0:
                    inv["water"] -= 1
                    h["thirst"] = min(config.HUNGER_MAX, h["thirst"] + config.THIRST_DRINK_RESTORE)
                    water_drunk += 1
                if water_drunk:
                    ctx.perception.notify(agent.handle, f"drank {water_drunk} water (thirst now {h['thirst']}, water left: {inv['water']})")

            if h["thirst"] == 0:
                eco["coins"] = max(0, eco["coins"] - config.THIRST_DEHYDRATION_COIN_PENALTY)
                ctx.perception.notify(agent.handle, f"coins -{config.THIRST_DEHYDRATION_COIN_PENALTY} (dehydrated)")

            ctx.store.set(agent.handle, "hunger", h)
            ctx.store.set(agent.handle, "inventory", inv)
            ctx.store.set(agent.handle, "economy", eco)


class DeathSystem:
    name = "death"

    def __init__(self, on_death: Callable[[Agent, TickContext], None] | None = None):
        self._on_death = on_death

    async def run(self, ctx: TickContext) -> None:
        for agent in list(ctx.pool.alive()):
            if not agent.alive:
                continue
            h = ctx.store.get(agent.handle, "hunger")
            inv = ctx.store.get(agent.handle, "inventory")
            if h["hunger"] == 0 and inv["bread"] == 0 and inv["flour"] == 0:
                ctx.pool.kill(agent.handle)
                log.info(f"[{agent.handle}] DEAD — starved")
                if self._on_death:
                    self._on_death(agent, ctx)
