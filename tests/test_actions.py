from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.store import ComponentStore
from conwai.perception import Perception
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.default_actions import create_registry
from pathlib import Path
import tempfile


def _setup():
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    store.register_component("hunger", {"hunger": 100, "thirst": 100})
    store.register_component("memory", {"memory": "", "code_fragment": None, "soul": ""})
    board = BulletinBoard()
    bus = MessageBus()
    events = EventLog(path=Path(":memory:"))
    perception = Perception()
    tmp = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp / "agents")
    pool = AgentPool(repo, bus, store)
    return store, board, bus, events, perception, pool


def _add(pool, handle, role):
    return pool.load_or_create(Agent(handle=handle, role=role, personality="test"))


def _make_registry(store, board, bus, events, perception, pool, tick_state=None):
    return create_registry(
        store=store, board=board, bus=bus, events=events,
        pool=pool, perception=perception, tick_state=tick_state,
    )


def test_forage_updates_store():
    store, board, bus, events, perception, pool = _setup()
    agent = _add(pool, "A1", "flour_forager")
    registry = _make_registry(store, board, bus, events, perception, pool)
    result = registry.execute(agent, "forage", {})
    inv = store.get("A1", "inventory")
    assert isinstance(result, str)
    assert inv["flour"] >= 0


def test_pay_transfers_coins():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, "A1", "baker")
    _add(pool, "A2", "baker")
    agent = pool.by_handle("A1")
    registry = _make_registry(store, board, bus, events, perception, pool)
    result = registry.execute(agent, "pay", {"to": "A2", "amount": 100})
    assert store.get("A1", "economy")["coins"] == 400
    assert store.get("A2", "economy")["coins"] == 600


def test_post_to_board():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, "A1", "baker")
    registry = _make_registry(store, board, bus, events, perception, pool)
    result = registry.execute(agent=pool.by_handle("A1"), name="post_to_board", args={"message": "hello"})
    posts = board.read_new("OTHER")
    assert any(p.content == "hello" for p in posts)


def test_send_message():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, "A1", "baker")
    _add(pool, "A2", "baker")
    tick_state = {"A1": {}, "A2": {}}
    registry = _make_registry(store, board, bus, events, perception, pool, tick_state=tick_state)
    result = registry.execute(pool.by_handle("A1"), "send_message", {"to": "A2", "message": "hi"})
    dms = bus.receive("A2")
    assert len(dms) == 1
    assert dms[0].content == "hi"


def test_give_updates_both_stores():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, "A1", "flour_forager")
    _add(pool, "A2", "baker")
    store.set("A1", "inventory", {"flour": 10, "water": 0, "bread": 0})
    registry = _make_registry(store, board, bus, events, perception, pool)
    result = registry.execute(pool.by_handle("A1"), "give", {"to": "A2", "resource": "flour", "amount": 5})
    assert store.get("A1", "inventory")["flour"] == 5
    assert store.get("A2", "inventory")["flour"] == 5


def test_bake():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, "A1", "baker")
    store.set("A1", "inventory", {"flour": 10, "water": 10, "bread": 0})
    registry = _make_registry(store, board, bus, events, perception, pool)
    result = registry.execute(pool.by_handle("A1"), "bake", {})
    inv = store.get("A1", "inventory")
    assert inv["bread"] > 0


def test_inspect():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, "A1", "baker")
    _add(pool, "A2", "flour_forager")
    registry = _make_registry(store, board, bus, events, perception, pool)
    result = registry.execute(pool.by_handle("A1"), "inspect", {"handle": "A2"})
    assert "A2" in result
    assert "flour forager" in result


def test_update_soul():
    store, board, bus, events, perception, pool = _setup()
    agent = _add(pool, "A1", "baker")
    registry = _make_registry(store, board, bus, events, perception, pool)
    registry.execute(agent, "update_soul", {"content": "I am wise"})
    mem = store.get("A1", "memory")
    assert mem["soul"] == "I am wise"


def test_update_journal():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, "A1", "baker")
    registry = _make_registry(store, board, bus, events, perception, pool)
    registry.execute(pool.by_handle("A1"), "update_journal", {"content": "day 1 notes"})
    mem = store.get("A1", "memory")
    assert mem["memory"] == "day 1 notes"


def test_cost_deducted():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, "A1", "baker")
    registry = _make_registry(store, board, bus, events, perception, pool)
    # post_to_board costs 25
    registry.execute(pool.by_handle("A1"), "post_to_board", {"message": "test"})
    assert store.get("A1", "economy")["coins"] == 475


def test_insufficient_coins():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, "A1", "baker")
    store.set("A1", "economy", {"coins": 5})
    registry = _make_registry(store, board, bus, events, perception, pool)
    result = registry.execute(pool.by_handle("A1"), "post_to_board", {"message": "test"})
    assert "not enough coins" in result
