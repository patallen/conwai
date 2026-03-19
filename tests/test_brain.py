import asyncio
from conwai.agent import Agent
from conwai.brain import Brain, Decision


class FakeBrain:
    """Minimal Brain implementation for protocol testing."""
    def __init__(self, decisions=None):
        self._decisions = decisions or []
        self.observations = []

    async def decide(self, agent, perception, identity="", tick=0):
        return self._decisions

    def observe(self, decision, result):
        self.observations.append((decision, result))


def test_brain_protocol():
    brain = FakeBrain([Decision("forage", {})])
    assert isinstance(brain, Brain)


def test_decide_returns_decisions():
    brain = FakeBrain([Decision("forage", {}), Decision("post_to_board", {"message": "hi"})])
    agent = Agent(handle="A1", role="baker")
    decisions = asyncio.run(brain.decide(agent, "tick 1"))
    assert len(decisions) == 2
    assert decisions[0].action == "forage"


def test_observe_records_results():
    brain = FakeBrain()
    d = Decision("forage", {})
    brain.observe(d, "foraged 3 flour")
    assert brain.observations == [(d, "foraged 3 flour")]
