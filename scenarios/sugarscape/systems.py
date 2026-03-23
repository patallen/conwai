from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from scenarios.sugarscape.components import Sugar
from scenarios.sugarscape.grid import Grid

if TYPE_CHECKING:
    from conwai.world import World

log = logging.getLogger("conwai")


class MetabolismSystem:
    name = "metabolism"

    async def run(self, world: World) -> None:
        dead = []
        for entity_id, sugar in world.query(Sugar):
            sugar.wealth -= sugar.metabolism
            if sugar.wealth <= 0:
                dead.append(entity_id)

        for entity_id in dead:
            log.info(f"[{entity_id}] died (starvation)")
            world.destroy(entity_id)


class RegrowthSystem:
    name = "regrowth"

    async def run(self, world: World) -> None:
        world.get_resource(Grid).regrow()
