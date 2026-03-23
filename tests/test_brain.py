import asyncio
from dataclasses import dataclass, field

from conwai.brain import Brain, BrainContext, Decision
from conwai.processes.types import (
    Decisions,
    Episodes,
    Episode,
    LLMSnapshot,
    WorkingMemory,
    WorkingMemoryEntry,
)
from conwai.typemap import Percept, State


@dataclass
class FakeMemory:
    entries: list[str] = field(default_factory=list)


@dataclass
class FakeEpisodes:
    items: list[str] = field(default_factory=list)


def test_state_get_set():
    state = State()
    state.set(FakeMemory(entries=["a", "b"]))
    result = state.get(FakeMemory)
    assert result is not None
    assert result.entries == ["a", "b"]


def test_state_serialize():
    state = State()
    state.set(FakeMemory(entries=["a"]))
    data = state.serialize()
    assert "FakeMemory" in data
    assert data["FakeMemory"]["entries"] == ["a"]


def test_state_deserialize():
    data = {"FakeMemory": {"entries": ["a", "b"]}}
    registry = {"FakeMemory": FakeMemory}
    state = State.deserialize(data, registry)
    mem = state.get(FakeMemory)
    assert mem is not None
    assert mem.entries == ["a", "b"]


def test_state_deserialize_with_from_dict():
    """Types with from_dict get custom deserialization."""

    @dataclass
    class Nested:
        value: str

    @dataclass
    class HasNested:
        items: list[dict] = field(default_factory=list)

        @classmethod
        def from_dict(cls, data):
            return cls(items=[Nested(**d) for d in data.get("items", [])])

    data = {"HasNested": {"items": [{"value": "x"}]}}
    registry = {"HasNested": HasNested}
    state = State.deserialize(data, registry)
    result = state.get(HasNested)
    assert result.items[0].value == "x"


def test_working_memory_from_dict():
    data = {
        "entries": [{"content": "hello", "kind": "observation"}],
        "last_tick": 5,
        "tick_entry_start": 0,
    }
    wm = WorkingMemory.from_dict(data)
    assert len(wm.entries) == 1
    assert isinstance(wm.entries[0], WorkingMemoryEntry)
    assert wm.entries[0].content == "hello"
    assert wm.last_tick == 5


def test_episodes_from_dict():
    data = {
        "entries": [
            {"content": "traded flour", "tick": 3},
            {"content": "baked bread", "tick": 4, "embedding": [0.1, 0.2]},
        ]
    }
    eps = Episodes.from_dict(data)
    assert len(eps.entries) == 2
    assert isinstance(eps.entries[0], Episode)
    assert eps.entries[1].embedding == [0.1, 0.2]


# -- Brain tests ------------------------------------------------------------


class AppendDecision:
    def __init__(self, action: str):
        self.action = action

    async def run(self, ctx: BrainContext):
        decisions = ctx.bb.get(Decisions) or Decisions()
        decisions.entries.append(Decision(self.action, {}))
        ctx.bb.set(decisions)


class WriteToState:
    async def run(self, ctx: BrainContext):
        wm = ctx.state.get(WorkingMemory) or WorkingMemory()
        wm.last_tick = 99
        ctx.state.set(wm)


def test_brain_runs_processes_in_order():
    brain = Brain(processes=[AppendDecision("first"), AppendDecision("second")])
    decisions = asyncio.run(brain.think(Percept()))
    assert [d.action for d in decisions] == ["first", "second"]


def test_brain_state_persists_across_thinks():
    brain = Brain(processes=[WriteToState()])
    asyncio.run(brain.think(Percept()))
    wm = brain.state.get(WorkingMemory)
    assert wm.last_tick == 99


def test_brain_bb_is_fresh_each_think():
    class WriteScratch:
        async def run(self, ctx: BrainContext):
            ctx.bb.set(LLMSnapshot(system_prompt="test"))

    brain = Brain(processes=[WriteScratch()])
    asyncio.run(brain.think(Percept()))
    # State should NOT have LLMSnapshot
    assert brain.state.get(LLMSnapshot) is None


def test_brain_empty_pipeline():
    brain = Brain(processes=[])
    decisions = asyncio.run(brain.think(Percept()))
    assert decisions == []


def test_brain_save_load_state():
    brain = Brain(
        processes=[WriteToState()],
        state_types=[WorkingMemory],
    )
    asyncio.run(brain.think(Percept()))

    data = brain.save_state()
    assert "WorkingMemory" in data

    brain2 = Brain(
        processes=[WriteToState()],
        state_types=[WorkingMemory],
    )
    brain2.load_state(data)
    wm = brain2.state.get(WorkingMemory)
    assert wm.last_tick == 99
