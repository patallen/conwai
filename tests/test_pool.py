import tempfile
from pathlib import Path

from conwai.agent import Agent
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.storage import SQLiteStorage
from conwai.store import ComponentStore
from scenarios.bread_economy.components import Economy, Inventory


def _make_pool(tmp_path=None):
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    storage = SQLiteStorage(tmp_path / "test.db")
    repo = AgentRepository(storage=storage)
    bus = MessageBus()
    store = ComponentStore(storage=storage)
    store.register(Economy)
    store.register(Inventory)
    pool = AgentPool(repo, store, bus=bus)
    return pool, store


def test_load_or_create_new():
    pool, store = _make_pool()
    agent = pool.load_or_create(Agent(handle="A1"))
    assert agent.handle == "A1"
    assert store.has("A1", Economy)


def test_add():
    pool, store = _make_pool()
    agent = pool.add(Agent(handle="A1", born_tick=5))
    assert agent.alive is True
    assert store.has(agent.handle, Economy)


def test_kill():
    pool, store = _make_pool()
    pool.load_or_create(Agent(handle="A1"))
    pool.kill("A1")
    assert pool.by_handle("A1").alive is False


def test_queries():
    pool, _ = _make_pool()
    pool.load_or_create(Agent(handle="A1"))
    pool.load_or_create(Agent(handle="A2"))
    pool.kill("A2")
    assert len(pool.alive()) == 1
    assert pool.by_handle("A2").alive is False


def test_pool_without_bus():
    """Pool works when bus is None."""
    tmp_path = Path(tempfile.mkdtemp())
    storage = SQLiteStorage(tmp_path / "test.db")
    repo = AgentRepository(storage=storage)
    store = ComponentStore(storage=storage)
    store.register(Economy)
    pool = AgentPool(repo, store)
    agent = pool.load_or_create(Agent(handle="A1"))
    assert agent.handle == "A1"
    pool.kill("A1")
    assert pool.by_handle("A1").alive is False
