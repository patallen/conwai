from conwai.actions import ActionFeedback, ActionResult
from conwai.comm import BulletinBoard, MessageBus
from conwai.scheduler import TickNumber
from conwai.processes.types import (
    AgentHandle,
    Identity,
    Observations,
    PerceptFeedback,
    PerceptTick,
)
from conwai.world import World
from scenarios.workbench.components import AgentInfo
from scenarios.workbench.perception import WorkbenchPerceptionBuilder


def _setup():
    world = World()
    world.register(AgentInfo)
    world.register(ActionFeedback)

    board = BulletinBoard()
    bus = MessageBus()

    world.set_resource(TickNumber(1))
    world.set_resource(board)
    world.set_resource(bus)
    return world, board, bus


def _add(world, handle="A1", role="observer", personality="curious"):
    world.spawn(handle, overrides=[AgentInfo(role=role, personality=personality)])


def test_percept_includes_broadcast():
    world, board, bus = _setup()
    _add(world, "A1")
    bus.register("A1")
    board.post("WORLD", "hello everyone")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build("A1", world)
    assert "hello everyone" in percept.get(Observations).text
    assert percept.get(AgentHandle).value == "A1"
    assert percept.get(PerceptTick).value == 1


def test_percept_includes_dms():
    world, board, bus = _setup()
    _add(world, "A1")
    bus.register("A1")
    bus.send("Bob", "A1", "private info")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build("A1", world)
    assert "private info" in percept.get(Observations).text


def test_percept_includes_identity():
    world, board, bus = _setup()
    _add(world, "A1", role="analyst", personality="methodical, quiet")
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build("A1", world)
    assert "methodical" in percept.get(Identity).text
    assert "A1" in percept.get(Identity).text


def test_percept_includes_action_feedback():
    world, board, bus = _setup()
    _add(world, "A1")
    bus.register("A1")

    feedback = [ActionResult(action="broadcast", args={"content": "hi"}, result="sent")]
    world.set("A1", ActionFeedback(entries=feedback))

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build("A1", world)
    assert percept.get(PerceptFeedback).entries == feedback


def test_percept_includes_injected_stimulus():
    world, board, bus = _setup()
    _add(world, "A1")
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    builder.inject("A1", "A strange sound echoes from the north.")
    percept = builder.build("A1", world)
    assert "strange sound" in percept.get(Observations).text


def test_percept_no_activity():
    world, board, bus = _setup()
    _add(world, "A1")
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build("A1", world)
    text = percept.get(Observations).text
    assert isinstance(text, str)
    assert len(text) > 0
