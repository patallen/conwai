from __future__ import annotations

import structlog
from typing import TYPE_CHECKING

from conwai.actions import Action, ActionRegistry
from scenarios.sugarscape.components import Position, Sugar
from scenarios.sugarscape.grid import Grid

if TYPE_CHECKING:
    from conwai.world import World

log = structlog.get_logger()


def _move(entity_id: str, world: World, args: dict) -> str:
    dx = int(args.get("dx", 0))
    dy = int(args.get("dy", 0))
    grid = world.get_resource(Grid)
    pos = world.get(entity_id, Position)

    nx = max(0, min(grid.width - 1, pos.x + dx))
    ny = max(0, min(grid.height - 1, pos.y + dy))

    # Check if cell is occupied
    for other_id, other_pos in world.query(Position):
        if other_id != entity_id and other_pos.x == nx and other_pos.y == ny:
            return f"blocked, ({nx},{ny}) is occupied"

    pos.x = nx
    pos.y = ny

    # Harvest sugar at new position
    sugar = grid.harvest(nx, ny)
    if sugar > 0:
        store = world.get(entity_id, Sugar)
        store.wealth += sugar
        return f"moved to ({nx},{ny}), harvested {sugar} sugar"

    return f"moved to ({nx},{ny})"


def create_registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(Action(name="move", handler=_move))
    return registry
