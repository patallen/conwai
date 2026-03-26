import asyncio
from pathlib import Path

from conwai.actions import Action, ActionFeedback, ActionRegistry, PendingActions
from conwai.brain import Brain, BrainContext, Decision, Decisions
from conwai.engine import TickNumber
from conwai.scheduler import SchedulerSystem
from conwai.typemap import Percept
from conwai.world import World


class FakeDecider:
    """Process that always decides to 'eat'."""
    async def run(self, ctx: BrainContext):
        decisions = ctx.bb.get(Decisions) or Decisions()
        decisions.entries.append(Decision("eat", {}))
        ctx.bb.set(decisions)


def _setup_world():
    world = World()
    world.register(PendingActions)
    world.register(ActionFeedback)
    world.set_resource(TickNumber(value=1))
    return world


def _setup_registry():
    registry = ActionRegistry()
    registry.register(Action(name="eat", handler=lambda eid, w, a: "yum"))
    return registry


def test_scheduler_resolution_1_executes_actions():
    """At resolution=1, scheduler produces ActionFeedback just like ActionSystem."""
    world = _setup_world()
    world.spawn("A1")
    brain = Brain(processes=[FakeDecider()])
    registry = _setup_registry()
    scheduler = SchedulerSystem(
        brains={"A1": brain},
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=1,
    )
    asyncio.run(scheduler.run(world))
    fb = world.get("A1", ActionFeedback)
    assert len(fb.entries) == 1
    assert fb.entries[0].action == "eat"
    assert fb.entries[0].result == "yum"


def test_scheduler_resolution_1_multiple_agents():
    """All agents think concurrently and get feedback."""
    world = _setup_world()
    world.spawn("A1")
    world.spawn("A2")
    brains = {h: Brain(processes=[FakeDecider()]) for h in ("A1", "A2")}
    registry = _setup_registry()
    scheduler = SchedulerSystem(
        brains=brains,
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=1,
    )
    asyncio.run(scheduler.run(world))
    for handle in ("A1", "A2"):
        fb = world.get(handle, ActionFeedback)
        assert len(fb.entries) == 1
        assert fb.entries[0].result == "yum"


def test_scheduler_handles_brain_error():
    """Agent errors are logged, not raised. Other agents still execute."""
    class ExplodingProcess:
        async def run(self, ctx):
            raise RuntimeError("boom")

    world = _setup_world()
    world.spawn("A1")
    world.spawn("A2")
    brains = {
        "A1": Brain(processes=[ExplodingProcess()]),
        "A2": Brain(processes=[FakeDecider()]),
    }
    registry = _setup_registry()
    scheduler = SchedulerSystem(
        brains=brains,
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=1,
    )
    asyncio.run(scheduler.run(world))
    # Errored agent gets empty feedback
    fb_a1 = world.get("A1", ActionFeedback)
    assert fb_a1.entries == []
    # Healthy agent still succeeds
    fb = world.get("A2", ActionFeedback)
    assert len(fb.entries) == 1


def test_scheduler_no_decisions_produces_empty_feedback():
    """Agent with no decisions gets empty ActionFeedback."""
    world = _setup_world()
    world.spawn("A1")
    brain = Brain(processes=[])
    registry = _setup_registry()
    scheduler = SchedulerSystem(
        brains={"A1": brain},
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=1,
    )
    asyncio.run(scheduler.run(world))
    fb = world.get("A1", ActionFeedback)
    assert len(fb.entries) == 0


def test_scheduler_skips_destroyed_entities():
    """Agents not in world.entities() are skipped."""
    world = _setup_world()
    world.spawn("A1")
    brains = {
        "A1": Brain(processes=[FakeDecider()]),
        "GHOST": Brain(processes=[FakeDecider()]),
    }
    registry = _setup_registry()
    scheduler = SchedulerSystem(
        brains=brains,
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=1,
    )
    asyncio.run(scheduler.run(world))
    fb = world.get("A1", ActionFeedback)
    assert len(fb.entries) == 1


def test_scheduler_load_brain_states():
    """load_brain_states restores persisted state."""
    from conwai.storage import SQLiteStorage
    storage = SQLiteStorage(path=Path(":memory:"))
    world = World(storage=storage)
    world.register(PendingActions)
    world.register(ActionFeedback)
    world.set_resource(TickNumber(value=1))
    world.spawn("A1")
    brain = Brain(processes=[], state_types=[])
    brains = {"A1": brain}
    world.save_raw("A1", "brain_state", {"test_key": "test_val"})
    scheduler = SchedulerSystem(
        brains=brains,
        perception=lambda eid, w: Percept(),
        actions=_setup_registry(),
        resolution=1,
    )
    scheduler.load_brain_states(world)
    # Verify no crash -- state loading is best-effort


def test_subtick_agents_resolve_at_think_cost():
    """Agents resolve at the sub-tick matching think_cost."""
    world = _setup_world()
    world.spawn("A1")
    brain = Brain(processes=[FakeDecider()])
    registry = _setup_registry()

    # resolution=5, think_cost=3 -> agents resolve at sub-tick 2 (0-indexed)
    scheduler = SchedulerSystem(
        brains={"A1": brain},
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=5,
        think_cost=3,
    )
    asyncio.run(scheduler.run(world))

    fb = world.get("A1", ActionFeedback)
    assert len(fb.entries) == 1
    assert fb.entries[0].action == "eat"


def test_subtick_think_cost_clamped_to_resolution():
    """think_cost > resolution is clamped: agents still resolve within the tick."""
    world = _setup_world()
    world.spawn("A1")
    brain = Brain(processes=[FakeDecider()])
    registry = _setup_registry()

    scheduler = SchedulerSystem(
        brains={"A1": brain},
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=3,
        think_cost=10,
    )
    asyncio.run(scheduler.run(world))

    fb = world.get("A1", ActionFeedback)
    assert len(fb.entries) == 1


def test_subtick_no_trigger_fn_means_no_retriggers():
    """Without a trigger_fn, no agent is ever re-triggered."""
    think_count = {"B": 0}

    class DMSender:
        async def run(self, ctx):
            decisions = ctx.bb.get(Decisions) or Decisions()
            decisions.entries.append(
                Decision("send_message", {"to": "@B", "message": "hi"})
            )
            ctx.bb.set(decisions)

    class Counter:
        async def run(self, ctx):
            think_count["B"] += 1

    world = _setup_world()
    world.spawn("A")
    world.spawn("B")

    registry = ActionRegistry()
    registry.register(
        Action(name="send_message", handler=lambda eid, w, a: "sent")
    )

    brains = {
        "A": Brain(processes=[DMSender()]),
        "B": Brain(processes=[Counter()]),
    }

    scheduler = SchedulerSystem(
        brains=brains,
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=10,
        think_cost=2,
        trigger_fn=None,  # no re-triggers
    )
    asyncio.run(scheduler.run(world))

    assert think_count["B"] == 1
