import asyncio

from conwai.cognition import Brain, Decision


class FakeBrain:
    """Minimal Brain implementation for protocol testing."""

    def __init__(self, decisions=None):
        self._decisions = decisions or []

    async def think(self, percept):
        return self._decisions


def test_brain_protocol():
    brain = FakeBrain([Decision("forage", {})])
    assert isinstance(brain, Brain)


def test_think_returns_decisions():
    brain = FakeBrain([Decision("forage", {}), Decision("post_to_board", {"message": "hi"})])
    decisions = asyncio.run(brain.think(None))
    assert len(decisions) == 2
    assert decisions[0].action == "forage"
