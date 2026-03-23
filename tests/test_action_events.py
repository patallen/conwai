from conwai.actions import Action, ActionRegistry
from conwai.event_bus import EventBus
from conwai.event_types import ActionExecuted
from conwai.world import World


def test_execute_emits_action_executed():
    bus = EventBus()
    world = World(bus=bus)
    world.spawn("e1", defaults=False)
    registry = ActionRegistry()
    registry.register(Action("ping", lambda eid, w, a: "pong"))
    registry.begin_tick(world, ["e1"])
    received = []
    bus.subscribe(ActionExecuted, lambda e: received.append(e))
    result = registry.execute("e1", "ping", {"x": 1}, world)
    bus.drain()
    assert result == "pong"
    assert len(received) == 1
    assert received[0].entity == "e1"
    assert received[0].action == "ping"
    assert received[0].args == {"x": 1}
    assert received[0].result == "pong"
