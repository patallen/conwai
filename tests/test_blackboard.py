import asyncio
from dataclasses import dataclass

from conwai.cognition import BlackboardBrain, Decision
from conwai.store import ComponentStore


@dataclass
class FakePercept:
    agent_id: str = "A1"
    tick: int = 1

    def to_prompt(self) -> str:
        return f"tick {self.tick}"


class AppendDecision:
    """Process that writes a fixed decision to the board."""

    def __init__(self, action: str):
        self.action = action

    async def run(self, board):
        board.setdefault("decisions", []).append(Decision(self.action, {}))


class WriteToState:
    """Process that writes a marker to persistent state."""

    async def run(self, board):
        state = board.setdefault("state", {})
        state["visited"] = True


def test_processes_run_in_order():
    brain = BlackboardBrain(processes=[AppendDecision("first"), AppendDecision("second")])
    decisions = asyncio.run(brain.think(FakePercept()))
    assert [d.action for d in decisions] == ["first", "second"]


def test_board_state_committed_to_store():
    store = ComponentStore()
    store.register_component("brain", {"messages": [], "diary": []})
    store.init_agent("A1")

    brain = BlackboardBrain(processes=[WriteToState()], store=store)
    asyncio.run(brain.think(FakePercept()))

    saved = store.get("A1", "brain")
    assert saved.get("visited") is True


def test_board_state_loaded_from_store():
    store = ComponentStore()
    store.register_component("brain", {"messages": [], "diary": []})
    store.init_agent("A1")
    store.set("A1", "brain", {"messages": [{"role": "user", "content": "old"}], "diary": []})

    class CheckMessages:
        async def run(self, board):
            state = board.get("state", {})
            msgs = state.get("messages", [])
            assert len(msgs) == 1
            assert msgs[0]["content"] == "old"

    brain = BlackboardBrain(processes=[CheckMessages()], store=store)
    asyncio.run(brain.think(FakePercept()))


def test_empty_pipeline_returns_no_decisions():
    brain = BlackboardBrain(processes=[])
    decisions = asyncio.run(brain.think(FakePercept()))
    assert decisions == []


def test_percept_available_on_board():
    class CheckPercept:
        async def run(self, board):
            p = board["percept"]
            assert p.agent_id == "A1"
            assert p.tick == 5

    brain = BlackboardBrain(processes=[CheckPercept()])
    asyncio.run(brain.think(FakePercept(tick=5)))
