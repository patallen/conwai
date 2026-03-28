"""Fishing and rest actions."""

from __future__ import annotations

from typing import TYPE_CHECKING

import structlog

from conwai.actions import ActionRegistry
from conwai.scheduler import TickNumber
from scenarios.commons.components import FishHaul
from scenarios.commons.config import get_config
from scenarios.commons.systems import Pond

if TYPE_CHECKING:
    from conwai.world import World

log = structlog.get_logger()


def _fish(entity_id: str, world: World, args: dict) -> str | tuple[str, dict]:
    cfg = get_config()
    tick = world.get_resource(TickNumber).value
    if tick < cfg.fish_interval or tick % cfg.fish_interval != 0:
        return "It's not a fishing day. You can only fish every few ticks. Use this time to communicate."
    pond = world.get_resource(Pond)
    requested = args.get("amount", cfg.fish_default)
    if not isinstance(requested, int):
        try:
            requested = int(requested)
        except (ValueError, TypeError):
            requested = cfg.fish_default
    requested = max(cfg.fish_min, min(cfg.fish_max, requested))

    if pond.population <= 0:
        return "The pond is empty. There are no fish left."

    caught = pond.harvest(requested)
    with world.mutate(entity_id, FishHaul) as haul:
        haul.fish += caught

    world.get_resource(ActionRegistry).block(
        entity_id, "You are fishing this tick and cannot take other actions."
    )
    log.info(
        "fished",
        handle=entity_id,
        caught=caught,
        requested=requested,
        pond_population=round(pond.population),
    )
    return f"caught {caught} fish (pond population: {int(pond.population)})", {
        "caught": caught
    }


def _rest(entity_id: str, world: World, args: dict) -> str:
    log.info("resting", handle=entity_id)
    return "rested — no fish caught this tick"
