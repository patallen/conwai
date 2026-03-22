import asyncio

from conwai.cognition import BlackboardBrain, BrainState, Decision
from conwai.processes.types import Decisions, WorkingMemory, WorkingMemoryEntry
from conwai.typemap import Blackboard, Percept
from conwai.world import World


class AppendDecision:
    def __init__(self, action: str):
        self.action = action

    async def run(self, percept: Percept, bb: Blackboard):
        decisions = bb.get(Decisions) or Decisions()
        decisions.entries.append(Decision(self.action, {}))
        bb.set(decisions)


class MarkLastTick:
    async def run(self, percept: Percept, bb: Blackboard):
        wm = bb.get(WorkingMemory) or WorkingMemory()
        wm.last_tick = 99
        bb.set(wm)


def test_processes_run_in_order():
    brain = BlackboardBrain(processes=[AppendDecision("first"), AppendDecision("second")])
    decisions = asyncio.run(brain.think(Percept()))
    assert [d.action for d in decisions] == ["first", "second"]


def test_brain_state_committed_to_store():
    world = World()
    world.register(BrainState)
    world.spawn("A1")

    brain = BlackboardBrain(processes=[MarkLastTick()])
    asyncio.run(brain.think(Percept()))
    world.set("A1", BrainState.save_from(brain.bb))

    saved = world.get("A1", BrainState)
    assert saved.last_tick == 99


def test_brain_state_loaded_from_store():
    world = World()
    world.register(BrainState)
    world.spawn("A1")
    world.set("A1", BrainState(
        working_memory=[{"content": "old", "kind": "observation"}],
    ))

    class CheckMemory:
        async def run(self, percept: Percept, bb: Blackboard):
            wm = bb.get(WorkingMemory)
            assert wm is not None
            assert len(wm.entries) == 1
            assert wm.entries[0].content == "old"

    brain = BlackboardBrain(processes=[CheckMemory()])
    brain_state = world.get("A1", BrainState)
    brain_state.load_into(brain.bb)
    asyncio.run(brain.think(Percept()))


def test_empty_pipeline():
    brain = BlackboardBrain(processes=[])
    decisions = asyncio.run(brain.think(Percept()))
    assert decisions == []
