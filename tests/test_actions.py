from pathlib import Path

from conwai.comm import BulletinBoard, MessageBus
from conwai.events import EventBus, EventLog
from conwai.scheduler import TickNumber
from conwai.world import World
from scenarios.bread_economy.actions import create_registry
from scenarios.bread_economy.components import (
    AgentInfo,
    AgentMemory,
    Economy,
    Hunger,
    Inventory,
)
from scenarios.bread_economy.perception import make_bread_perception


def _setup():
    bus = EventBus()
    world = World(bus=bus)
    world.register(Economy)
    world.register(Inventory)
    world.register(Hunger)
    world.register(AgentMemory)
    world.register(AgentInfo)

    board = BulletinBoard()
    msg_bus = MessageBus()
    events = EventLog(path=Path(":memory:"))
    events.subscribe_to(bus)
    perception = make_bread_perception()
    registry = create_registry()

    world.set_resource(TickNumber(1))
    world.set_resource(board)
    world.set_resource(msg_bus)
    world.set_resource(events)
    world.set_resource(perception)
    world.set_resource(registry)
    return world, board, msg_bus, registry


def _add(world, handle, role):
    world.spawn(handle, overrides=[AgentInfo(role=role, personality="test")])
    world.get_resource(MessageBus).register(handle)


def test_pay_transfers_coins():
    world, board, bus, registry = _setup()
    _add(world, "A1", "baker")
    _add(world, "A2", "baker")
    registry.begin_tick(world, ["A1", "A2"])
    registry.execute("A1", "pay", {"to": "A2", "amount": 100}, world)
    assert world.get("A1", Economy).coins == 400
    assert world.get("A2", Economy).coins == 600


def test_post_to_board():
    world, board, bus, registry = _setup()
    _add(world, "A1", "baker")
    registry.begin_tick(world, ["A1"])
    registry.execute("A1", "post_to_board", {"message": "hello"}, world)
    posts = board.read_new("OTHER")
    assert any(p.content == "hello" for p in posts)


def test_send_message():
    world, board, bus, registry = _setup()
    _add(world, "A1", "baker")
    _add(world, "A2", "baker")
    registry.begin_tick(world, ["A1", "A2"])
    registry.execute("A1", "send_message", {"to": "A2", "message": "hi"}, world)
    dms = bus.receive("A2")
    assert len(dms) == 1
    assert dms[0].content == "hi"


def test_give_updates_both_stores():
    world, board, bus, registry = _setup()
    _add(world, "A1", "flour_forager")
    _add(world, "A2", "baker")
    world.set("A1", Inventory(flour=10, water=0, bread=0))
    registry.begin_tick(world, ["A1", "A2"])
    registry.execute(
        "A1", "give", {"to": "A2", "resource": "flour", "amount": 5}, world
    )
    assert world.get("A1", Inventory).flour == 5
    assert world.get("A2", Inventory).flour == 5


def test_inspect():
    world, board, bus, registry = _setup()
    _add(world, "A1", "baker")
    _add(world, "A2", "flour_forager")
    world.set("A2", AgentMemory(soul="reliable trader"))
    registry.begin_tick(world, ["A1", "A2"])
    result = registry.execute("A1", "inspect", {"handle": "A2"}, world)
    assert "A2" in result
    assert "reliable trader" in result


def test_update_soul():
    world, board, bus, registry = _setup()
    _add(world, "A1", "baker")
    registry.begin_tick(world, ["A1"])
    registry.execute("A1", "update_soul", {"content": "I am wise"}, world)
    mem = world.get("A1", AgentMemory)
    assert mem.soul == "I am wise"


def test_update_journal():
    world, board, bus, registry = _setup()
    _add(world, "A1", "baker")
    registry.begin_tick(world, ["A1"])
    registry.execute("A1", "update_journal", {"content": "day 1 notes"}, world)
    mem = world.get("A1", AgentMemory)
    assert mem.memory == "day 1 notes"


def test_cost_deducted():
    world, board, bus, registry = _setup()
    _add(world, "A1", "baker")
    registry.begin_tick(world, ["A1"])
    # post_to_board costs 25
    registry.execute("A1", "post_to_board", {"message": "test"}, world)
    assert world.get("A1", Economy).coins == 475


def test_insufficient_coins():
    world, board, bus, registry = _setup()
    _add(world, "A1", "baker")
    world.set("A1", Economy(coins=5))
    registry.begin_tick(world, ["A1"])
    result = registry.execute("A1", "post_to_board", {"message": "test"}, world)
    assert "not enough coins" in result
