from pathlib import Path

from conwai.events import ActionExecuted, EntityDestroyed, EntitySpawned, EventBus, EventLog


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


def test_event_log_subscribes_to_action_executed():
    bus = EventBus()
    log = EventLog(path=Path(":memory:"))
    log.subscribe_to(bus)
    bus.emit(ActionExecuted(
        entity="e1", action="forage", args={"x": 1}, result="ok",
        data={"flour": 3, "water": 2},
    ))
    bus.drain()
    events = log.read_since()
    assert len(events) == 1
    assert events[0]["entity"] == "e1"
    assert events[0]["type"] == "forage"
    # data merges args + handler data
    assert events[0]["data"]["x"] == 1
    assert events[0]["data"]["flour"] == 3
    assert events[0]["data"]["water"] == 2
