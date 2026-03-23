from __future__ import annotations

import random
from dataclasses import dataclass, field

from conwai.brain import BrainContext, Decision, Decisions
from scenarios.sugarscape.perception import LocalView

# -- State types (persist across ticks) --


@dataclass
class CellMemory:
    x: int
    y: int
    sugar: int
    tick: int


@dataclass
class SugarMemory:
    """Remembered sugar locations."""

    cells: list[CellMemory] = field(default_factory=list)
    max_entries: int = 50

    @classmethod
    def from_dict(cls, data: dict) -> SugarMemory:
        return cls(
            cells=[CellMemory(**c) for c in data.get("cells", [])],
            max_entries=data.get("max_entries", 50),
        )


# -- Blackboard types (per-cycle scratch) --


@dataclass
class MovePlan:
    target_x: int
    target_y: int
    reason: str = ""


# -- Processes --


class RememberSugar:
    """Record visible sugar locations into persistent memory."""

    async def run(self, ctx: BrainContext) -> None:
        view = ctx.percept.get(LocalView)
        if not view:
            return

        memory = ctx.state.get(SugarMemory) or SugarMemory()

        # Update memory with what we see now
        seen = set()
        for cell in view.cells:
            seen.add((cell.x, cell.y))
            # Update or add
            found = False
            for mem in memory.cells:
                if mem.x == cell.x and mem.y == cell.y:
                    mem.sugar = cell.sugar
                    mem.tick = 0  # "just seen"
                    found = True
                    break
            if not found:
                memory.cells.append(
                    CellMemory(x=cell.x, y=cell.y, sugar=cell.sugar, tick=0)
                )

        # Age unseen memories
        for mem in memory.cells:
            if (mem.x, mem.y) not in seen:
                mem.tick += 1

        # Trim old memories
        memory.cells.sort(key=lambda m: (-m.sugar, m.tick))
        memory.cells = memory.cells[: memory.max_entries]

        ctx.state.set(memory)


class PlanMove:
    """Decide whether to exploit known sugar or explore.

    Exploit: go to the richest known cell.
    Explore: move in a random direction to find new sugar.
    Threshold: explore when wealthy, exploit when hungry.
    """

    def __init__(self, hunger_threshold: int = 15):
        self.hunger_threshold = hunger_threshold

    async def run(self, ctx: BrainContext) -> None:
        view = ctx.percept.get(LocalView)
        if not view:
            return

        memory = ctx.state.get(SugarMemory) or SugarMemory()
        hungry = view.my_wealth < self.hunger_threshold

        if hungry and memory.cells:
            # Exploit: target richest remembered cell
            best = max(memory.cells, key=lambda m: m.sugar)
            if best.sugar > 0:
                ctx.bb.set(
                    MovePlan(
                        target_x=best.x,
                        target_y=best.y,
                        reason="exploit",
                    )
                )
                return

        # Explore: pick a random direction
        dx, dy = random.choice([(0, -1), (0, 1), (-1, 0), (1, 0)])
        ctx.bb.set(
            MovePlan(
                target_x=view.my_x + dx * 3,
                target_y=view.my_y + dy * 3,
                reason="explore",
            )
        )


class ExecuteMove:
    """Pick the best visible unoccupied cell toward the plan's target."""

    async def run(self, ctx: BrainContext) -> None:
        view = ctx.percept.get(LocalView)
        plan = ctx.bb.get(MovePlan)
        if not view:
            return

        candidates = [c for c in view.cells if not c.occupied]
        if not candidates:
            return

        if plan:
            # Move toward target, prefer sugar along the way
            def score(c):
                dist_to_target = abs(c.x - plan.target_x) + abs(c.y - plan.target_y)
                return (c.sugar * 10) - dist_to_target

            candidates.sort(key=score, reverse=True)
            best = candidates[0]
        else:
            # No plan, just grab nearest sugar
            best_sugar = max(c.sugar for c in candidates)
            richest = [c for c in candidates if c.sugar == best_sugar]
            best = random.choice(richest)

        if best.sugar == 0 and not plan:
            return

        dx = best.x - view.my_x
        dy = best.y - view.my_y

        decisions = ctx.bb.get(Decisions) or Decisions()
        decisions.entries.append(Decision("move", {"dx": dx, "dy": dy}))
        ctx.bb.set(decisions)
