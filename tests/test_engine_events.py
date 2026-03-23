import asyncio

from conwai.engine import Engine, TickNumber
from conwai.event_bus import EventBus
from conwai.event_types import TickEnded, TickStarted
from conwai.world import World


def test_tick_emits_start_and_end():
    bus = EventBus()
    world = World(bus=bus)
    world.set_resource(TickNumber(0))
    received = []
    bus.subscribe(TickStarted, lambda e: received.append(("start", e.tick)))
    bus.subscribe(TickEnded, lambda e: received.append(("end", e.tick)))
    engine = Engine(world, systems=[])
    asyncio.run(engine.tick())
    assert received == [("start", 1), ("end", 1)]
