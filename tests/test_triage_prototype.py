"""Prototype: two agents with triage-based activation.

The brain doesn't return actions directly — it returns a triage result:
  ignore     → done, no cost
  react      → execute decisions immediately
  deliberate → schedule a full think at higher cost

The runner interprets the result and schedules follow-up work.
"""

import asyncio
from dataclasses import dataclass, field
from enum import Enum, auto

from conwai.event_bus import Event, EventBus
from conwai.scheduler import Scheduler


# --- Triage result ---

class Mode(Enum):
    IGNORE = auto()
    REACT = auto()
    DELIBERATE = auto()


@dataclass
class TriageResult:
    mode: Mode
    actions: list[dict] = field(default_factory=list)


# --- Fake world state ---

@dataclass
class World:
    board: list[str] = field(default_factory=list)
    inbox: dict[str, list[str]] = field(default_factory=lambda: {"alice": [], "bob": []})


# --- Events ---

@dataclass
class ActionDone(Event):
    agent: str = ""
    action: str = ""
    target: str = ""


@dataclass
class NeedsDeliberation(Event):
    agent: str = ""


# --- Brains (just functions) ---

def alice_brain(world: World, activation: int) -> TriageResult:
    if activation == 1:
        # First think: send DM to bob
        return TriageResult(Mode.REACT, [{"send_dm": "bob", "msg": "let's coordinate"}])
    elif activation == 2 and world.inbox["alice"]:
        # Got a reply — need to think about this
        return TriageResult(Mode.DELIBERATE)
    elif activation == 3:
        # Full deliberation complete — post to board
        return TriageResult(Mode.REACT, [{"post_board": "we agreed to fish less"}])
    return TriageResult(Mode.IGNORE)


def bob_brain(world: World, activation: int) -> TriageResult:
    if world.inbox["bob"]:
        # Got a DM — quick reply
        world.inbox["bob"].clear()
        return TriageResult(Mode.REACT, [{"send_dm": "alice", "msg": "sure, sounds good"}])
    return TriageResult(Mode.IGNORE)


# --- Test ---

def test_triage_conversation():
    bus = EventBus()
    world = World()
    transcript = []
    activation_count = {"alice": 0, "bob": 0}

    scheduler = Scheduler(bus, default_cost=1)

    TRIAGE_COST = 1
    DELIBERATE_COST = 4

    def execute_actions(agent, actions):
        for action in actions:
            if "send_dm" in action:
                target = action["send_dm"]
                world.inbox[target].append(action["msg"])
                transcript.append(f"{agent} -> {target}: {action['msg']}")
                bus.emit(ActionDone(agent=agent, action="send_dm", target=target))
            elif "post_board" in action:
                world.board.append(action["post_board"])
                transcript.append(f"{agent} -> board: {action['post_board']}")

    async def activate(agent):
        activation_count[agent] += 1
        brain = alice_brain if agent == "alice" else bob_brain
        result = brain(world, activation_count[agent])

        if result.mode == Mode.IGNORE:
            transcript.append(f"{agent}: [ignore]")
        elif result.mode == Mode.REACT:
            execute_actions(agent, result.actions)
        elif result.mode == Mode.DELIBERATE:
            transcript.append(f"{agent}: [deliberating...]")
            bus.emit(NeedsDeliberation(agent=agent))

    # DM recipients get scheduled for triage
    def on_action(event):
        if event.action == "send_dm":
            scheduler.schedule(
                event.target,
                lambda t=event.target: activate(t),
                cost=TRIAGE_COST,
            )

    bus.subscribe(ActionDone, on_action)

    def on_deliberate(event):
        scheduler.schedule(
            event.agent,
            lambda a=event.agent: activate(a),
            cost=DELIBERATE_COST,
        )

    bus.subscribe(NeedsDeliberation, on_deliberate)

    async def go():
        # Both agents start with triage
        scheduler.schedule("alice", lambda: activate("alice"))
        scheduler.schedule("bob", lambda: activate("bob"))
        await scheduler.run()

    asyncio.run(go())

    print("\n--- Transcript ---")
    for line in transcript:
        print(f"  {line}")
    print(f"\n--- Board ---")
    for post in world.board:
        print(f"  {post}")
    print(f"\n--- Activations ---")
    for agent, count in activation_count.items():
        print(f"  {agent}: {count}")

    # Alice: triage(react:DM) → triage(deliberate) → full think(react:board) = 3 activations
    # Bob: triage(ignore) → triage(react:reply) = 2 activations
    assert activation_count["alice"] == 3
    assert activation_count["bob"] == 2
    assert world.board == ["we agreed to fish less"]
    # t=1: alice and bob run concurrently. alice sends DM, bob sees it and replies.
    # t=2: bob re-triggered (no mail left, ignores). alice re-triggered (sees reply, deliberates).
    # t=6: alice deliberates, posts to board.
    assert transcript == [
        "alice -> bob: let's coordinate",          # t=1: alice DMs bob
        "bob -> alice: sure, sounds good",         # t=1: bob sees DM, replies
        "bob: [ignore]",                           # t=2: bob re-triggered, nothing new
        "alice: [deliberating...]",                # t=2: alice sees reply, needs to think
        "alice -> board: we agreed to fish less",  # t=6: alice deliberates, posts
    ]
