from pathlib import Path

from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickNumber
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.world import World
from scenarios.workbench.actions import create_registry
from scenarios.workbench.components import AgentInfo, BrainState


def _setup():
    world = World()
    world.register(AgentInfo)
    world.register(BrainState)

    board = BulletinBoard()
    bus = MessageBus()
    events = EventLog(path=Path(":memory:"))

    world.set_resource(TickNumber(1))
    world.set_resource(board)
    world.set_resource(bus)
    world.set_resource(events)
    return world, board, bus


def _add(world, handle):
    world.spawn(handle, overrides=[AgentInfo(role="test", personality="test")])
    world.get_resource(MessageBus).register(handle)


def test_broadcast_posts_to_board():
    world, board, bus = _setup()
    _add(world, "A1")
    registry = create_registry()

    result = registry.execute("A1", "broadcast", {"content": "hello world"}, world)
    assert "hello world" in result

    posts = board.read_new("OTHER")
    assert len(posts) == 1
    assert posts[0].content == "hello world"
    assert posts[0].handle == "A1"


def test_message_sends_dm():
    world, board, bus = _setup()
    _add(world, "A1")
    _add(world, "A2")
    registry = create_registry()

    result = registry.execute("A1", "message", {"to": "A2", "content": "secret"}, world)
    assert "A2" in result

    dms = bus.receive("A2")
    assert len(dms) == 1
    assert dms[0].content == "secret"
    assert dms[0].from_handle == "A1"


def test_message_to_unknown_handle():
    world, board, bus = _setup()
    _add(world, "A1")
    registry = create_registry()

    result = registry.execute("A1", "message", {"to": "nobody", "content": "hi"}, world)
    assert "unknown" in result.lower() or "not delivered" in result.lower()
