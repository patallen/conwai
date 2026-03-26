import asyncio
from pathlib import Path

from conwai.actions import Action, ActionFeedback, ActionRegistry, ActionResult, PendingActions
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


def _dm_trigger(result: ActionResult) -> list[str]:
    """Trigger function: DMs re-trigger the recipient."""
    if result.action == "send_message":
        target = result.args.get("to", "").lstrip("@")
        if target:
            return [target]
    return []


def test_dm_retriggers_idle_recipient():
    """Sender DMs recipient. Recipient (idle) gets re-triggered and thinks again.

    Agents resolve in sorted order within a subtick. The sender must sort
    after the recipient so the recipient is already idle when the trigger fires.
    """
    think_count = {"sender": 0, "recipient": 0}

    class DMSender:
        async def run(self, ctx):
            think_count["sender"] += 1
            decisions = ctx.bb.get(Decisions) or Decisions()
            decisions.entries.append(
                Decision("send_message", {"to": "@A_recip", "message": "hello"})
            )
            ctx.bb.set(decisions)

    class Counter:
        async def run(self, ctx):
            think_count["recipient"] += 1
            decisions = ctx.bb.get(Decisions) or Decisions()
            decisions.entries.append(Decision("eat", {}))
            ctx.bb.set(decisions)

    world = _setup_world()
    world.spawn("A_recip")
    world.spawn("Z_sender")

    registry = ActionRegistry()
    registry.register(Action(name="eat", handler=lambda eid, w, a: "yum"))
    registry.register(
        Action(
            name="send_message",
            handler=lambda eid, w, a: f"sent to {a.get('to', '?')}",
        )
    )

    brains = {
        "Z_sender": Brain(processes=[DMSender()]),
        "A_recip": Brain(processes=[Counter()]),
    }

    # resolution=5, think_cost=2, retrigger_cost=2
    # Both resolve at subtick 1. Sorted order: A_recip, Z_sender.
    # A_recip goes idle first. Z_sender's DM triggers A_recip.
    # A_recip re-thinks, resolves at subtick 3.
    scheduler = SchedulerSystem(
        brains=brains,
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=5,
        think_cost=2,
        retrigger_cost=2,
        trigger_fn=_dm_trigger,
    )
    asyncio.run(scheduler.run(world))

    assert think_count["sender"] == 1      # sender thinks once
    assert think_count["recipient"] == 2   # recipient thinks twice: initial + re-trigger


def test_no_retrigger_at_resolution_1():
    """At resolution=1, no re-triggers fire -- backward compat."""
    think_count = {"recipient": 0}

    class DMSender:
        async def run(self, ctx):
            decisions = ctx.bb.get(Decisions) or Decisions()
            decisions.entries.append(
                Decision("send_message", {"to": "@A_recip", "message": "hi"})
            )
            ctx.bb.set(decisions)

    class Counter:
        async def run(self, ctx):
            think_count["recipient"] += 1

    world = _setup_world()
    world.spawn("A_recip")
    world.spawn("Z_sender")

    registry = ActionRegistry()
    registry.register(
        Action(name="send_message", handler=lambda eid, w, a: "sent")
    )

    brains = {
        "Z_sender": Brain(processes=[DMSender()]),
        "A_recip": Brain(processes=[Counter()]),
    }

    scheduler = SchedulerSystem(
        brains=brains,
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=1,
        trigger_fn=_dm_trigger,
    )
    asyncio.run(scheduler.run(world))

    # Recipient thinks exactly once -- no re-trigger at resolution=1
    assert think_count["recipient"] == 1


def test_cascade_retrigger():
    """Z_sender DMs B_mid, B_mid DMs A_end -- cascading re-triggers within one tick.

    Sorted processing order at subtick 1: A_end, B_mid, Z_sender.
    Z_sender's DM triggers B_mid (already idle). B_mid re-triggers at subtick 3,
    DMs A_end (already idle). A_end re-triggers at subtick 5.
    """
    think_count = {"sender": 0, "mid": 0, "end": 0}

    class DMTo:
        def __init__(self, target):
            self.target = target

        async def run(self, ctx):
            think_count["sender"] += 1
            decisions = ctx.bb.get(Decisions) or Decisions()
            decisions.entries.append(
                Decision(
                    "send_message",
                    {"to": f"@{self.target}", "message": "hey"},
                )
            )
            ctx.bb.set(decisions)

    class CountAndDM:
        """B_mid: count think, then DM A_end on re-trigger (2nd think)."""

        async def run(self, ctx):
            think_count["mid"] += 1
            decisions = ctx.bb.get(Decisions) or Decisions()
            if think_count["mid"] == 2:
                # On re-trigger, DM A_end
                decisions.entries.append(
                    Decision(
                        "send_message",
                        {"to": "@A_end", "message": "forwarding"},
                    )
                )
            else:
                decisions.entries.append(Decision("eat", {}))
            ctx.bb.set(decisions)

    class CountOnly:
        def __init__(self, key):
            self.key = key

        async def run(self, ctx):
            think_count[self.key] += 1

    world = _setup_world()
    world.spawn("A_end")
    world.spawn("B_mid")
    world.spawn("Z_sender")

    registry = ActionRegistry()
    registry.register(Action(name="eat", handler=lambda eid, w, a: "yum"))
    registry.register(
        Action(name="send_message", handler=lambda eid, w, a: "sent")
    )

    brains = {
        "Z_sender": Brain(processes=[DMTo("B_mid")]),
        "B_mid": Brain(processes=[CountAndDM()]),
        "A_end": Brain(processes=[CountOnly("end")]),
    }

    # resolution=10, think_cost=2, retrigger_cost=2
    # Subtick 1: A_end, B_mid, Z_sender resolve. Z_sender DMs B_mid -> B_mid re-triggered
    # Subtick 3: B_mid resolves re-trigger, DMs A_end -> A_end re-triggered
    # Subtick 5: A_end resolves re-trigger
    scheduler = SchedulerSystem(
        brains=brains,
        perception=lambda eid, w: Percept(),
        actions=registry,
        resolution=10,
        think_cost=2,
        retrigger_cost=2,
        trigger_fn=_dm_trigger,
    )
    asyncio.run(scheduler.run(world))

    assert think_count["sender"] == 1
    assert think_count["mid"] == 2  # initial + re-trigger
    assert think_count["end"] == 2  # initial + re-trigger from B_mid's cascade
