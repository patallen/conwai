import asyncio
import random

import structlog

from conwai.actions import ActionFeedback, PendingActions, WorldActionAdapter
from conwai.brain import PipelineBrain
from conwai.events import EventBus
from conwai.scheduler import Scheduler, TickNumber
from conwai.tick_loop import TickLoop
from conwai.world import World
from scenarios.sugarscape.actions import create_registry
from scenarios.sugarscape.components import Position, Sugar, Vision
from scenarios.sugarscape.grid import Grid
from scenarios.sugarscape.perception import SugarPerception
from scenarios.sugarscape.processes import (
    ExecuteMove,
    PlanMove,
    RememberSugar,
    SugarMemory,
)
from scenarios.sugarscape.systems import MetabolismSystem, RegrowthSystem

log = structlog.get_logger()


def gini(values: list[int | float]) -> float:
    """Gini coefficient. 0 = perfect equality, 1 = one agent has everything."""
    if not values or sum(values) == 0:
        return 0.0
    sorted_v = sorted(values)
    n = len(sorted_v)
    total = sum(sorted_v)
    cum = sum((2 * (i + 1) - n - 1) * v for i, v in enumerate(sorted_v))
    return cum / (n * total)


_SUGAR_COLORS = {
    0: "\033[90m·\033[0m",  # dim dot
    1: "\033[33m░\033[0m",  # dim yellow
    2: "\033[93m▒\033[0m",  # yellow
    3: "\033[93m▓\033[0m",  # bright yellow
    4: "\033[93m█\033[0m",  # full yellow
}
_AGENT = "\033[1;32m@\033[0m"  # bright green


def render(world: World, grid: Grid) -> str:
    agents = {}
    for entity_id, pos in world.query(Position):
        agents[(pos.x, pos.y)] = entity_id

    lines = []
    for y in range(grid.height):
        row = []
        for x in range(grid.width):
            if (x, y) in agents:
                row.append(_AGENT)
            else:
                row.append(_SUGAR_COLORS.get(grid.sugar_at(x, y), "?"))
        lines.append(" ".join(row))
    return "\n".join(lines)


async def run(
    width: int = 20,
    height: int = 20,
    n_agents: int = 10,
    ticks: int = 100,
    seed: int | None = None,
):
    if seed is not None:
        random.seed(seed)

    # World
    world = World()
    world.register(Position)
    world.register(Sugar)
    world.register(Vision)
    world.register(PendingActions)
    world.register(ActionFeedback)

    # Grid — two sugar peaks
    grid = Grid(width, height)
    grid.seed_peaks()
    world.set_resource(grid)
    world.set_resource(TickNumber())

    # Actions
    registry = create_registry()

    adapter = WorldActionAdapter(world=world, registry=registry)

    # Perception
    perception = SugarPerception()

    # Agents — random metabolism (1-4), vision (1-6), scattered randomly
    brains: dict[str, PipelineBrain] = {}
    for i in range(n_agents):
        handle = f"A{i}"
        world.spawn(
            handle,
            overrides=[
                Position(
                    x=random.randint(0, width - 1), y=random.randint(0, height - 1)
                ),
                Sugar(wealth=random.randint(5, 25), metabolism=random.randint(1, 4)),
                Vision(range=random.randint(1, 6)),
            ],
        )
        brains[handle] = PipelineBrain(
            processes=[RememberSugar(), PlanMove(), ExecuteMove()],
            adapter=adapter,
            state_types=[SugarMemory],
        )

    bus = EventBus()
    scheduler = Scheduler(bus)

    async def on_tick(handle):
        percept = perception.build(handle, world)
        brains[handle].perceive(percept, scheduler, handle)

    loop = TickLoop(scheduler=scheduler, event_bus=bus, world=world)
    loop.add_pre_system(RegrowthSystem())
    loop.add_post_system(MetabolismSystem())

    tick_number = world.get_resource(TickNumber)

    # Run
    for t in range(ticks):
        alive = len(world.entities())
        if alive == 0:
            log.info("all_agents_dead", tick=t)
            break

        tick_number.value += 1

        handles = [h for h in brains if h in set(world.entities())]
        await loop.tick(handles, on_tick)

        wealths = [s.wealth for _, s in world.query(Sugar)]
        g = gini(wealths)
        print(f"\033[2J\033[H--- Tick {tick_number.value} ({alive} alive, gini={g:.2f}) ---")
        print(render(world, grid))
        print()
        for eid, sugar, vision in world.query(Sugar, Vision):
            bar = "█" * min(40, sugar.wealth // 2)
            print(
                f"  {eid:>3}: {bar} {sugar.wealth} (m={sugar.metabolism} v={vision.range})"
            )
        await asyncio.sleep(0.3)

    # Summary
    log.info("simulation_done", survivors=len(world.entities()), ticks=ticks)
    for entity_id, pos, sugar in world.query(Position, Sugar):
        log.info("agent_final", entity=entity_id, x=pos.x, y=pos.y, wealth=sugar.wealth)


def main():
    import logging

    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(logging.WARNING),
    )
    asyncio.run(run(width=50, height=50, n_agents=40, ticks=200, seed=42))


if __name__ == "__main__":
    main()
