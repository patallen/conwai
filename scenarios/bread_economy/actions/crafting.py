from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING

from conwai.actions import ActionRegistry
from conwai.events import EventLog
from scenarios.bread_economy.actions.helpers import _capped_add
from scenarios.bread_economy.components import AgentInfo, Inventory
from scenarios.bread_economy.config import get_config

if TYPE_CHECKING:
    from conwai.world import World

log = logging.getLogger("conwai")


def _forage(entity_id: str, world: World, args: dict) -> str:
    cfg = get_config()
    info = world.get(entity_id, AgentInfo)
    skills = cfg.forage_skill_by_role.get(info.role, {"flour": 1, "water": 1})

    flour = random.randint(0, skills["flour"])
    water = random.randint(0, skills["water"])
    with world.mutate(entity_id, Inventory) as inv:
        flour = _capped_add(inv, "flour", flour)
        water = _capped_add(inv, "water", water)

    world.get_resource(ActionRegistry).block(
        entity_id, "You are foraging this tick and cannot take other actions."
    )
    world.get_resource(EventLog).log(
        entity_id, "forage", {"flour": flour, "water": water}
    )
    log.info(f"[{entity_id}] foraged {flour} flour, {water} water")
    parts = []
    if flour > 0:
        parts.append(f"{flour} flour")
    if water > 0:
        parts.append(f"{water} water")
    if parts:
        return f"foraged {', '.join(parts)}"
    return "found nothing"


def _bake(entity_id: str, world: World, args: dict) -> str:
    cfg = get_config()
    flour_needed = cfg.bake_cost["flour"]
    water_needed = cfg.bake_cost["water"]
    inv = world.get(entity_id, Inventory)
    if inv.flour < flour_needed or inv.water < water_needed:
        return f"need {flour_needed} flour and {water_needed} water to bake (have {inv.flour} flour, {inv.water} water)"
    info = world.get(entity_id, AgentInfo)
    bread_yield = cfg.bake_baker_yield if info.role == "baker" else cfg.bake_yield
    with world.mutate(entity_id, Inventory) as inv:
        inv.flour -= flour_needed
        inv.water -= water_needed
        bread_yield = _capped_add(inv, "bread", bread_yield)
    world.get_resource(EventLog).log(
        entity_id,
        "bake",
        {"bread": bread_yield, "flour": inv.flour, "water": inv.water},
    )
    log.info(f"[{entity_id}] baked {bread_yield} bread")
    return f"baked {bread_yield} bread (flour: {inv.flour}, water: {inv.water}, bread: {inv.bread})"
