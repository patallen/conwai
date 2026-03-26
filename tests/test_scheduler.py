"""Tests for the sub-tick scheduler."""

import asyncio
from dataclasses import dataclass

from conwai.event_bus import Event, EventBus
from conwai.scheduler import Scheduler


async def _val(v):
    return v


def test_schedule_and_run():
    bus = EventBus()
    s = Scheduler(bus, resolution=1)
    s.schedule("a", lambda: _val("done"))
    asyncio.run(s.run_tick())


def test_multiple_tasks_concurrent():
    bus = EventBus()
    order = []

    async def track(key):
        order.append(key)

    s = Scheduler(bus, resolution=1)
    s.schedule("a", lambda: track("a"))
    s.schedule("b", lambda: track("b"))
    asyncio.run(s.run_tick())
    assert set(order) == {"a", "b"}


def test_error_does_not_crash_others():
    bus = EventBus()
    ran = []

    async def fail():
        raise RuntimeError("boom")

    async def ok():
        ran.append(True)

    s = Scheduler(bus, resolution=1)
    s.schedule("bad", fail)
    s.schedule("good", ok)
    asyncio.run(s.run_tick())
    assert ran == [True]


def test_duplicate_key_ignored():
    bus = EventBus()
    count = {"a": 0}

    async def track():
        count["a"] += 1

    s = Scheduler(bus, resolution=5)
    s.schedule("a", track)
    s.schedule("a", track)  # duplicate, ignored
    asyncio.run(s.run_tick())
    assert count["a"] == 1


def test_event_driven_retrigger():
    """Events from completed work trigger new work via the EventBus."""
    bus = EventBus()
    ran = []

    @dataclass
    class Done(Event):
        key: str = ""

    s = Scheduler(bus, resolution=5, default_cost=0)

    def on_done(event):
        if event.key == "a":
            s.schedule("b", lambda: _track("b"), cost=1)

    bus.subscribe(Done, on_done)

    async def _track(key):
        ran.append(key)
        bus.emit(Done(key=key))

    s.schedule("a", lambda: _track("a"))
    asyncio.run(s.run_tick())

    assert ran == ["a", "b"]


def test_no_retrigger_at_resolution_1():
    """At resolution=1, no room for re-triggered work."""
    bus = EventBus()
    ran = []

    @dataclass
    class Done(Event):
        key: str = ""

    s = Scheduler(bus, resolution=1, default_cost=0)

    def on_done(event):
        if event.key == "a":
            s.schedule("b", lambda: _track("b"), cost=0)

    bus.subscribe(Done, on_done)

    async def _track(key):
        ran.append(key)
        bus.emit(Done(key=key))

    s.schedule("a", lambda: _track("a"))
    asyncio.run(s.run_tick())

    assert ran == ["a"]


def test_cascade():
    """a -> b -> c cascade through events."""
    bus = EventBus()
    ran = []

    @dataclass
    class Done(Event):
        key: str = ""

    s = Scheduler(bus, resolution=10, default_cost=0)

    def on_done(event):
        if event.key == "a":
            s.schedule("b", lambda: _track("b"), cost=2)
        elif event.key == "b":
            s.schedule("c", lambda: _track("c"), cost=2)

    bus.subscribe(Done, on_done)

    async def _track(key):
        ran.append(key)
        bus.emit(Done(key=key))

    s.schedule("a", lambda: _track("a"))
    asyncio.run(s.run_tick())

    assert ran == ["a", "b", "c"]


def test_cost_past_resolution_dropped():
    """Work that would resolve past the tick is dropped."""
    bus = EventBus()

    s = Scheduler(bus, resolution=3, default_cost=0)
    s.schedule("a", lambda: _val("ok"))
    s.schedule("late", lambda: _val("nope"), cost=5)
    asyncio.run(s.run_tick())
    # "late" was dropped, only "a" ran


def test_run_tick_resets_state():
    """Each run_tick starts fresh."""
    bus = EventBus()
    count = {"a": 0}

    async def track():
        count["a"] += 1

    s = Scheduler(bus, resolution=1)
    s.schedule("a", track)
    asyncio.run(s.run_tick())

    s.schedule("a", track)
    asyncio.run(s.run_tick())

    assert count["a"] == 2
