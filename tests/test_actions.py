import tempfile
from pathlib import Path

from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickContext
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.store import ComponentStore
from scenarios.bread_economy.actions import create_registry
from scenarios.bread_economy.perception import make_bread_perception


def _setup():
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    store.register_component("hunger", {"hunger": 100, "thirst": 100})
    store.register_component("memory", {"memory": "", "code_fragment": None, "soul": ""})
    store.register_component("forage", {"streak": 0})
    store.register_component("agent_info", {"role": "", "personality": ""})
    board = BulletinBoard()
    bus = MessageBus()
    events = EventLog(path=Path(":memory:"))
    perception = make_bread_perception()
    tmp = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp / "agents")
    pool = AgentPool(repo, store, bus=bus)
    return store, board, bus, events, perception, pool


def _add(pool, store, handle, role):
    agent = pool.load_or_create(
        Agent(handle=handle),
        component_overrides={"agent_info": {"role": role, "personality": "test"}},
    )
    return agent


def _make_ctx(store, board, bus, events, perception, pool, tick=1):
    return TickContext(
        tick=tick, pool=pool, store=store,
        perception=perception, board=board, bus=bus, events=events,
    )


def _make_registry():
    return create_registry()


def test_pay_transfers_coins():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1", "baker")
    _add(pool, store, "A2", "baker")
    agent = pool.by_handle("A1")
    registry = _make_registry()
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry.begin_tick(ctx, ["A1", "A2"])
    registry.execute(agent, "pay", {"to": "A2", "amount": 100}, ctx)
    assert store.get("A1", "economy")["coins"] == 400
    assert store.get("A2", "economy")["coins"] == 600


def test_post_to_board():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1", "baker")
    registry = _make_registry()
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry.begin_tick(ctx, ["A1"])
    registry.execute(agent=pool.by_handle("A1"), name="post_to_board", args={"message": "hello"}, ctx=ctx)
    posts = board.read_new("OTHER")
    assert any(p.content == "hello" for p in posts)


def test_send_message():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1", "baker")
    _add(pool, store, "A2", "baker")
    registry = _make_registry()
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry.begin_tick(ctx, ["A1", "A2"])
    registry.execute(pool.by_handle("A1"), "send_message", {"to": "A2", "message": "hi"}, ctx)
    dms = bus.receive("A2")
    assert len(dms) == 1
    assert dms[0].content == "hi"


def test_give_updates_both_stores():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1", "flour_forager")
    _add(pool, store, "A2", "baker")
    store.set("A1", "inventory", {"flour": 10, "water": 0, "bread": 0})
    registry = _make_registry()
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry.begin_tick(ctx, ["A1", "A2"])
    registry.execute(pool.by_handle("A1"), "give", {"to": "A2", "resource": "flour", "amount": 5}, ctx)
    assert store.get("A1", "inventory")["flour"] == 5
    assert store.get("A2", "inventory")["flour"] == 5


def test_inspect():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1", "baker")
    _add(pool, store, "A2", "flour_forager")
    registry = _make_registry()
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry.begin_tick(ctx, ["A1", "A2"])
    result = registry.execute(pool.by_handle("A1"), "inspect", {"handle": "A2"}, ctx)
    assert "A2" in result
    assert "flour forager" in result


def test_update_soul():
    store, board, bus, events, perception, pool = _setup()
    agent = _add(pool, store, "A1", "baker")
    registry = _make_registry()
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry.begin_tick(ctx, ["A1"])
    registry.execute(agent, "update_soul", {"content": "I am wise"}, ctx)
    mem = store.get("A1", "memory")
    assert mem["soul"] == "I am wise"


def test_update_journal():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1", "baker")
    registry = _make_registry()
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry.begin_tick(ctx, ["A1"])
    registry.execute(pool.by_handle("A1"), "update_journal", {"content": "day 1 notes"}, ctx)
    mem = store.get("A1", "memory")
    assert mem["memory"] == "day 1 notes"


def test_cost_deducted():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1", "baker")
    registry = _make_registry()
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry.begin_tick(ctx, ["A1"])
    # post_to_board costs 25
    registry.execute(pool.by_handle("A1"), "post_to_board", {"message": "test"}, ctx)
    assert store.get("A1", "economy")["coins"] == 475


def test_insufficient_coins():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1", "baker")
    store.set("A1", "economy", {"coins": 5})
    registry = _make_registry()
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry.begin_tick(ctx, ["A1"])
    result = registry.execute(pool.by_handle("A1"), "post_to_board", {"message": "test"}, ctx)
    assert "not enough coins" in result
