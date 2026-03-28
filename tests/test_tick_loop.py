"""Tests for the TickLoop simulation loop."""

import asyncio

from conwai.events import EventBus
from conwai.scheduler import Scheduler
from conwai.tick_loop import TickLoop
from conwai.world import World


def _make_loop(**overrides) -> tuple[TickLoop, EventBus, World]:
    bus = EventBus()
    world = World(bus=bus)
    scheduler = Scheduler(bus)
    kwargs = dict(scheduler=scheduler, event_bus=bus, world=world)
    kwargs.update(overrides)
    return TickLoop(**kwargs), bus, world


def test_pre_systems_run_before_agents():
    order = []

    class PreSystem:
        async def run(self, world):
            order.append("pre")

    loop, bus, world = _make_loop()
    loop.add_pre_system(PreSystem())

    async def agent_fn(handle):
        order.append(f"agent:{handle}")

    asyncio.run(loop.tick(["a1"], agent_fn))
    assert order[0] == "pre"
    assert "agent:a1" in order


def test_post_systems_run_after_agents():
    order = []

    class PostSystem:
        async def run(self, world):
            order.append("post")

    loop, bus, world = _make_loop()
    loop.add_post_system(PostSystem())

    async def agent_fn(handle):
        order.append(f"agent:{handle}")

    asyncio.run(loop.tick(["a1"], agent_fn))
    assert order.index("agent:a1") < order.index("post")


def test_multiple_agents_run_concurrently():
    """All agents should be scheduled, not run sequentially by TickLoop."""
    ran = set()

    async def agent_fn(handle):
        ran.add(handle)

    loop, bus, world = _make_loop()
    asyncio.run(loop.tick(["a1", "a2", "a3"], agent_fn))
    assert ran == {"a1", "a2", "a3"}


def test_event_bus_drains_after_pre_systems():
    """Each pre-system should drain the event bus after running."""
    original_drain = EventBus.drain

    class Spy:
        def __init__(self, bus):
            self.bus = bus
            self.count = 0

        def patch(self):
            outer = self

            def counting_drain(self_bus, *args, **kwargs):
                outer.count += 1
                return original_drain(self_bus, *args, **kwargs)

            self.bus.drain = counting_drain.__get__(self.bus, EventBus)

    class EmittingSystem:
        async def run(self, world):
            pass

    loop, bus, world = _make_loop()
    spy = Spy(bus)
    spy.patch()

    loop.add_pre_system(EmittingSystem())
    loop.add_pre_system(EmittingSystem())

    async def agent_fn(handle):
        pass

    asyncio.run(loop.tick(["a1"], agent_fn))
    # At least one drain per pre-system
    assert spy.count >= 2


def test_event_bus_drains_after_post_systems():
    original_drain = EventBus.drain

    class Spy:
        def __init__(self, bus):
            self.bus = bus
            self.count = 0

        def patch(self):
            outer = self

            def counting_drain(self_bus, *args, **kwargs):
                outer.count += 1
                return original_drain(self_bus, *args, **kwargs)

            self.bus.drain = counting_drain.__get__(self.bus, EventBus)

    class PostSystem:
        async def run(self, world):
            pass

    loop, bus, world = _make_loop()
    spy = Spy(bus)
    spy.patch()

    loop.add_post_system(PostSystem())

    async def agent_fn(handle):
        pass

    asyncio.run(loop.tick(["a1"], agent_fn))
    # Scheduler drains internally + post-system drain
    assert spy.count >= 2


def test_persist_called_after_post_systems():
    order = []

    class PostSystem:
        async def run(self, world):
            order.append("post")

    def persist():
        order.append("persist")

    loop, bus, world = _make_loop()
    loop.add_post_system(PostSystem())
    loop.on_persist = persist

    async def agent_fn(handle):
        pass

    asyncio.run(loop.tick(["a1"], agent_fn))
    assert order.index("post") < order.index("persist")


def test_full_ordering():
    """pre -> agents -> post -> persist, in that order."""
    order = []

    class Pre:
        async def run(self, world):
            order.append("pre")

    class Post:
        async def run(self, world):
            order.append("post")

    def persist():
        order.append("persist")

    loop, bus, world = _make_loop()
    loop.add_pre_system(Pre())
    loop.add_post_system(Post())
    loop.on_persist = persist

    async def agent_fn(handle):
        order.append("agent")

    asyncio.run(loop.tick(["a1"], agent_fn))
    assert order == ["pre", "agent", "post", "persist"]


def test_no_agents_still_runs_systems():
    order = []

    class Pre:
        async def run(self, world):
            order.append("pre")

    class Post:
        async def run(self, world):
            order.append("post")

    loop, bus, world = _make_loop()
    loop.add_pre_system(Pre())
    loop.add_post_system(Post())

    async def agent_fn(handle):
        order.append("agent")

    asyncio.run(loop.tick([], agent_fn))
    assert order == ["pre", "post"]


def test_persist_not_called_when_not_set():
    """No crash when on_persist is not set."""
    loop, bus, world = _make_loop()

    async def agent_fn(handle):
        pass

    asyncio.run(loop.tick(["a1"], agent_fn))


def test_agent_cost_passed_to_scheduler():
    """Agent cost should be forwarded to the scheduler."""
    costs = []
    loop, bus, world = _make_loop()

    original_schedule = loop._scheduler.schedule

    def spy_schedule(key, task_fn, cost=None):
        costs.append(cost)
        return original_schedule(key, task_fn, cost=cost)

    loop._scheduler.schedule = spy_schedule

    async def agent_fn(handle):
        pass

    asyncio.run(loop.tick(["a1"], agent_fn, cost=5))
    assert costs == [5]
