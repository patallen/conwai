import tempfile
from pathlib import Path

from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.config import STARTING_BREAD
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository


def _make_pool(tmp_path: Path | None = None) -> tuple[AgentPool, AgentRepository, MessageBus]:
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp_path / "agents")
    bus = MessageBus()
    pool = AgentPool(repo, bus)
    return pool, repo, bus


def test_load_or_create_new():
    pool, repo, bus = _make_pool()
    agent = pool.load_or_create("A1", "baker", born_tick=0)
    assert agent.handle == "A1"
    assert agent.role == "baker"
    assert agent.alive is True
    assert agent.bread == STARTING_BREAD
    assert pool.by_handle("A1") is agent
    assert "A1" in bus._known_handles
    assert repo.exists("A1")


def test_load_or_create_existing():
    tmp = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp / "agents")
    agent = Agent(handle="A1", role="baker", coins=42, born_tick=0)
    repo.create(agent)

    bus = MessageBus()
    pool = AgentPool(repo, bus)
    loaded = pool.load_or_create("A1", "baker", born_tick=0)
    assert loaded.coins == 42
    assert loaded.alive is True
    assert "A1" in bus._known_handles


def test_load_or_create_dead_agent_not_registered_on_bus():
    tmp = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp / "agents")
    agent = Agent(handle="A1", role="baker", alive=False, born_tick=0)
    repo.create(agent)

    bus = MessageBus()
    pool = AgentPool(repo, bus)
    loaded = pool.load_or_create("A1", "baker", born_tick=0)
    assert loaded.alive is False
    assert "A1" not in bus._known_handles
    assert pool.by_handle("A1") is loaded


def test_spawn():
    pool, repo, bus = _make_pool()
    agent = pool.spawn("flour_forager", born_tick=5)
    assert agent.role == "flour_forager"
    assert agent.born_tick == 5
    assert agent.alive is True
    assert agent.bread == STARTING_BREAD
    assert pool.by_handle(agent.handle) is agent
    assert agent.handle in bus._known_handles
    assert repo.exists(agent.handle)


def test_kill():
    pool, repo, bus = _make_pool()
    pool.load_or_create("A1", "baker", born_tick=0)
    pool.kill("A1")
    agent = pool.by_handle("A1")
    assert agent.alive is False
    assert "A1" not in bus._known_handles


def test_queries():
    pool, _, _ = _make_pool()
    pool.load_or_create("A1", "baker", born_tick=0)
    pool.load_or_create("A2", "flour_forager", born_tick=0)
    pool.load_or_create("A3", "baker", born_tick=0)
    pool.kill("A2")

    assert len(pool.all()) == 3
    assert len(pool.alive()) == 2
    assert set(pool.handles()) == {"A1", "A3"}
    assert pool.by_handle("A2").alive is False
    assert pool.by_handle("NOPE") is None


def test_replace_dead():
    pool, _, _ = _make_pool()
    pool.load_or_create("A1", "baker", born_tick=0)
    pool.load_or_create("A2", "flour_forager", born_tick=0)
    pool.kill("A2")

    board = BulletinBoard()
    events = EventLog(path=Path(":memory:"))
    new_agents = pool.replace_dead(board, events, born_tick=10)

    assert len(new_agents) == 1
    assert new_agents[0].role == "flour_forager"
    assert new_agents[0].alive is True
    assert new_agents[0].born_tick == 10
    # Dead agent evicted
    assert pool.by_handle("A2") is None
    # Replacement is in pool
    assert pool.by_handle(new_agents[0].handle) is not None
    assert len(pool.alive()) == 2
    assert len(pool.all()) == 2


def test_save():
    tmp = Path(tempfile.mkdtemp())
    pool, repo, _ = _make_pool(tmp)
    agent = pool.load_or_create("A1", "baker", born_tick=0)
    agent.coins = 999
    pool.save("A1")

    # Reload from disk and verify
    loaded = repo.load("A1")
    assert loaded.coins == 999
