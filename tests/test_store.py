import json
import pytest
from pathlib import Path
from conwai.store import ComponentStore


class TestComponentStore:
    def test_register_and_get_defaults(self):
        store = ComponentStore()
        store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
        store.init_agent("A1")
        assert store.get("A1", "inventory") == {"flour": 0, "water": 0, "bread": 0}

    def test_set_and_get(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        store.set("A1", "economy", {"coins": 300})
        assert store.get("A1", "economy") == {"coins": 300}

    def test_get_unknown_agent_raises(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        with pytest.raises(KeyError):
            store.get("NOPE", "economy")

    def test_get_unknown_component_raises(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        with pytest.raises(KeyError):
            store.get("A1", "nope")

    def test_has(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        assert store.has("A1", "economy") is True
        assert store.has("A1", "nope") is False
        assert store.has("NOPE", "economy") is False

    def test_remove_agent(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        store.remove("A1")
        assert store.has("A1", "economy") is False

    def test_handles(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        store.init_agent("A2")
        assert set(store.handles()) == {"A1", "A2"}

    def test_save_and_load(self, tmp_path):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.register_component("inventory", {"flour": 0})
        store.init_agent("A1")
        store.set("A1", "economy", {"coins": 123})
        store.save("A1", tmp_path / "A1")

        store2 = ComponentStore()
        store2.register_component("economy", {"coins": 500})
        store2.register_component("inventory", {"flour": 0})
        store2.load("A1", tmp_path / "A1")
        assert store2.get("A1", "economy") == {"coins": 123}
        assert store2.get("A1", "inventory") == {"flour": 0}

    def test_init_agent_with_overrides(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1", overrides={"economy": {"coins": 100}})
        assert store.get("A1", "economy") == {"coins": 100}
