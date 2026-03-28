import asyncio

from conwai.actions import (
    Action,
    ActionFeedback,
    ActionRegistry,
    ActionResult,
    PendingActions,
    WorldActionAdapter,
)
from conwai.brain import Decision
from conwai.component import Component
from conwai.scheduler import TickNumber
from conwai.world import World


def test_pending_actions_is_component():
    assert issubclass(PendingActions, Component)


def test_action_feedback_is_component():
    assert issubclass(ActionFeedback, Component)


def test_action_result_fields():
    r = ActionResult(action="eat", args={}, result="yum")
    assert r.action == "eat"
    assert r.result == "yum"


def test_world_action_adapter_writes_pending_before_executing():
    """PendingActions must be written BEFORE actions execute, for snapshottability."""
    world = World()
    world.register(PendingActions)
    world.register(ActionFeedback)
    world.spawn("A1")
    world.set_resource(TickNumber())

    execution_order = []

    def handler(eid, w, args):
        # At execution time, PendingActions should already be on the entity
        pa = w.get(eid, PendingActions)
        execution_order.append(("execute", len(pa.entries)))
        return "ok"

    registry = ActionRegistry()
    registry.register(Action(name="eat", handler=handler))

    adapter = WorldActionAdapter(world=world, registry=registry)
    results = asyncio.run(adapter.execute("A1", [Decision("eat", {})]))

    assert execution_order == [
        ("execute", 1)
    ]  # PendingActions had 1 entry when handler ran
    assert len(results) == 1
    assert results[0].action == "eat"
    assert results[0].result == "ok"

    fb = world.get("A1", ActionFeedback)
    assert len(fb.entries) == 1


def test_world_action_adapter_empty_decisions():
    world = World()
    world.register(PendingActions)
    world.register(ActionFeedback)
    world.spawn("A1")
    world.set_resource(TickNumber())

    registry = ActionRegistry()
    adapter = WorldActionAdapter(world=world, registry=registry)
    results = asyncio.run(adapter.execute("A1", []))

    assert results == []
