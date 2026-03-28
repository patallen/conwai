"""Systems for the commons scenario."""
from __future__ import annotations
from typing import TYPE_CHECKING

import structlog
from conwai.scheduler import TickNumber

if TYPE_CHECKING:
    from conwai.world import World

log = structlog.get_logger()


class Pond:
    """Shared fish pond resource with logistic regeneration."""

    def __init__(self, population: float, capacity: float, growth_rate: float,
                 collapse_threshold: float):
        self.population = population
        self.capacity = capacity
        self.growth_rate = growth_rate
        self.collapse_threshold = collapse_threshold
        self.total_harvested: float = 0

    def harvest(self, amount: int) -> int:
        """Remove fish from the pond. Returns actual amount taken."""
        actual = min(amount, max(0, int(self.population)))
        self.population -= actual
        self.total_harvested += actual
        return actual

    def regenerate(self) -> None:
        """Double the population, capped at capacity. No regen below collapse threshold."""
        if self.population <= 0:
            return
        if self.population < self.collapse_threshold:
            self.population = 0  # Collapse
            return
        self.population = min(self.capacity, self.population * 2)


class PondSystem:
    """Applies logistic regeneration to the shared pond each tick."""
    name = "pond"

    async def run(self, world: World) -> None:
        from scenarios.commons.config import get_config
        cfg = get_config()
        tick = world.get_resource(TickNumber).value
        pond = world.get_resource(Pond)
        if tick < cfg.fish_interval or tick % cfg.fish_interval != 0:
            return
        before = pond.population
        pond.regenerate()
        log.info("pond_regenerated", tick=tick, before=round(before), after=round(pond.population), capacity=round(pond.capacity))
