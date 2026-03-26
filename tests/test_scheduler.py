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

    async def go():
        s.schedule("a", lambda: _val("done"))
        await s.run_tick()

    asyncio.run(go())


def test_multiple_tasks_concurrent():
    bus = EventBus()
    order = []

    async def track(key):
        order.append(key)

    s = Scheduler(bus, resolution=1)

    async def go():
        s.schedule("a", lambda: track("a"))
        s.schedule("b", lambda: track("b"))
        await s.run_tick()

    asyncio.run(go())
    assert set(order) == {"a", "b"}


def test_error_does_not_crash_others():
    bus = EventBus()
    ran = []

    async def fail():
        raise RuntimeError("boom")

    async def ok():
        ran.append(True)

    s = Scheduler(bus, resolution=1)

    async def go():
        s.schedule("bad", fail)
        s.schedule("good", ok)
        await s.run_tick()

    asyncio.run(go())
    assert ran == [True]


def test_duplicate_key_ignored():
    bus = EventBus()
    count = {"a": 0}

    async def track():
        count["a"] += 1

    s = Scheduler(bus, resolution=5)

    async def go():
        s.schedule("a", track)
        s.schedule("a", track)  # duplicate, ignored
        await s.run_tick()

    asyncio.run(go())
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

    async def go():
        s.schedule("a", lambda: _track("a"))
        await s.run_tick()

    asyncio.run(go())
    assert ran == ["a", "b"]


def test_same_time_retrigger():
    """Work scheduled at the same sim_time resolves in the same step."""
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

    async def go():
        s.schedule("a", lambda: _track("a"))
        await s.run_tick()
        assert ran == ["a", "b"]

    asyncio.run(go())


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

    async def go():
        s.schedule("a", lambda: _track("a"))
        await s.run_tick()

    asyncio.run(go())
    assert ran == ["a", "b", "c"]


def test_cost_past_resolution_carries_over():
    """Work past tick boundary carries over to next tick."""
    bus = EventBus()
    ran = []

    async def track():
        ran.append(True)

    s = Scheduler(bus, resolution=3, default_cost=0)

    async def go():
        s.schedule("a", lambda: _val("ok"))
        s.schedule("late", lambda: track(), cost=5)  # resolves at subtick 5
        await s.run_tick()  # tick has 3 subticks, "late" carries over
        assert ran == []
        await s.run_tick()  # "late" resolves (5 - 3 = subtick 2)
        assert ran == [True]

    asyncio.run(go())


def test_run_tick_resets_state():
    """Each run_tick starts fresh."""
    bus = EventBus()
    count = {"a": 0}

    async def track():
        count["a"] += 1

    s = Scheduler(bus, resolution=1)

    async def go():
        s.schedule("a", track)
        await s.run_tick()
        s.schedule("a", track)
        await s.run_tick()

    asyncio.run(go())
    assert count["a"] == 2


def test_task_with_cost_resolves_later():
    """Task scheduled with cost resolves at the right subtick."""
    bus = EventBus()
    resolved_at = {}

    s = Scheduler(bus, resolution=5, default_cost=3)

    async def track_resolve(key):
        resolved_at[key] = s.sim_time

    async def go():
        s.schedule("a", lambda: track_resolve("a"))  # cost=3, resolves at subtick 3
        await s.run_tick()

    asyncio.run(go())
    assert resolved_at["a"] == 3


def test_negative_cost_raises():
    """Negative cost is rejected."""
    bus = EventBus()
    s = Scheduler(bus, resolution=5)

    async def go():
        try:
            s.schedule("a", lambda: _val("x"), cost=-1)
            assert False, "should have raised"
        except ValueError:
            pass

    asyncio.run(go())


def test_conversation_within_one_tick():
    """Three-message conversation in a single tick.

    Old system: each agent thinks once per tick. A DMs B, B sees it
    next tick, replies, A sees reply the tick after. Three ticks.

    With the scheduler: A DMs B, B re-triggers and replies, A
    re-triggers and posts to board. One tick.
    """
    bus = EventBus()
    transcript = []

    @dataclass
    class Message(Event):
        sender: str = ""
        recipient: str = ""

    s = Scheduler(bus, resolution=10, default_cost=2)

    inbox: dict[str, list[str]] = {"alice": [], "bob": []}

    def on_message(event):
        inbox[event.recipient].append(event.sender)
        s.schedule(
            event.recipient,
            lambda r=event.recipient: agent_act(r),
            cost=2,
        )

    bus.subscribe(Message, on_message)

    async def agent_act(name):
        if name == "alice" and not inbox["alice"]:
            # First activation: alice DMs bob
            transcript.append("alice -> bob: hey want to coordinate?")
            bus.emit(Message(sender="alice", recipient="bob"))
        elif name == "bob" and inbox["bob"]:
            # Bob got a DM, replies
            transcript.append("bob -> alice: yeah let's fish less")
            bus.emit(Message(sender="bob", recipient="alice"))
        elif name == "alice" and inbox["alice"]:
            # Alice got reply, posts to board
            transcript.append("alice -> board: we agreed to conserve")

    async def go():
        s.schedule("alice", lambda: agent_act("alice"))
        s.schedule("bob", lambda: agent_act("bob"))
        await s.run_tick()

    asyncio.run(go())

    assert transcript == [
        "alice -> bob: hey want to coordinate?",
        "bob -> alice: yeah let's fish less",
        "alice -> board: we agreed to conserve",
    ]
