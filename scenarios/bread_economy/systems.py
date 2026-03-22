from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from scenarios.bread_economy.components import AgentInfo, Economy, Hunger, Inventory
from scenarios.bread_economy.config import get_config

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext

log = logging.getLogger("conwai")


class DecaySystem:
    name = "decay"

    async def run(self, ctx: TickContext) -> None:
        cfg = get_config()
        for agent in ctx.pool.alive():
            h = ctx.store.get(agent.handle, Hunger)
            h.hunger = max(0, h.hunger - cfg.hunger_decay_per_tick)
            h.thirst = max(0, h.thirst - cfg.thirst_decay_per_tick)
            ctx.store.set(agent.handle, h)
            inv = ctx.store.get(agent.handle, Inventory)
            inv.water += cfg.passive_water_per_tick
            ctx.store.set(agent.handle, inv)


class TaxSystem:
    name = "tax"

    def __init__(self, interval: int = 24, rate: float = 0.01):
        self.interval = interval
        self.rate = rate

    async def run(self, ctx: TickContext) -> None:
        if ctx.tick % self.interval != 0:
            return
        for agent in ctx.pool.alive():
            eco = ctx.store.get(agent.handle, Economy)
            if eco.coins > 0:
                tax = max(1, int(eco.coins * self.rate))
                eco.coins -= tax
                ctx.store.set(agent.handle, eco)
                ctx.perception.notify(agent.handle, f"coins -{tax} (daily tax)")
        log.info(f"[WORLD] daily tax collected (tick {ctx.tick})")


class SpoilageSystem:
    name = "spoilage"

    async def run(self, ctx: TickContext) -> None:
        cfg = get_config()
        if cfg.bread_spoil_interval <= 0:
            return
        if ctx.tick % cfg.bread_spoil_interval != 0:
            return
        for agent in ctx.pool.alive():
            inv = ctx.store.get(agent.handle, Inventory)
            if inv.bread > 0:
                spoiled = min(inv.bread, cfg.bread_spoil_amount)
                inv.bread -= spoiled
                ctx.store.set(agent.handle, inv)
                ctx.perception.notify(agent.handle, f"{spoiled} bread spoiled (bread left: {inv.bread})")


class AutoForageSystem:
    """Automatically forages for each agent every tick. Agents don't choose to forage."""
    name = "auto_forage"

    async def run(self, ctx: TickContext) -> None:
        import random
        cfg = get_config()
        for agent in ctx.pool.alive():
            info = ctx.store.get(agent.handle, AgentInfo)
            skills = cfg.forage_skill_by_role.get(info.role, {"flour": 1, "water": 1})
            inv = ctx.store.get(agent.handle, Inventory)
            cap = cfg.inventory_cap
            flour = random.randint(0, skills["flour"])
            water = random.randint(0, skills["water"])
            flour = min(flour, max(0, cap - inv.flour))
            water = min(water, max(0, cap - inv.water))
            inv.flour += flour
            inv.water += water
            ctx.store.set(agent.handle, inv)


class AutoBakeSystem:
    """Automatically bakes bread when agent has enough ingredients and bread is low."""
    name = "auto_bake"

    async def run(self, ctx: TickContext) -> None:
        cfg = get_config()
        flour_cost = cfg.bake_cost["flour"]
        water_cost = cfg.bake_cost["water"]
        bread_yield = cfg.bake_yield
        cap = cfg.inventory_cap

        for agent in ctx.pool.alive():
            inv = ctx.store.get(agent.handle, Inventory)
            # Bake when bread is low and we have ingredients
            while inv.bread < 20 and inv.flour >= flour_cost and inv.water >= water_cost:
                inv.flour -= flour_cost
                inv.water -= water_cost
                actual = min(bread_yield, max(0, cap - inv.bread))
                inv.bread += actual
                if actual == 0:
                    break
            ctx.store.set(agent.handle, inv)


class ConsumptionSystem:
    name = "consumption"

    async def run(self, ctx: TickContext) -> None:
        cfg = get_config()
        for agent in ctx.pool.alive():
            h = ctx.store.get(agent.handle, Hunger)
            inv = ctx.store.get(agent.handle, Inventory)
            eco = ctx.store.get(agent.handle, Economy)

            # Auto-eat bread
            if h.hunger <= cfg.hunger_auto_eat_threshold:
                bread_eaten = 0
                while h.hunger <= cfg.hunger_auto_eat_threshold and inv.bread > 0:
                    inv.bread -= 1
                    h.hunger = min(cfg.hunger_max, h.hunger + cfg.hunger_eat_restore)
                    bread_eaten += 1
                if bread_eaten:
                    ctx.perception.notify(agent.handle, f"ate {bread_eaten} bread (hunger now {h.hunger}, bread left: {inv.bread})")

                # Fall back to raw flour only if no bread
                flour_eaten = 0
                while h.hunger <= cfg.hunger_auto_eat_threshold and inv.flour > 0:
                    inv.flour -= 1
                    h.hunger = min(cfg.hunger_max, h.hunger + cfg.hunger_eat_raw_restore)
                    flour_eaten += 1
                if flour_eaten:
                    ctx.perception.notify(agent.handle, f"ate {flour_eaten} flour raw (hunger now {h.hunger}, flour left: {inv.flour})")

            if h.hunger == 0:
                eco.coins = max(0, eco.coins - cfg.hunger_starve_coin_penalty)
                ctx.perception.notify(agent.handle, f"coins -{cfg.hunger_starve_coin_penalty} (starving)")

            # Auto-drink
            if h.thirst <= cfg.thirst_auto_drink_threshold:
                water_drunk = 0
                while h.thirst <= cfg.thirst_auto_drink_threshold and inv.water > 0:
                    inv.water -= 1
                    h.thirst = min(cfg.hunger_max, h.thirst + cfg.thirst_drink_restore)
                    water_drunk += 1
                if water_drunk:
                    ctx.perception.notify(agent.handle, f"drank {water_drunk} water (thirst now {h.thirst}, water left: {inv.water})")

            if h.thirst == 0:
                eco.coins = max(0, eco.coins - cfg.thirst_dehydration_coin_penalty)
                ctx.perception.notify(agent.handle, f"coins -{cfg.thirst_dehydration_coin_penalty} (dehydrated)")

            ctx.store.set(agent.handle, h)
            ctx.store.set(agent.handle, inv)
            ctx.store.set(agent.handle, eco)


class DeathSystem:
    name = "death"

    def __init__(self, on_death: Callable[[Agent, TickContext], None] | None = None):
        self._on_death = on_death

    async def run(self, ctx: TickContext) -> None:
        for agent in list(ctx.pool.alive()):
            if not agent.alive:
                continue
            h = ctx.store.get(agent.handle, Hunger)
            inv = ctx.store.get(agent.handle, Inventory)
            if h.hunger == 0 and inv.bread == 0 and inv.flour == 0:
                ctx.pool.kill(agent.handle)
                log.info(f"[{agent.handle}] DEAD — starved")
                if self._on_death:
                    self._on_death(agent, ctx)
