from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from conwai.typemap import Percept

from scenarios.sugarscape.components import Sugar, Position, Vision
from scenarios.sugarscape.grid import Grid

if TYPE_CHECKING:
    from conwai.world import World


@dataclass
class VisibleCell:
    x: int
    y: int
    sugar: int
    occupied: bool = False


@dataclass
class LocalView:
    """What the agent can see along cardinal directions."""
    cells: list[VisibleCell] = field(default_factory=list)
    my_x: int = 0
    my_y: int = 0
    my_wealth: int = 0


_DIRECTIONS = [(0, -1), (0, 1), (-1, 0), (1, 0)]


class SugarPerception:
    def build(
        self,
        entity_id: str,
        world: World,
    ) -> Percept:
        grid = world.get_resource(Grid)
        pos = world.get(entity_id, Position)
        sugar = world.get(entity_id, Sugar)
        vision = world.get(entity_id, Vision)

        occupied = set()
        for other_id, other_pos in world.query(Position):
            if other_id != entity_id:
                occupied.add((other_pos.x, other_pos.y))

        cells = []
        for dx, dy in _DIRECTIONS:
            for dist in range(1, vision.range + 1):
                nx, ny = pos.x + dx * dist, pos.y + dy * dist
                if 0 <= nx < grid.width and 0 <= ny < grid.height:
                    cells.append(VisibleCell(
                        x=nx, y=ny,
                        sugar=grid.sugar_at(nx, ny),
                        occupied=(nx, ny) in occupied,
                    ))

        percept = Percept()
        percept.set(LocalView(
            cells=cells,
            my_x=pos.x,
            my_y=pos.y,
            my_wealth=sugar.wealth,
        ))
        return percept
