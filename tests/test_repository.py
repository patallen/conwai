import pytest

from conwai.agent import Agent
from conwai.repository import AgentRepository
from conwai.config import ENERGY_MAX, SCRATCHPAD_MAX


@pytest.fixture
def repo(tmp_path):
    return AgentRepository(base_dir=tmp_path)


@pytest.fixture
def agent():
    return Agent(handle="test1", personality="curious, blunt")


class TestCreate:
    def test_creates_directory(self, repo, agent):
        repo.create(agent)
        assert (repo._base_dir / "test1").is_dir()

    def test_persists_personality(self, repo, agent):
        repo.create(agent)
        assert (
            repo._base_dir / "test1" / "personality.md"
        ).read_text() == "curious, blunt"

    def test_persists_energy(self, repo, agent):
        repo.create(agent)
        assert float((repo._base_dir / "test1" / "energy").read_text()) == ENERGY_MAX

    def test_persists_alive(self, repo, agent):
        repo.create(agent)
        assert (repo._base_dir / "test1" / "alive").read_text() == "true"

    def test_raises_on_duplicate(self, repo, agent):
        repo.create(agent)
        with pytest.raises(ValueError, match="already exists"):
            repo.create(agent)

    def test_returns_agent(self, repo, agent):
        result = repo.create(agent)
        assert result is agent


class TestSave:
    def test_persists_energy(self, repo, agent):
        agent.energy = 42.5
        repo.save(agent)
        assert float((repo._base_dir / "test1" / "energy").read_text()) == 42.5

    def test_persists_alive_false(self, repo, agent):
        agent.alive = False
        repo.save(agent)
        assert (repo._base_dir / "test1" / "alive").read_text() == "false"

    def test_persists_soul(self, repo, agent):
        agent.soul = "I am a thinker"
        repo.save(agent)
        assert (repo._base_dir / "test1" / "soul.md").read_text() == "I am a thinker"

    def test_persists_scratchpad(self, repo, agent):
        agent.scratchpad = "tick 1: nothing happened"
        repo.save(agent)
        assert (
            repo._base_dir / "test1" / "scratchpad.md"
        ).read_text() == "tick 1: nothing happened"

    def test_truncates_scratchpad(self, repo, agent):
        agent.scratchpad = "x" * (SCRATCHPAD_MAX + 500)
        repo.save(agent)
        saved = (repo._base_dir / "test1" / "scratchpad.md").read_text()
        assert len(saved) == SCRATCHPAD_MAX

    def test_persists_context(self, repo, agent):
        agent.system_prompt = "you are test1"
        agent.messages = [{"role": "user", "content": "hello"}]
        repo.save(agent)
        import json

        ctx = json.loads((repo._base_dir / "test1" / "context.json").read_text())
        assert ctx["system"] == "you are test1"
        assert len(ctx["messages"]) == 1

    def test_overwrites_existing(self, repo, agent):
        agent.energy = 100
        repo.save(agent)
        agent.energy = 200
        repo.save(agent)
        assert float((repo._base_dir / "test1" / "energy").read_text()) == 200


class TestLoad:
    def test_returns_none_for_missing(self, repo):
        assert repo.load("nonexistent") is None

    def test_roundtrip(self, repo, agent):
        agent.energy = 777
        agent.soul = "test soul"
        agent.scratchpad = "test scratch"
        agent.system_prompt = "sys prompt"
        agent.messages = [{"role": "user", "content": "hi"}]
        repo.save(agent)

        loaded = repo.load("test1")
        assert loaded.handle == "test1"
        assert loaded.energy == 777
        assert loaded.alive is True
        assert loaded.soul == "test soul"
        assert loaded.scratchpad == "test scratch"
        assert loaded.personality == "curious, blunt"
        assert loaded.system_prompt == "sys prompt"
        assert len(loaded.messages) == 1

    def test_roundtrip_dead_agent(self, repo, agent):
        agent.alive = False
        agent.energy = 0
        repo.save(agent)

        loaded = repo.load("test1")
        assert loaded.alive is False
        assert loaded.energy == 0

    def test_load_without_context_file(self, repo, agent):
        repo.save(agent)
        (repo._base_dir / "test1" / "context.json").unlink()

        loaded = repo.load("test1")
        assert loaded.system_prompt == ""
        assert loaded.messages == []

    def test_load_defaults_energy_if_missing(self, repo):
        d = repo._base_dir / "test2"
        d.mkdir(parents=True)
        (d / "personality.md").write_text("dry, warm")

        loaded = repo.load("test2")
        assert loaded.energy == ENERGY_MAX


class TestExists:
    def test_false_for_missing(self, repo):
        assert repo.exists("nope") is False

    def test_true_after_create(self, repo, agent):
        repo.create(agent)
        assert repo.exists("test1") is True
