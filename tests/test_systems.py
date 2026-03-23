import asyncio

from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickNumber
from conwai.event_bus import EventBus
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.world import World
from scenarios.bread_economy.components import (
    AgentInfo,
    AgentMemory,
    Economy,
    Hunger,
    Inventory,
)
from scenarios.bread_economy.config import get_config
from scenarios.bread_economy.perception import make_bread_perception
from scenarios.bread_economy.systems import (
    ConsumptionSystem,
    DecaySystem,
    SpoilageSystem,
    TaxSystem,
)


def _setup(tick=1):
    bus = EventBus()
    world = World(bus=bus)
    world.register(Economy)
    world.register(Inventory)
    world.register(Hunger)
    world.register(AgentInfo)
    world.register(AgentMemory)

    world.set_resource(TickNumber(tick))
    board = BulletinBoard()
    msg_bus = MessageBus()
    events = EventLog()
    perception = make_bread_perception()
    world.set_resource(board)
    world.set_resource(msg_bus)
    world.set_resource(events)
    world.set_resource(perception)
    return world


def _add_agent(world, handle="A1", role="baker"):
    world.spawn(handle, overrides=[AgentInfo(role=role, personality="")])


def test_decay():
    world = _setup(tick=1)
    _add_agent(world)
    asyncio.run(DecaySystem().run(world))
    h = world.get("A1", Hunger)
    assert h.hunger == 100 - get_config().hunger_decay_per_tick
    assert h.thirst == 100 - get_config().thirst_decay_per_tick


def test_tax():
    world = _setup(tick=1)
    _add_agent(world)
    asyncio.run(TaxSystem(interval=1).run(world))
    eco = world.get("A1", Economy)
    assert eco.coins < 500


def test_tax_skips_off_interval():
    world = _setup(tick=5)
    _add_agent(world)
    asyncio.run(TaxSystem(interval=24).run(world))
    eco = world.get("A1", Economy)
    assert eco.coins == 500


def test_spoilage():
    world = _setup(tick=get_config().bread_spoil_interval)
    _add_agent(world)
    world.set("A1", Inventory(flour=0, water=0, bread=5))
    asyncio.run(SpoilageSystem().run(world))
    inv = world.get("A1", Inventory)
    assert inv.bread < 5


def test_consumption_eats_when_hungry():
    world = _setup(tick=1)
    _add_agent(world)
    world.set("A1", Hunger(hunger=20, thirst=100))
    world.set("A1", Inventory(flour=0, water=0, bread=3))
    asyncio.run(ConsumptionSystem().run(world))
    h = world.get("A1", Hunger)
    assert h.hunger > 20
    inv = world.get("A1", Inventory)
    assert inv.bread < 3


def test_consumption_drinks_when_thirsty():
    world = _setup(tick=1)
    _add_agent(world)
    world.set("A1", Hunger(hunger=100, thirst=20))
    world.set("A1", Inventory(flour=0, water=3, bread=0))
    asyncio.run(ConsumptionSystem().run(world))
    h = world.get("A1", Hunger)
    assert h.thirst > 20
    inv = world.get("A1", Inventory)
    assert inv.water < 3
