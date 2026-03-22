from dataclasses import dataclass

import pytest

from conwai.component import Component
from conwai.store import ComponentStore


@dataclass
class Inventory(Component):
    flour: int = 0
    water: int = 0
    bread: int = 0


@dataclass
class Economy(Component):
    coins: int = 500


@dataclass
class Unused(Component):
    x: int = 0


class TestComponentStore:
    def test_register_and_get_defaults(self):
        store = ComponentStore()
        store.register(Inventory)
        store.init_agent("A1")
        assert store.get("A1", Inventory) == Inventory(flour=0, water=0, bread=0)

    def test_set_and_get(self):
        store = ComponentStore()
        store.register(Economy)
        store.init_agent("A1")
        store.set("A1", Economy(coins=300))
        assert store.get("A1", Economy).coins == 300

    def test_get_unknown_agent_raises(self):
        store = ComponentStore()
        store.register(Economy)
        with pytest.raises(KeyError):
            store.get("NOPE", Economy)

    def test_get_unknown_component_raises(self):
        store = ComponentStore()
        store.register(Economy)
        store.init_agent("A1")
        with pytest.raises(KeyError):
            store.get("A1", Unused)

    def test_has(self):
        store = ComponentStore()
        store.register(Economy)
        store.init_agent("A1")
        assert store.has("A1", Economy) is True
        assert store.has("A1", Unused) is False
        assert store.has("NOPE", Economy) is False

    def test_remove_agent(self):
        store = ComponentStore()
        store.register(Economy)
        store.init_agent("A1")
        store.remove("A1")
        assert store.has("A1", Economy) is False

    def test_handles(self):
        store = ComponentStore()
        store.register(Economy)
        store.init_agent("A1")
        store.init_agent("A2")
        assert set(store.handles()) == {"A1", "A2"}

    def test_init_agent_with_overrides(self):
        store = ComponentStore()
        store.register(Economy)
        store.init_agent("A1", overrides=[Economy(coins=100)])
        assert store.get("A1", Economy) == Economy(coins=100)
