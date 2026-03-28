"""Tests for the discrete event scheduler."""

import asyncio
from dataclasses import dataclass

from conwai.events import Event, EventBus
from conwai.scheduler import Scheduler


async def _val(v):
    return v


def test_schedule_and_run():
    bus = EventBus()
    s = Scheduler(bus)

    async def go():
        s.schedule("a", lambda: _val("done"))
        await s.run()

    asyncio.run(go())


def test_multiple_tasks_same_time():
    bus = EventBus()
    order = []

    async def track(key):
        order.append(key)

    s = Scheduler(bus)

    async def go():
        s.schedule("a", lambda: track("a"))
        s.schedule("b", lambda: track("b"))
        await s.run()

    asyncio.run(go())
    assert set(order) == {"a", "b"}


def test_error_does_not_crash_others():
    bus = EventBus()
    ran = []

    async def fail():
        raise RuntimeError("boom")

    async def ok():
        ran.append(True)

    s = Scheduler(bus)

    async def go():
        s.schedule("bad", fail)
        s.schedule("good", ok)
        await s.run()

    asyncio.run(go())
    assert ran == [True]


def test_duplicate_key_ignored():
    bus = EventBus()
    count = {"a": 0}

    async def track():
        count["a"] += 1

    s = Scheduler(bus)

    async def go():
        s.schedule("a", track)
        s.schedule("a", track)
        await s.run()

    asyncio.run(go())
    assert count["a"] == 1


def test_event_driven_retrigger():
    """Completed work triggers new work via EventBus."""
    bus = EventBus()
    ran = []

    @dataclass
    class Done(Event):
        key: str = ""

    s = Scheduler(bus)

    def on_done(event):
        if event.key == "a":
            s.schedule("b", lambda: _track("b"), cost=2)

    bus.subscribe(Done, on_done)

    async def _track(key):
        ran.append(key)
        bus.emit(Done(key=key))

    async def go():
        s.schedule("a", lambda: _track("a"))
        await s.run()

    asyncio.run(go())
    assert ran == ["a", "b"]


def test_same_time_retrigger():
    """Work at cost=0 triggers more work at the same sim_time."""
    bus = EventBus()
    ran = []

    @dataclass
    class Done(Event):
        key: str = ""

    s = Scheduler(bus)

    def on_done(event):
        if event.key == "a":
            s.schedule("b", lambda: _track("b"), cost=0)

    bus.subscribe(Done, on_done)

    async def _track(key):
        ran.append(key)
        bus.emit(Done(key=key))

    async def go():
        s.schedule("a", lambda: _track("a"))
        await s.run()

    asyncio.run(go())
    assert ran == ["a", "b"]


def test_cascade():
    """a -> b -> c cascade through events at different times."""
    bus = EventBus()
    ran = []
    times = {}

    @dataclass
    class Done(Event):
        key: str = ""

    s = Scheduler(bus)

    def on_done(event):
        if event.key == "a":
            s.schedule("b", lambda: _track("b"), cost=2)
        elif event.key == "b":
            s.schedule("c", lambda: _track("c"), cost=3)

    bus.subscribe(Done, on_done)

    async def _track(key):
        ran.append(key)
        times[key] = s.sim_time
        bus.emit(Done(key=key))

    async def go():
        s.schedule("a", lambda: _track("a"))
        await s.run()

    asyncio.run(go())
    assert ran == ["a", "b", "c"]
    assert times["a"] == 0
    assert times["b"] == 2
    assert times["c"] == 5  # 2 + 3


def test_until_stops_at_time():
    """run(until=N) stops before processing events at time N."""
    bus = EventBus()
    ran = []

    s = Scheduler(bus)

    async def go():
        s.schedule("early", lambda: _track("early"), cost=1)
        s.schedule("late", lambda: _track("late"), cost=10)
        await s.run(until=5)

    async def _track(key):
        ran.append(key)

    asyncio.run(go())
    assert "early" in ran
    assert "late" not in ran
    assert s.sim_time == 5


def test_until_preserves_heap():
    """Work past `until` stays on the heap for the next run()."""
    bus = EventBus()
    ran = []

    s = Scheduler(bus)

    async def _track(key):
        ran.append(key)

    async def go():
        s.schedule("a", lambda: _track("a"), cost=2)
        s.schedule("b", lambda: _track("b"), cost=8)
        await s.run(until=5)
        assert ran == ["a"]
        await s.run(until=10)
        assert ran == ["a", "b"]

    asyncio.run(go())


def test_sim_time_advances():
    """sim_time reflects when work resolved."""
    bus = EventBus()
    s = Scheduler(bus)
    resolved_at = {}

    async def track(key):
        resolved_at[key] = s.sim_time

    async def go():
        s.schedule("a", lambda: track("a"), cost=3)
        s.schedule("b", lambda: track("b"), cost=7)
        await s.run()

    asyncio.run(go())
    assert resolved_at["a"] == 3
    assert resolved_at["b"] == 7


def test_key_reusable_after_completion():
    """A key can be re-scheduled after its previous work completes."""
    bus = EventBus()
    count = {"a": 0}

    async def track():
        count["a"] += 1

    s = Scheduler(bus)

    async def go():
        s.schedule("a", track, cost=0)
        await s.run()
        s.schedule("a", track, cost=0)
        await s.run()

    asyncio.run(go())
    assert count["a"] == 2


def test_negative_cost_raises():
    bus = EventBus()
    s = Scheduler(bus)

    async def go():
        try:
            s.schedule("a", lambda: _val("x"), cost=-1)
            assert False, "should have raised"
        except ValueError:
            pass

    asyncio.run(go())


def test_conversation_within_one_run():
    """Three-message conversation in a single run."""
    bus = EventBus()
    transcript = []

    @dataclass
    class Message(Event):
        sender: str = ""
        recipient: str = ""

    s = Scheduler(bus, default_cost=2)

    inbox: dict[str, list[str]] = {"alice": [], "bob": []}

    def on_message(event):
        inbox[event.recipient].append(event.sender)
        s.schedule(event.recipient, lambda r=event.recipient: agent_act(r), cost=2)

    bus.subscribe(Message, on_message)

    async def agent_act(name):
        if name == "alice" and not inbox["alice"]:
            transcript.append("alice -> bob")
            bus.emit(Message(sender="alice", recipient="bob"))
        elif name == "bob" and inbox["bob"]:
            transcript.append("bob -> alice")
            bus.emit(Message(sender="bob", recipient="alice"))
        elif name == "alice" and inbox["alice"]:
            transcript.append("alice -> board")

    async def go():
        s.schedule("alice", lambda: agent_act("alice"))
        s.schedule("bob", lambda: agent_act("bob"))
        await s.run()

    asyncio.run(go())
    assert transcript == ["alice -> bob", "bob -> alice", "alice -> board"]
