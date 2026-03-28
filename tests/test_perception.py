from conwai.comm import BulletinBoard, MessageBus
from conwai.processes.types import Observations
from conwai.scheduler import TickNumber
from conwai.world import World
from scenarios.bread_economy.components import (
    AgentInfo,
    AgentMemory,
    Economy,
    Hunger,
    Inventory,
)
from scenarios.bread_economy.perception import make_bread_perception


def _setup(tick=1):
    world = World()
    world.register(Economy)
    world.register(Inventory)
    world.register(Hunger)
    world.register(AgentMemory)
    world.register(AgentInfo)

    board = BulletinBoard()
    bus = MessageBus()
    perception = make_bread_perception()
    world.set_resource(TickNumber(tick))
    world.set_resource(board)
    world.set_resource(bus)
    world.set_resource(perception)
    return world, board, bus, perception


def _add(world, handle="A1", role="baker", personality="test"):
    world.spawn(handle, overrides=[AgentInfo(role=role, personality=personality)])


def test_perception_includes_board_posts():
    world, board, bus, perception = _setup()
    _add(world, "A1", "baker")
    bus.register("A1")
    board.post("A2", "hello world")

    percept = perception.build("A1", world)
    text = percept.get(Observations).text
    assert "hello world" in text
    assert "@A2" in text


def test_perception_includes_dms():
    world, board, bus, perception = _setup()
    _add(world, "A1", "baker")
    bus.register("A1")
    bus.send("A2", "A1", "secret message")

    percept = perception.build("A1", world)
    text = percept.get(Observations).text
    assert "secret message" in text


def test_perception_includes_hunger_warning():
    world, board, bus, perception = _setup()
    _add(world, "A1", "baker")
    bus.register("A1")
    world.set("A1", Hunger(hunger=20, thirst=100))

    percept = perception.build("A1", world)
    text = percept.get(Observations).text
    assert "hungry" in text.lower() or "hunger" in text.lower()


def test_perception_includes_state():
    world, board, bus, perception = _setup()
    _add(world, "A1", "baker")
    bus.register("A1")
    world.set("A1", Economy(coins=42))

    percept = perception.build("A1", world)
    text = percept.get(Observations).text
    assert "42" in text


def test_perception_includes_notifications():
    world, board, bus, perception = _setup()
    _add(world, "A1", "baker")
    bus.register("A1")

    perception.notify("A1", "coins -5 (daily tax)")
    percept = perception.build("A1", world)
    text = percept.get(Observations).text
    assert "daily tax" in text
