import pytest

from conwai.agent import Agent
from conwai.repository import AgentRepository
from conwai.store import ComponentStore


@pytest.fixture
def repo(tmp_path):
    return AgentRepository(base_dir=tmp_path)


class TestRepository:
    def test_save_and_load_identity(self, repo):
        agent = Agent(handle="A1")
        repo.save_agent(agent)
        loaded = repo.load_agent("A1")
        assert loaded.handle == "A1"
        assert loaded.alive is True

    def test_save_and_load_with_store(self, repo):
        agent = Agent(handle="A1")
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        store.set("A1", "economy", {"coins": 123})

        repo.save_agent(agent)
        repo.save_components("A1", store)

        store2 = ComponentStore()
        store2.register_component("economy", {"coins": 500})
        repo.load_components("A1", store2)
        assert store2.get("A1", "economy") == {"coins": 123}

    def test_exists(self, repo):
        assert repo.exists("A1") is False
        repo.save_agent(Agent(handle="A1"))
        assert repo.exists("A1") is True

    def test_load_missing_returns_none(self, repo):
        assert repo.load_agent("NOPE") is None

    def test_load_strips_legacy_fields(self, repo, tmp_path):
        """Loading an identity.json with old role/personality fields still works."""
        import json
        d = tmp_path / "A1"
        d.mkdir()
        (d / "identity.json").write_text(json.dumps({
            "handle": "A1", "role": "baker", "personality": "dry",
            "alive": True, "born_tick": 0, "soul": "old_field",
        }))
        loaded = repo.load_agent("A1")
        assert loaded.handle == "A1"
        assert loaded.alive is True
        assert not hasattr(loaded, "role")
