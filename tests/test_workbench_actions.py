import tempfile
from pathlib import Path

from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickContext
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.storage import SQLiteStorage
from conwai.store import ComponentStore
from scenarios.workbench.actions import create_registry
from scenarios.workbench.components import AgentInfo, BrainState
from scenarios.workbench.perception import WorkbenchPerceptionBuilder


def _setup():
    store = ComponentStore()
    store.register(AgentInfo)
    store.register(BrainState)
    board = BulletinBoard()
    bus = MessageBus()
    events = EventLog(path=Path(":memory:"))
    perception = WorkbenchPerceptionBuilder()
    tmp = Path(tempfile.mkdtemp())
    storage = SQLiteStorage(tmp / "test.db")
    repo = AgentRepository(storage=storage)
    pool = AgentPool(repo, store, bus=bus)
    return store, board, bus, events, perception, pool


def _add(pool, store, handle):
    return pool.load_or_create(
        Agent(handle=handle),
        component_overrides=[AgentInfo(role="test", personality="test")],
    )


def _make_ctx(store, board, bus, events, perception, pool, tick=1):
    return TickContext(
        tick=tick, pool=pool, store=store,
        perception=perception, board=board, bus=bus, events=events,
    )


def test_broadcast_posts_to_board():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1")
    agent = pool.by_handle("A1")
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry = create_registry()

    result = registry.execute(agent, "broadcast", {"content": "hello world"}, ctx)
    assert "hello world" in result

    posts = board.read_new("OTHER")
    assert len(posts) == 1
    assert posts[0].content == "hello world"
    assert posts[0].handle == "A1"


def test_message_sends_dm():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1")
    _add(pool, store, "A2")
    agent = pool.by_handle("A1")
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry = create_registry()

    result = registry.execute(agent, "message", {"to": "A2", "content": "secret"}, ctx)
    assert "A2" in result

    dms = bus.receive("A2")
    assert len(dms) == 1
    assert dms[0].content == "secret"
    assert dms[0].from_handle == "A1"


def test_message_to_unknown_handle():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1")
    agent = pool.by_handle("A1")
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry = create_registry()

    result = registry.execute(agent, "message", {"to": "nobody", "content": "hi"}, ctx)
    assert "unknown" in result.lower() or "not delivered" in result.lower()
