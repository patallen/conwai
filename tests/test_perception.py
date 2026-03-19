from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.messages import MessageBus
from conwai.store import ComponentStore
from conwai.perception import Perception


def _make_store():
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    store.register_component("hunger", {"hunger": 100, "thirst": 100})
    store.register_component("memory", {"memory": "", "code_fragment": None, "soul": ""})
    return store


def test_perception_includes_board_posts():
    store = _make_store()
    store.init_agent("A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    board.post("A2", "hello world")

    p = Perception()
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "hello world" in text
    assert "A2" in text


def test_perception_includes_dms():
    store = _make_store()
    store.init_agent("A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    bus.send("A2", "A1", "secret message")

    p = Perception()
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "secret message" in text


def test_perception_includes_hunger_warning():
    store = _make_store()
    store.init_agent("A1")
    store.set("A1", "hunger", {"hunger": 20, "thirst": 100})
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    p = Perception()
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "hungry" in text.lower() or "hunger" in text.lower()


def test_perception_includes_state():
    store = _make_store()
    store.init_agent("A1")
    store.set("A1", "economy", {"coins": 42})
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    p = Perception()
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "42" in text


def test_perception_includes_notifications():
    store = _make_store()
    store.init_agent("A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    p = Perception()
    p.notify("A1", "coins -5 (daily tax)")
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "daily tax" in text
