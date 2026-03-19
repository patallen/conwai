from conwai.agent import Agent


def test_agent_is_identity():
    a = Agent(handle="A1", role="baker", personality="dry, blunt")
    assert a.handle == "A1"
    assert a.role == "baker"
    assert a.alive is True
    assert a.born_tick == 0
    assert a.personality == "dry, blunt"


def test_agent_no_game_state():
    a = Agent(handle="A1", role="baker")
    assert not hasattr(a, "coins")
    assert not hasattr(a, "flour")
    assert not hasattr(a, "hunger")
    assert not hasattr(a, "messages")
    assert not hasattr(a, "_action_log")
    assert not hasattr(a, "soul")
