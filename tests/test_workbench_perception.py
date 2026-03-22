from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.cognition.percept import ActionFeedback
from conwai.messages import MessageBus
from conwai.store import ComponentStore
from scenarios.workbench.perception import WorkbenchPerceptionBuilder


def _make_store():
    store = ComponentStore()
    store.register_component("agent_info", {"role": "", "personality": ""})
    store.register_component("brain", {"messages": [], "diary": []})
    return store


def _init_agent(store, handle="A1", role="observer", personality="curious"):
    store.init_agent(handle, overrides={"agent_info": {"role": role, "personality": personality}})


def test_percept_includes_broadcast():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    board.post("WORLD", "hello everyone")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "hello everyone" in percept.to_prompt()
    assert percept.agent_id == "A1"
    assert percept.tick == 1


def test_percept_includes_dms():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    bus.send("Bob", "A1", "private info")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "private info" in percept.to_prompt()


def test_percept_includes_identity():
    store = _make_store()
    _init_agent(store, "A1", role="analyst", personality="methodical, quiet")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "methodical" in percept.identity
    assert "A1" in percept.identity


def test_percept_includes_action_feedback():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    feedback = [ActionFeedback(action="broadcast", args={"content": "hi"}, result="sent")]
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1, action_feedback=feedback)
    assert percept.action_feedback == feedback


def test_percept_includes_injected_stimulus():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    builder.inject("A1", "A strange sound echoes from the north.")
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "strange sound" in percept.to_prompt()


def test_percept_no_activity():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    text = percept.to_prompt()
    assert isinstance(text, str)
    assert len(text) > 0
