from pathlib import Path

from conwai.event_bus import EventBus
from conwai.event_types import EntityDestroyed, EntitySpawned
from conwai.events import EventLog


def test_event_log_subscribes_to_lifecycle():
    bus = EventBus()
    log = EventLog(path=Path(":memory:"))
    log.subscribe_to(bus)
    bus.emit(EntitySpawned(entity="e1"))
    bus.emit(EntityDestroyed(entity="e1"))
    bus.drain()
    events = log.read_since()
    assert len(events) == 2
    assert events[0]["entity"] == "e1"
    assert events[0]["type"] == "entity_spawned"
    assert events[1]["entity"] == "e1"
    assert events[1]["type"] == "entity_destroyed"
