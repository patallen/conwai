from conwai.agent import Agent


def test_agent_is_identity():
    a = Agent(handle="A1")
    assert a.handle == "A1"
    assert a.alive is True
    assert a.born_tick == 0


def test_agent_no_game_state():
    a = Agent(handle="A1")
    assert not hasattr(a, "coins")
    assert not hasattr(a, "flour")
    assert not hasattr(a, "hunger")
    assert not hasattr(a, "messages")
    assert not hasattr(a, "_action_log")
    assert not hasattr(a, "soul")
    assert not hasattr(a, "role")
    assert not hasattr(a, "personality")
