"""Tests for EventBus and event types."""

from __future__ import annotations

import pytest

from conwai.event_bus import Event, EventBus
from conwai.event_types import (
    ActionExecuted,
    ComponentChanged,
    EntityDestroyed,
    EntitySpawned,
    TickEnded,
    TickStarted,
)


# ---------------------------------------------------------------------------
# Task 1: EventBus core
# ---------------------------------------------------------------------------


def test_subscribe_and_drain():
    """Events are not delivered until drain() is called."""
    bus = EventBus()
    received: list[Event] = []

    class Ping(Event):
        pass

    bus.subscribe(Ping, received.append)

    bus.emit(Ping())
    assert received == [], "handler must not fire before drain"
    assert bus.pending() == 1

    bus.drain()
    assert len(received) == 1
    assert bus.pending() == 0


def test_cascade():
    """A handler may emit further events; drain processes all of them."""
    bus = EventBus()
    log: list[str] = []

    class Alpha(Event):
        pass

    class Beta(Event):
        pass

    def on_alpha(event: Alpha) -> None:
        log.append("alpha")
        bus.emit(Beta())

    def on_beta(event: Beta) -> None:
        log.append("beta")

    bus.subscribe(Alpha, on_alpha)
    bus.subscribe(Beta, on_beta)

    bus.emit(Alpha())
    bus.drain()

    assert log == ["alpha", "beta"]


def test_emit_no_subscribers():
    """Emitting an event with no subscribers does not raise."""
    class Orphan(Event):
        pass

    bus = EventBus()
    bus.emit(Orphan())
    bus.drain()  # must not raise


def test_pending_counts_queued_events():
    bus = EventBus()

    class E(Event):
        pass

    assert bus.pending() == 0
    bus.emit(E())
    bus.emit(E())
    assert bus.pending() == 2
    bus.drain()
    assert bus.pending() == 0


def test_drain_cascade_guard():
    """drain() raises on runaway cascades."""
    bus = EventBus()

    class Loop(Event):
        pass

    bus.subscribe(Loop, lambda _: bus.emit(Loop()))
    bus.emit(Loop())
    with pytest.raises(RuntimeError, match="exceeded"):
        bus.drain(max_iterations=100)


def test_multiple_subscribers_same_type():
    """All subscribers for a type receive the event."""
    bus = EventBus()
    results: list[int] = []

    class Tick(Event):
        pass

    bus.subscribe(Tick, lambda _: results.append(1))
    bus.subscribe(Tick, lambda _: results.append(2))

    bus.emit(Tick())
    bus.drain()

    assert results == [1, 2]


# ---------------------------------------------------------------------------
# Task 2: Event types
# ---------------------------------------------------------------------------


def test_event_types_are_events():
    """All concrete event types must subclass Event."""
    for cls in (
        ComponentChanged,
        EntitySpawned,
        EntityDestroyed,
        ActionExecuted,
        TickStarted,
        TickEnded,
    ):
        assert issubclass(cls, Event), f"{cls.__name__} must subclass Event"


def test_component_changed_fields():
    """ComponentChanged stores entity, comp_type, old, and new."""
    from conwai.component import Component
    from dataclasses import dataclass

    @dataclass
    class Hp(Component):
        value: int = 100

    old = Hp(value=100)
    new = Hp(value=50)
    ev = ComponentChanged(entity="e1", comp_type=Hp, old=old, new=new)

    assert ev.entity == "e1"
    assert ev.comp_type is Hp
    assert ev.old is old
    assert ev.new is new


def test_entity_spawned_fields():
    ev = EntitySpawned(entity="agent_42")
    assert ev.entity == "agent_42"


def test_entity_destroyed_fields():
    ev = EntityDestroyed(entity="agent_7")
    assert ev.entity == "agent_7"


def test_action_executed_fields():
    ev = ActionExecuted(entity="e1", action="move", args={"dx": 1}, result="ok")
    assert ev.entity == "e1"
    assert ev.action == "move"
    assert ev.args == {"dx": 1}
    assert ev.result == "ok"


def test_action_executed_default_args():
    """args defaults to an empty dict (not shared across instances)."""
    a = ActionExecuted()
    b = ActionExecuted()
    a.args["x"] = 1
    assert b.args == {}, "default args must not be shared between instances"


def test_tick_started_fields():
    ev = TickStarted(tick=5)
    assert ev.tick == 5


def test_tick_ended_fields():
    ev = TickEnded(tick=5)
    assert ev.tick == 5


def test_event_types_routed_through_bus():
    """EventBus correctly dispatches concrete event types."""
    bus = EventBus()
    spawned: list[str] = []

    bus.subscribe(EntitySpawned, lambda e: spawned.append(e.entity))

    bus.emit(EntitySpawned(entity="alice"))
    bus.emit(EntitySpawned(entity="bob"))
    bus.emit(TickStarted(tick=1))  # different type, should not fire spawned handler

    bus.drain()

    assert spawned == ["alice", "bob"]
