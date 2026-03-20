import tempfile
from pathlib import Path

from conwai.agent import Agent
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.store import ComponentStore


def _make_pool(tmp_path=None):
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp_path / "agents")
    bus = MessageBus()
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    pool = AgentPool(repo, store, bus=bus)
    return pool, store


def test_load_or_create_new():
    pool, store = _make_pool()
    agent = pool.load_or_create(Agent(handle="A1"))
    assert agent.handle == "A1"
    assert store.has("A1", "economy")


def test_add():
    pool, store = _make_pool()
    agent = pool.add(Agent(handle="A1", born_tick=5))
    assert agent.alive is True
    assert store.has(agent.handle, "economy")


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
    repo = AgentRepository(base_dir=tmp_path / "agents")
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    pool = AgentPool(repo, store)
    agent = pool.load_or_create(Agent(handle="A1"))
    assert agent.handle == "A1"
    pool.kill("A1")
    assert pool.by_handle("A1").alive is False
