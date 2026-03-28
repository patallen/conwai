"""Tests for World event bus integration (Tasks 3 and 4)."""

from dataclasses import dataclass

import pytest

from conwai.component import Component
from conwai.events import ComponentChanged, EntityDestroyed, EntitySpawned, EventBus
from conwai.world import World


@dataclass
class Health(Component):
    hp: int = 100


@dataclass
class Position(Component):
    x: int = 0
    y: int = 0


# ---------------------------------------------------------------------------
# Task 3: World.mutate()
# ---------------------------------------------------------------------------


def test_mutate_emits_component_changed():
    bus = EventBus()
    world = World(bus=bus)
    world.register(Health)
    world.spawn("e1")

    received: list[ComponentChanged] = []
    bus.subscribe(ComponentChanged, received.append)

    with world.mutate("e1", Health) as h:
        h.hp = 50

    bus.drain()

    assert len(received) == 1
    evt = received[0]
    assert evt.entity == "e1"
    assert evt.comp_type is Health
    assert evt.old.hp == 100
    assert evt.new.hp == 50


def test_mutate_no_change_no_event():
    bus = EventBus()
    world = World(bus=bus)
    world.register(Health)
    world.spawn("e1")

    received: list[ComponentChanged] = []
    bus.subscribe(ComponentChanged, received.append)

    with world.mutate("e1", Health):
        pass  # no mutation

    bus.drain()
    assert received == []


def test_mutate_exception_no_event():
    bus = EventBus()
    world = World(bus=bus)
    world.register(Health)
    world.spawn("e1")

    received: list[ComponentChanged] = []
    bus.subscribe(ComponentChanged, received.append)

    with pytest.raises(RuntimeError):
        with world.mutate("e1", Health) as h:
            h.hp = 50
            raise RuntimeError("oops")

    bus.drain()
    # No event — the exception branch was taken
    assert received == []


def test_mutate_no_bus():
    world = World()  # no bus
    world.register(Health)
    world.spawn("e1")

    # Must not raise
    with world.mutate("e1", Health) as h:
        h.hp = 75

    assert world.get("e1", Health).hp == 75


# ---------------------------------------------------------------------------
# Task 4: set(), spawn(), destroy() events
# ---------------------------------------------------------------------------


def test_set_emits_component_changed():
    bus = EventBus()
    world = World(bus=bus)
    world.spawn("e1", defaults=False)
    world.set("e1", Health(hp=100))
    bus.drain()  # clear the initial set event

    received: list[ComponentChanged] = []
    bus.subscribe(ComponentChanged, received.append)

    world.set("e1", Health(hp=50))
    bus.drain()

    assert len(received) == 1
    evt = received[0]
    assert evt.entity == "e1"
    assert evt.comp_type is Health
    assert evt.old.hp == 100
    assert evt.new.hp == 50


def test_set_emits_component_changed_first_time():
    """set() with no prior component: old should be None."""
    bus = EventBus()
    world = World(bus=bus)
    world.spawn("e1", defaults=False)

    received: list[ComponentChanged] = []
    bus.subscribe(ComponentChanged, received.append)

    world.set("e1", Health(hp=42))
    bus.drain()

    assert len(received) == 1
    evt = received[0]
    assert evt.old is None
    assert evt.new.hp == 42


def test_spawn_emits_entity_spawned_only():
    """spawn() with defaults emits EntitySpawned but NOT ComponentChanged (suppressed)."""
    bus = EventBus()
    world = World(bus=bus)
    world.register(Health)

    spawned: list[EntitySpawned] = []
    changed: list[ComponentChanged] = []
    bus.subscribe(EntitySpawned, spawned.append)
    bus.subscribe(ComponentChanged, changed.append)

    world.spawn("e1")
    bus.drain()

    assert len(spawned) == 1
    assert spawned[0].entity == "e1"
    assert changed == []


def test_spawn_no_bus():
    """spawn() without a bus works normally."""
    world = World()
    world.register(Health)
    world.spawn("e1")
    assert world.get("e1", Health).hp == 100


def test_destroy_emits_entity_destroyed():
    bus = EventBus()
    world = World(bus=bus)
    world.spawn("e1", defaults=False)

    destroyed: list[EntityDestroyed] = []
    bus.subscribe(EntityDestroyed, destroyed.append)

    world.destroy("e1")
    bus.drain()

    assert len(destroyed) == 1
    assert destroyed[0].entity == "e1"


def test_destroy_event_carries_entity_id():
    """EntityDestroyed event carries the correct entity id."""
    bus = EventBus()
    world = World(bus=bus)
    world.spawn("e1", defaults=False)
    world.set("e1", Health(hp=77))
    bus.drain()  # clear setup events

    destroyed: list[EntityDestroyed] = []
    bus.subscribe(EntityDestroyed, destroyed.append)

    world.destroy("e1")
    bus.drain()

    assert len(destroyed) == 1
    assert destroyed[0].entity == "e1"


def test_destroy_no_bus():
    """destroy() without a bus works normally."""
    world = World()
    world.spawn("e1", defaults=False)
    world.destroy("e1")
    assert "e1" not in world.entities()
