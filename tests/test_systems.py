import asyncio

from scenarios.bread_economy.config import get_config
from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickContext
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.store import ComponentStore
from scenarios.bread_economy.components import (
    AgentInfo,
    Economy,
    Hunger,
    Inventory,
)
from scenarios.bread_economy.perception import make_bread_perception
from scenarios.bread_economy.systems import (
    ConsumptionSystem,
    DecaySystem,
    SpoilageSystem,
    TaxSystem,
)


class _FakeRepo:
    def exists(self, handle): return False
    def save_agent(self, agent): pass
    def save_components(self, handle, store): pass
    def load_agent(self, handle): pass
    def load_components(self, handle, store): pass


def _setup():
    store = ComponentStore()
    store.register(Economy)
    store.register(Inventory)
    store.register(Hunger)
    store.register(AgentInfo)
    perception = make_bread_perception()
    board = BulletinBoard()
    bus = MessageBus()
    events = EventLog()
    repo = _FakeRepo()
    pool = AgentPool(repo, store, bus=bus)
    return store, perception, board, bus, events, pool


def _make_ctx(pool, store, perception, board, bus, events, tick=1):
    return TickContext(
        tick=tick, pool=pool, store=store,
        perception=perception, board=board, bus=bus, events=events,
    )


def _add_agent(pool, store, handle="A1", role="baker"):
    agent = Agent(handle=handle)
    store.init_agent(handle, overrides=[AgentInfo(role=role, personality="")])
    pool._agents[handle] = agent
    return agent


def test_decay():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=1)
    asyncio.run(DecaySystem().run(ctx))
    h = store.get("A1", Hunger)
    assert h.hunger == 100 - get_config().hunger_decay_per_tick
    assert h.thirst == 100 - get_config().thirst_decay_per_tick


def test_tax():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=1)
    asyncio.run(TaxSystem(interval=1).run(ctx))
    eco = store.get("A1", Economy)
    assert eco.coins < 500


def test_tax_skips_off_interval():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=5)
    asyncio.run(TaxSystem(interval=24).run(ctx))
    eco = store.get("A1", Economy)
    assert eco.coins == 500


def test_spoilage():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    store.set("A1", Inventory(flour=0, water=0, bread=5))
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=get_config().bread_spoil_interval)
    asyncio.run(SpoilageSystem().run(ctx))
    inv = store.get("A1", Inventory)
    assert inv.bread < 5


def test_consumption_eats_when_hungry():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    store.set("A1", Hunger(hunger=20, thirst=100))
    store.set("A1", Inventory(flour=0, water=0, bread=3))
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=1)
    asyncio.run(ConsumptionSystem().run(ctx))
    h = store.get("A1", Hunger)
    assert h.hunger > 20
    inv = store.get("A1", Inventory)
    assert inv.bread < 3


def test_consumption_drinks_when_thirsty():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    store.set("A1", Hunger(hunger=100, thirst=20))
    store.set("A1", Inventory(flour=0, water=3, bread=0))
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=1)
    asyncio.run(ConsumptionSystem().run(ctx))
    h = store.get("A1", Hunger)
    assert h.thirst > 20
    inv = store.get("A1", Inventory)
    assert inv.water < 3
