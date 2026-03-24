from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable

from conwai.engine import TickNumber
from conwai.events import EventLog
from scenarios.bread_economy.components import AgentInfo, Economy, Hunger, Inventory
from scenarios.bread_economy.config import get_config
from scenarios.bread_economy.perception import BreadPerceptionBuilder

if TYPE_CHECKING:
    from conwai.world import World

log = logging.getLogger("conwai")


class Treasury:
    """Central bank that collects fees and penalties for redistribution."""

    def __init__(self) -> None:
        self.balance: float = 0


def deposit_to_treasury(world: World, amount: float) -> None:
    """Deposit coins into the treasury for redistribution."""
    if amount <= 0:
        return
    if not world.has_resource(Treasury):
        return
    world.get_resource(Treasury).balance += amount


class DecaySystem:
    name = "decay"

    async def run(self, world: World) -> None:
        cfg = get_config()
        for entity, _h, _inv in world.query(Hunger, Inventory):
            with world.mutate(entity, Hunger) as h, world.mutate(entity, Inventory) as inv:
                h.hunger = max(0, h.hunger - cfg.hunger_decay_per_tick)
                h.thirst = max(0, h.thirst - cfg.thirst_decay_per_tick)
                inv.water += cfg.passive_water_per_tick


class TaxSystem:
    name = "tax"

    def __init__(self, interval: int = 24, rate: float = 0.01):
        self.interval = interval
        self.rate = rate

    async def run(self, world: World) -> None:
        tick = world.get_resource(TickNumber).value
        if tick % self.interval != 0:
            return
        perception = world.get_resource(BreadPerceptionBuilder)

        # Collect wealth tax into treasury
        for entity, _eco in world.query(Economy):
            if _eco.coins > 0:
                tax = max(1, int(_eco.coins * self.rate))
                with world.mutate(entity, Economy) as eco:
                    eco.coins -= tax
                deposit_to_treasury(world, tax)
                perception.notify(entity, f"coins -{tax} (daily tax)")

        # Redistribute entire treasury balance equally
        treasury = world.get_resource(Treasury)
        pool = treasury.balance
        agents = [eid for eid, _ in world.query(Economy)]
        events = world.get_resource(EventLog)
        if agents and pool > 0:
            per_agent = int(pool) // len(agents)
            remainder = int(pool) - per_agent * len(agents)
            for entity in agents:
                dividend = per_agent + (1 if remainder > 0 else 0)
                remainder -= 1 if remainder > 0 else 0
                if dividend > 0:
                    with world.mutate(entity, Economy) as eco:
                        eco.coins += dividend
                    perception.notify(entity, f"coins +{dividend} (tax dividend)")
            treasury.balance = 0
            events.log("WORLD", "tax_redistribution", {
                "pool": int(pool),
                "per_agent": per_agent,
                "agents": len(agents),
                "tick": tick,
            })
            log.info(f"[WORLD] daily tax: redistributed {int(pool)} coins to {len(agents)} agents (tick {tick})")
        else:
            log.info(f"[WORLD] daily tax: nothing to redistribute (tick {tick})")


class SpoilageSystem:
    name = "spoilage"

    async def run(self, world: World) -> None:
        cfg = get_config()
        if cfg.bread_spoil_interval <= 0:
            return
        tick = world.get_resource(TickNumber).value
        if tick % cfg.bread_spoil_interval != 0:
            return
        perception = world.get_resource(BreadPerceptionBuilder)
        for entity, _inv in world.query(Inventory):
            if _inv.bread > 0:
                spoiled = min(_inv.bread, cfg.bread_spoil_amount)
                with world.mutate(entity, Inventory) as inv:
                    inv.bread -= spoiled
                perception.notify(
                    entity, f"{spoiled} bread spoiled (bread left: {inv.bread})"
                )


class AutoForageSystem:
    """Automatically forages for each agent every tick. Agents don't choose to forage."""

    name = "auto_forage"

    async def run(self, world: World) -> None:
        import random

        cfg = get_config()
        for entity, info, _inv in world.query(AgentInfo, Inventory):
            skills = cfg.forage_skill_by_role.get(info.role, {"flour": 1, "water": 1})
            cap = cfg.inventory_cap
            flour = random.randint(0, skills["flour"])
            water = random.randint(0, skills["water"])
            flour = min(flour, max(0, cap - _inv.flour))
            water = min(water, max(0, cap - _inv.water))
            with world.mutate(entity, Inventory) as inv:
                inv.flour += flour
                inv.water += water


class AutoBakeSystem:
    """Automatically bakes bread when agent has enough ingredients and bread is low."""

    name = "auto_bake"

    async def run(self, world: World) -> None:
        cfg = get_config()
        flour_cost = cfg.bake_cost["flour"]
        water_cost = cfg.bake_cost["water"]
        bread_yield = cfg.bake_yield
        cap = cfg.inventory_cap

        for entity, _inv in world.query(Inventory):
            with world.mutate(entity, Inventory) as inv:
                # Bake when bread is low and we have ingredients
                while (
                    inv.bread < 20 and inv.flour >= flour_cost and inv.water >= water_cost
                ):
                    inv.flour -= flour_cost
                    inv.water -= water_cost
                    actual = min(bread_yield, max(0, cap - inv.bread))
                    inv.bread += actual
                    if actual == 0:
                        break


class ConsumptionSystem:
    name = "consumption"

    async def run(self, world: World) -> None:
        cfg = get_config()
        perception = world.get_resource(BreadPerceptionBuilder)
        for entity, _h, _inv, _eco in world.query(Hunger, Inventory, Economy):
            with (
                world.mutate(entity, Hunger) as h,
                world.mutate(entity, Inventory) as inv,
                world.mutate(entity, Economy) as eco,
            ):
                # Auto-eat bread
                if h.hunger <= cfg.hunger_auto_eat_threshold:
                    bread_eaten = 0
                    while h.hunger <= cfg.hunger_auto_eat_threshold and inv.bread > 0:
                        inv.bread -= 1
                        h.hunger = min(cfg.hunger_max, h.hunger + cfg.hunger_eat_restore)
                        bread_eaten += 1
                    if bread_eaten:
                        perception.notify(
                            entity,
                            f"ate {bread_eaten} bread (hunger now {h.hunger}, bread left: {inv.bread})",
                        )

                    # Fall back to raw flour only if no bread
                    flour_eaten = 0
                    while h.hunger <= cfg.hunger_auto_eat_threshold and inv.flour > 0:
                        inv.flour -= 1
                        h.hunger = min(
                            cfg.hunger_max, h.hunger + cfg.hunger_eat_raw_restore
                        )
                        flour_eaten += 1
                    if flour_eaten:
                        perception.notify(
                            entity,
                            f"ate {flour_eaten} flour raw (hunger now {h.hunger}, flour left: {inv.flour})",
                        )

                if h.hunger == 0:
                    penalty = min(eco.coins, cfg.hunger_starve_coin_penalty)
                    eco.coins -= penalty
                    deposit_to_treasury(world, penalty)
                    perception.notify(
                        entity, f"coins -{cfg.hunger_starve_coin_penalty} (starving)"
                    )

                # Auto-drink
                if h.thirst <= cfg.thirst_auto_drink_threshold:
                    water_drunk = 0
                    while h.thirst <= cfg.thirst_auto_drink_threshold and inv.water > 0:
                        inv.water -= 1
                        h.thirst = min(cfg.hunger_max, h.thirst + cfg.thirst_drink_restore)
                        water_drunk += 1
                    if water_drunk:
                        perception.notify(
                            entity,
                            f"drank {water_drunk} water (thirst now {h.thirst}, water left: {inv.water})",
                        )

                if h.thirst == 0:
                    penalty = min(eco.coins, cfg.thirst_dehydration_coin_penalty)
                    eco.coins -= penalty
                    deposit_to_treasury(world, penalty)
                    perception.notify(
                        entity, f"coins -{cfg.thirst_dehydration_coin_penalty} (dehydrated)"
                    )


class DeathSystem:
    name = "death"

    def __init__(self, on_death: Callable[[str, World], None] | None = None):
        self._on_death = on_death

    async def run(self, world: World) -> None:
        # Snapshot query results since destroy() mutates the entity set
        for entity, h, inv in list(world.query(Hunger, Inventory)):
            if h.hunger == 0 and inv.bread == 0 and inv.flour == 0:
                log.info(f"[{entity}] DEAD -- starved")
                if self._on_death:
                    self._on_death(entity, world)
                world.destroy(entity)
