import pytest

from conwai.agent import Agent
from conwai.repository import AgentRepository
from conwai.storage import SQLiteStorage
from conwai.store import ComponentStore
from scenarios.bread_economy.components import Economy


@pytest.fixture
def repo(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    return AgentRepository(storage=storage)


class TestRepository:
    def test_save_and_load_identity(self, repo):
        agent = Agent(handle="A1")
        repo.save_agent(agent)
        loaded = repo.load_agent("A1")
        assert loaded.handle == "A1"
        assert loaded.alive is True

    def test_save_and_load_with_store(self, repo, tmp_path):
        storage = SQLiteStorage(tmp_path / "test2.db")
        store = ComponentStore(storage=storage)
        store.register(Economy)
        store.init_agent("A1")
        store.set("A1", Economy(coins=123))

        # Verify the write-through persisted it
        result = storage.load_component("A1", "economy")
        assert result == {"coins": 123}

    def test_exists(self, repo):
        assert repo.exists("A1") is False
        repo.save_agent(Agent(handle="A1"))
        assert repo.exists("A1") is True

    def test_load_missing_returns_none(self, repo):
        assert repo.load_agent("NOPE") is None

    def test_load_strips_legacy_fields(self, tmp_path):
        """Loading an _identity with old role/personality fields still works."""
        storage = SQLiteStorage(tmp_path / "legacy.db")
        storage.save_component("A1", "_identity", {
            "handle": "A1", "role": "baker", "personality": "dry",
            "alive": True, "born_tick": 0, "soul": "old_field",
        })
        repo = AgentRepository(storage=storage)
        loaded = repo.load_agent("A1")
        assert loaded.handle == "A1"
        assert loaded.alive is True
        assert not hasattr(loaded, "role")
