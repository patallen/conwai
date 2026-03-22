from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.cognition.percept import ActionFeedback
from conwai.messages import MessageBus
from conwai.processes.types import AgentHandle, Identity, Observations, PerceptFeedback, TickNumber
from conwai.store import ComponentStore
from scenarios.workbench.components import AgentInfo, BrainState
from scenarios.workbench.perception import WorkbenchPerceptionBuilder


def _make_store():
    store = ComponentStore()
    store.register(AgentInfo)
    store.register(BrainState)
    return store


def _init_agent(store, handle="A1", role="observer", personality="curious"):
    store.init_agent(handle, overrides=[AgentInfo(role=role, personality=personality)])


def test_percept_includes_broadcast():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    board.post("WORLD", "hello everyone")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "hello everyone" in percept.get(Observations).text
    assert percept.get(AgentHandle).value == "A1"
    assert percept.get(TickNumber).value == 1


def test_percept_includes_dms():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    bus.send("Bob", "A1", "private info")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "private info" in percept.get(Observations).text


def test_percept_includes_identity():
    store = _make_store()
    _init_agent(store, "A1", role="analyst", personality="methodical, quiet")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "methodical" in percept.get(Identity).text
    assert "A1" in percept.get(Identity).text


def test_percept_includes_action_feedback():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    feedback = [ActionFeedback(action="broadcast", args={"content": "hi"}, result="sent")]
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1, action_feedback=feedback)
    assert percept.get(PerceptFeedback).entries == feedback


def test_percept_includes_injected_stimulus():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    builder.inject("A1", "A strange sound echoes from the north.")
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "strange sound" in percept.get(Observations).text


def test_percept_no_activity():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    text = percept.get(Observations).text
    assert isinstance(text, str)
    assert len(text) > 0
