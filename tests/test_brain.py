import asyncio
from dataclasses import dataclass, field

from conwai.brain import (
    ActionAdapter,
    BrainContext,
    Decision,
    Decisions,
    PipelineBrain,
)
from conwai.brain import (
    Brain as BrainProtocol,
)
from conwai.events import EventBus
from conwai.processes.types import (
    Episode,
    Episodes,
    LLMSnapshot,
    WorkingMemory,
    WorkingMemoryEntry,
)
from conwai.scheduler import Scheduler
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


def test_brain_protocol_compliance():
    class MinimalBrain:
        def perceive(self, percept, scheduler, handle):
            pass

        def save_state(self):
            return {}

        def load_state(self, data):
            pass

    assert isinstance(MinimalBrain(), BrainProtocol)


class FakeAdapter:
    def __init__(self):
        self.calls: list[tuple[str, list[Decision]]] = []

    async def execute(self, handle, decisions):
        self.calls.append((handle, list(decisions)))
        return []


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


def test_perceive_schedules_work():
    bus = EventBus()
    scheduler = Scheduler(bus=bus)
    adapter = FakeAdapter()
    brain = PipelineBrain(processes=[AppendDecision("eat")], adapter=adapter)

    brain.perceive(Percept(), scheduler, "A1")

    # perceive() just schedules — adapter not called yet
    assert adapter.calls == []
    assert len(scheduler._heap) == 1


def test_perceive_runs_pipeline_and_calls_adapter():
    bus = EventBus()
    scheduler = Scheduler(bus=bus)
    adapter = FakeAdapter()
    brain = PipelineBrain(processes=[AppendDecision("eat")], adapter=adapter)

    brain.perceive(Percept(), scheduler, "A1")
    asyncio.run(scheduler.run())

    assert len(adapter.calls) == 1
    handle, decisions = adapter.calls[0]
    assert handle == "A1"
    assert [d.action for d in decisions] == ["eat"]


def test_perceive_runs_processes_in_order():
    bus = EventBus()
    scheduler = Scheduler(bus=bus)
    adapter = FakeAdapter()
    brain = PipelineBrain(
        processes=[AppendDecision("first"), AppendDecision("second")],
        adapter=adapter,
    )

    brain.perceive(Percept(), scheduler, "A1")
    asyncio.run(scheduler.run())

    _, decisions = adapter.calls[0]
    assert [d.action for d in decisions] == ["first", "second"]


def test_perceive_no_decisions_skips_adapter():
    bus = EventBus()
    scheduler = Scheduler(bus=bus)
    adapter = FakeAdapter()
    brain = PipelineBrain(processes=[], adapter=adapter)

    brain.perceive(Percept(), scheduler, "A1")
    asyncio.run(scheduler.run())

    assert adapter.calls == []


def test_perceive_state_persists_across_calls():
    bus = EventBus()
    scheduler = Scheduler(bus=bus)
    adapter = FakeAdapter()
    brain = PipelineBrain(processes=[WriteToState()], adapter=adapter)

    brain.perceive(Percept(), scheduler, "A1")
    asyncio.run(scheduler.run())

    wm = brain.state.get(WorkingMemory)
    assert wm.last_tick == 99


def test_perceive_duplicate_dropped_while_active():
    bus = EventBus()
    scheduler = Scheduler(bus=bus)
    adapter = FakeAdapter()
    brain = PipelineBrain(processes=[AppendDecision("eat")], adapter=adapter)

    brain.perceive(Percept(), scheduler, "A1")
    brain.perceive(Percept(), scheduler, "A1")  # duplicate — should be dropped

    assert len(scheduler._heap) == 1  # only one task scheduled


def test_pipeline_brain_save_load_state():
    bus = EventBus()
    scheduler = Scheduler(bus=bus)
    adapter = FakeAdapter()
    brain = PipelineBrain(
        processes=[WriteToState()],
        adapter=adapter,
        state_types=[WorkingMemory],
    )

    brain.perceive(Percept(), scheduler, "A1")
    asyncio.run(scheduler.run())

    data = brain.save_state()
    assert "WorkingMemory" in data

    brain2 = PipelineBrain(
        processes=[WriteToState()],
        adapter=adapter,
        state_types=[WorkingMemory],
    )
    brain2.load_state(data)
    wm = brain2.state.get(WorkingMemory)
    assert wm.last_tick == 99


def test_perceive_bb_is_fresh_each_call():
    class WriteScratch:
        async def run(self, ctx: BrainContext):
            ctx.bb.set(LLMSnapshot(system_prompt="test"))

    bus = EventBus()
    scheduler = Scheduler(bus=bus)
    adapter = FakeAdapter()
    brain = PipelineBrain(processes=[WriteScratch()], adapter=adapter)

    brain.perceive(Percept(), scheduler, "A1")
    asyncio.run(scheduler.run())

    assert brain.state.get(LLMSnapshot) is None


def test_action_adapter_protocol_compliance():
    class MinimalAdapter:
        async def execute(self, handle, decisions):
            return []

    assert isinstance(MinimalAdapter(), ActionAdapter)
