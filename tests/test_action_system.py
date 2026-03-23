import asyncio

from conwai.actions import Action, ActionFeedback, ActionRegistry, ActionResult, PendingActions
from conwai.brain import Brain, BrainContext, Decision, Decisions
from conwai.component import Component
from conwai.contrib.systems import ActionSystem, BrainSystem
from conwai.engine import TickNumber
from conwai.typemap import Percept
from conwai.world import World


def test_pending_actions_is_component():
    assert issubclass(PendingActions, Component)


def test_action_feedback_is_component():
    assert issubclass(ActionFeedback, Component)


def test_action_result_fields():
    r = ActionResult(action="eat", args={}, result="yum")
    assert r.action == "eat"
    assert r.result == "yum"


class FakeDecider:
    async def run(self, ctx: BrainContext):
        decisions = ctx.bb.get(Decisions) or Decisions()
        decisions.entries.append(Decision("eat", {}))
        ctx.bb.set(decisions)


def test_action_system_executes_pending():
    world = World()
    world.register(PendingActions)
    world.register(ActionFeedback)
    world.spawn("A1")
    world.set("A1", PendingActions(entries=[Decision("eat", {})]))
    world.set_resource(TickNumber())

    def handler(eid, w, args):
        return "yum"

    registry = ActionRegistry()
    registry.register(Action(name="eat", handler=handler))

    system = ActionSystem(actions=registry)
    asyncio.run(system.run(world))

    fb = world.get("A1", ActionFeedback)
    assert len(fb.entries) == 1
    assert fb.entries[0].action == "eat"
    assert fb.entries[0].result == "yum"

    pa = world.get("A1", PendingActions)
    assert len(pa.entries) == 0


def test_action_system_skips_empty_pending():
    world = World()
    world.register(PendingActions)
    world.register(ActionFeedback)
    world.spawn("A1")
    world.set_resource(TickNumber())

    registry = ActionRegistry()
    system = ActionSystem(actions=registry)
    asyncio.run(system.run(world))

    fb = world.get("A1", ActionFeedback)
    assert len(fb.entries) == 0


def test_brain_system_writes_pending_actions():
    world = World()
    world.register(PendingActions)
    world.register(ActionFeedback)
    world.set_resource(TickNumber())
    world.spawn("A1")

    brain = Brain(processes=[FakeDecider()])
    brains = {"A1": brain}

    def perception(entity_id, w):
        return Percept()

    system = BrainSystem(brains=brains, perception=perception)
    asyncio.run(system.run(world))

    pa = world.get("A1", PendingActions)
    assert len(pa.entries) == 1
    assert pa.entries[0].action == "eat"


def test_brain_system_no_decisions_no_pending():
    world = World()
    world.register(PendingActions)
    world.register(ActionFeedback)
    world.set_resource(TickNumber())
    world.spawn("A1")

    brain = Brain(processes=[])
    brains = {"A1": brain}

    def perception(entity_id, w):
        return Percept()

    system = BrainSystem(brains=brains, perception=perception)
    asyncio.run(system.run(world))

    pa = world.get("A1", PendingActions)
    assert len(pa.entries) == 0
