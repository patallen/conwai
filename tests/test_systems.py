import asyncio

import scenarios.bread_economy.config as config
from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickContext
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.store import ComponentStore
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
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    store.register_component("hunger", {"hunger": 100, "thirst": 100})
    store.register_component("agent_info", {"role": "", "personality": ""})
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
    store.init_agent(handle, overrides={"agent_info": {"role": role, "personality": ""}})
    pool._agents[handle] = agent
    return agent


def test_decay():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=1)
    asyncio.run(DecaySystem().run(ctx))
    h = store.get("A1", "hunger")
    assert h["hunger"] == 100 - config.HUNGER_DECAY_PER_TICK
    assert h["thirst"] == 100 - config.THIRST_DECAY_PER_TICK


def test_tax():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=1)
    asyncio.run(TaxSystem(interval=1).run(ctx))
    eco = store.get("A1", "economy")
    assert eco["coins"] < 500


def test_tax_skips_off_interval():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=5)
    asyncio.run(TaxSystem(interval=24).run(ctx))
    eco = store.get("A1", "economy")
    assert eco["coins"] == 500


def test_spoilage():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    store.set("A1", "inventory", {"flour": 0, "water": 0, "bread": 5})
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=config.BREAD_SPOIL_INTERVAL)
    asyncio.run(SpoilageSystem().run(ctx))
    inv = store.get("A1", "inventory")
    assert inv["bread"] < 5


def test_consumption_eats_when_hungry():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    store.set("A1", "hunger", {"hunger": 20, "thirst": 100})
    store.set("A1", "inventory", {"flour": 0, "water": 0, "bread": 3})
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=1)
    asyncio.run(ConsumptionSystem().run(ctx))
    h = store.get("A1", "hunger")
    assert h["hunger"] > 20
    inv = store.get("A1", "inventory")
    assert inv["bread"] < 3


def test_consumption_drinks_when_thirsty():
    store, perception, board, bus, events, pool = _setup()
    _add_agent(pool, store)
    store.set("A1", "hunger", {"hunger": 100, "thirst": 20})
    store.set("A1", "inventory", {"flour": 0, "water": 3, "bread": 0})
    ctx = _make_ctx(pool, store, perception, board, bus, events, tick=1)
    asyncio.run(ConsumptionSystem().run(ctx))
    h = store.get("A1", "hunger")
    assert h["thirst"] > 20
    inv = store.get("A1", "inventory")
    assert inv["water"] < 3
