from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.messages import MessageBus
from conwai.processes.types import Observations
from conwai.store import ComponentStore
from scenarios.bread_economy.components import (
    AgentInfo,
    AgentMemory,
    Economy,
    Hunger,
    Inventory,
)
from scenarios.bread_economy.perception import make_bread_perception


def _make_store():
    store = ComponentStore()
    store.register(Economy)
    store.register(Inventory)
    store.register(Hunger)
    store.register(AgentMemory)
    store.register(AgentInfo)
    return store


def _init_agent(store, handle="A1", role="baker", personality="test"):
    store.init_agent(handle, overrides=[AgentInfo(role=role, personality=personality)])


def test_perception_includes_board_posts():
    store = _make_store()
    _init_agent(store, "A1", "baker")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    board.post("A2", "hello world")

    p = make_bread_perception()
    percept = p.build(Agent(handle="A1"), store, board, bus, tick=1)
    text = percept.get(Observations).text
    assert "hello world" in text
    assert "@A2" in text


def test_perception_includes_dms():
    store = _make_store()
    _init_agent(store, "A1", "baker")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    bus.send("A2", "A1", "secret message")

    p = make_bread_perception()
    percept = p.build(Agent(handle="A1"), store, board, bus, tick=1)
    text = percept.get(Observations).text
    assert "secret message" in text


def test_perception_includes_hunger_warning():
    store = _make_store()
    _init_agent(store, "A1", "baker")
    store.set("A1", Hunger(hunger=20, thirst=100))
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    p = make_bread_perception()
    percept = p.build(Agent(handle="A1"), store, board, bus, tick=1)
    text = percept.get(Observations).text
    assert "hungry" in text.lower() or "hunger" in text.lower()


def test_perception_includes_state():
    store = _make_store()
    _init_agent(store, "A1", "baker")
    store.set("A1", Economy(coins=42))
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    p = make_bread_perception()
    percept = p.build(Agent(handle="A1"), store, board, bus, tick=1)
    text = percept.get(Observations).text
    assert "42" in text


def test_perception_includes_notifications():
    store = _make_store()
    _init_agent(store, "A1", "baker")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    p = make_bread_perception()
    p.notify("A1", "coins -5 (daily tax)")
    percept = p.build(Agent(handle="A1"), store, board, bus, tick=1)
    text = percept.get(Observations).text
    assert "daily tax" in text
