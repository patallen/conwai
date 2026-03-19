import conwai.config as config
from conwai.agent import Agent
from conwai.store import ComponentStore
from conwai.perception import Perception
from conwai.systems.decay import DecaySystem
from conwai.systems.tax import TaxSystem
from conwai.systems.spoilage import SpoilageSystem
from conwai.systems.consumption import ConsumptionSystem


def _setup():
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    store.register_component("hunger", {"hunger": 100, "thirst": 100})
    perception = Perception()
    return store, perception


def test_decay():
    store, perception = _setup()
    store.init_agent("A1")
    agents = [Agent(handle="A1", role="baker")]
    DecaySystem().tick(agents, store, perception)
    h = store.get("A1", "hunger")
    assert h["hunger"] == 100 - config.HUNGER_DECAY_PER_TICK
    assert h["thirst"] == 100 - config.THIRST_DECAY_PER_TICK


def test_tax():
    store, perception = _setup()
    store.init_agent("A1")
    agents = [Agent(handle="A1", role="baker")]
    TaxSystem(interval=1).tick(agents, store, perception, tick=1)
    eco = store.get("A1", "economy")
    assert eco["coins"] < 500


def test_tax_skips_off_interval():
    store, perception = _setup()
    store.init_agent("A1")
    agents = [Agent(handle="A1", role="baker")]
    TaxSystem(interval=24).tick(agents, store, perception, tick=5)
    eco = store.get("A1", "economy")
    assert eco["coins"] == 500


def test_spoilage():
    store, perception = _setup()
    store.init_agent("A1")
    store.set("A1", "inventory", {"flour": 0, "water": 0, "bread": 5})
    agents = [Agent(handle="A1", role="baker")]
    # Must be on the right interval tick
    import conwai.config as config
    SpoilageSystem().tick(agents, store, perception, tick=config.BREAD_SPOIL_INTERVAL)
    inv = store.get("A1", "inventory")
    assert inv["bread"] < 5


def test_consumption_eats_when_hungry():
    store, perception = _setup()
    store.init_agent("A1")
    store.set("A1", "hunger", {"hunger": 20, "thirst": 100})
    store.set("A1", "inventory", {"flour": 0, "water": 0, "bread": 3})
    agents = [Agent(handle="A1", role="baker")]
    ConsumptionSystem().tick(agents, store, perception)
    h = store.get("A1", "hunger")
    assert h["hunger"] > 20
    inv = store.get("A1", "inventory")
    assert inv["bread"] < 3


def test_consumption_drinks_when_thirsty():
    store, perception = _setup()
    store.init_agent("A1")
    store.set("A1", "hunger", {"hunger": 100, "thirst": 20})
    store.set("A1", "inventory", {"flour": 0, "water": 3, "bread": 0})
    agents = [Agent(handle="A1", role="baker")]
    ConsumptionSystem().tick(agents, store, perception)
    h = store.get("A1", "hunger")
    assert h["thirst"] > 20
    inv = store.get("A1", "inventory")
    assert inv["water"] < 3
