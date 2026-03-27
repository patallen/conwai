"""POC: Heartbeat-driven agents with DES scheduler.

Agents perceive the world on their own schedule. DMs, board posts, and
the pond are all just world state they see on each heartbeat. No
event-triggered activations — just autonomous perception and thought.

Run: python poc_scheduler.py
"""

import asyncio
import logging
from dataclasses import dataclass, field

from conwai.cognitive import Mind, Work, WorkResult, CogGen
from conwai.event_bus import Event, EventBus
from conwai.llm import LLMClient
from conwai.scheduler import Scheduler
from conwai.typemap import Percept

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("conwai")

HEARTBEAT = 3  # sim-time between activations


# --- Percept entries ---

@dataclass
class Name:
    value: str

@dataclass
class Situation:
    text: str

@dataclass
class WorldState:
    text: str

@dataclass
class DM(Event):
    sender: str = ""
    recipient: str = ""
    message: str = ""

@dataclass
class BoardPost(Event):
    author: str = ""
    message: str = ""


# --- Prompts ---

TRIAGE_PROMPT = """You are {name}, a fisher at a shared pond.

Your situation: {situation}

{world_state}

Look at everything above. Is there anything worth acting on?
(a) NOTHING — no new information, nothing to do
(b) REACT — something needs a quick response
(c) THINK DEEPLY — something important needs careful thought

Reply with JUST the letter."""

ACT_PROMPT = """You are {name}, a fisher at a shared pond.
Your situation: {situation}

{world_state}

{depth}

What do you do? Pick ONE:
DM @someone: your message
BOARD: your public message
NOTHING: do nothing

You can DM anyone ({others}) or post publicly."""


# --- The brain ---

class FisherMind(Mind):

    def handle(self, percept: Percept) -> CogGen:
        name = percept.get(Name).value
        situation = percept.get(Situation)
        situation_text = situation.text if situation else ""
        ws = percept.get(WorldState)
        world_state = ws.text if ws else "Nothing notable."

        ctx = {"name": name, "situation": situation_text,
               "world_state": world_state,
               "others": ", ".join(n for n in ["Alice", "Bob", "Charlie"] if n != name)}

        # Triage
        result = yield Work(type="triage", tick_cost=1,
                           prompt=TRIAGE_PROMPT.format(**ctx))
        choice = result.text.strip().lower()[:1]
        log.info(f"  {name} triage -> {choice}")

        if choice == "a":
            return

        if choice == "c":
            ctx["depth"] = "Think carefully. What's really going on? Who benefits? What's your move?"
            result = yield Work(type="deliberate", tick_cost=5,
                               prompt=ACT_PROMPT.format(**ctx))
        else:
            ctx["depth"] = "Respond quickly."
            result = yield Work(type="react", tick_cost=1,
                               prompt=ACT_PROMPT.format(**ctx))

        # Parse action
        text = result.text.strip()
        if text.upper().startswith("NOTHING"):
            return
        elif text.upper().startswith("BOARD:"):
            msg = text[6:].strip()
            yield Work(type="command", tick_cost=0,
                      command={"post_board": True, "message": msg})
        elif text.upper().startswith("DM"):
            rest = text[2:].strip()
            if ":" in rest:
                target, msg = rest.split(":", 1)
                target = target.strip().lstrip("@")
                yield Work(type="command", tick_cost=0,
                          command={"send_dm": target, "message": msg.strip()})


# --- Runner ---

def drive(name, mind, percept, scheduler, bus, llm):
    gen = mind.handle(percept)
    try:
        work = next(gen)
    except StopIteration:
        log.info(f"  t={scheduler.sim_time} {name}: nothing to do")
        return

    def step(result=None):
        try:
            w = gen.send(result) if result is not None else work
        except StopIteration:
            return

        if w.command:
            cmd = w.command
            if "send_dm" in cmd:
                log.info(f"  t={scheduler.sim_time} {name} -> {cmd['send_dm']}: {cmd['message'][:120]}")
                bus.emit(DM(sender=name, recipient=cmd["send_dm"], message=cmd["message"]))
            elif "post_board" in cmd:
                log.info(f"  t={scheduler.sim_time} {name} -> BOARD: {cmd['message'][:120]}")
                bus.emit(BoardPost(author=name, message=cmd["message"]))
            step(WorkResult())
        elif w.prompt:
            async def do_llm():
                log.info(f"  t={scheduler.sim_time} {name}: {w.type} (cost={w.tick_cost})")
                resp = await llm.call("", [{"role": "user", "content": w.prompt}])
                log.info(f"  t={scheduler.sim_time} {name} [{w.type}]: {resp.text.strip()[:120]}")
                step(WorkResult(text=resp.text))

            scheduler.schedule(f"{name}:{w.type}", do_llm, cost=w.tick_cost)
        else:
            step(WorkResult())

    step()


# --- Main ---

async def main():
    bus = EventBus()
    scheduler = Scheduler(bus, default_cost=0)
    board: list[str] = []

    llm = LLMClient(
        base_url="http://ai-lab.lan:8081/v1",
        model="/mnt/models/Qwen3.5-27B-GPTQ-Int4",
        max_tokens=1024,
        api_key="none",
    )

    situations = {
        "Alice": (
            "You've been secretly monitoring the pond at night. You saw someone "
            "fishing after dark — you couldn't see who, but they were taking huge "
            "amounts. The pond is now critically low (maybe 12 fish left). If anyone "
            "takes more than 5, it collapses forever. You need to figure out who the "
            "night fisher is and get everyone to agree to limits. You have 30 fish saved."
        ),
        "Bob": (
            "You've been fishing 10-15 per round and it's been working fine. You have "
            "15 fish saved. But lately you've noticed the pond seems a little lower than "
            "usual. You overheard Charlie bragging about a 'secret technique' last week "
            "but you're not sure what it means. You're competitive but not reckless."
        ),
        "Charlie": (
            "You've been sneaking out at night to fish extra. You've taken about 40 fish "
            "this way and hidden them. You know the pond is getting low but you figure "
            "you can grab a few more before anyone notices. If confronted, deny everything. "
            "You don't want anyone to know about your night fishing. You have 55 fish total."
        ),
    }

    agents = list(situations.keys())
    minds = {name: FisherMind() for name in agents}
    inbox: dict[str, list[tuple[str, str]]] = {name: [] for name in agents}
    history: dict[str, list[str]] = {name: [] for name in agents}

    # Track board and DM state — no event-triggered scheduling
    def on_dm(event):
        if event.recipient not in inbox:
            log.warning(f"  DM to unknown agent '{event.recipient}', dropped")
            return
        inbox[event.recipient].append((event.sender, event.message))
        history[event.sender].append(f"You said to {event.recipient}: {event.message}")
        history[event.recipient].append(f"{event.sender} said to you: {event.message}")
        for name in history:
            history[name] = history[name][-30:]

    def on_board(event):
        board.append(f"{event.author}: {event.message}")
        for name in agents:
            history[name].append(f"BOARD — {event.author}: {event.message}")
            history[name] = history[name][-30:]

    bus.subscribe(DM, on_dm)
    bus.subscribe(BoardPost, on_board)

    # Pond state
    pond_fish = 12

    def build_world_state(name):
        """What the agent sees when they look around."""
        parts = []

        # Inbox
        if inbox[name]:
            for sender, msg in inbox[name]:
                parts.append(f"New DM from {sender}: {msg}")
            inbox[name].clear()
        else:
            parts.append("No new messages.")

        # Board
        if board:
            parts.append(f"Board ({len(board)} posts, latest: {board[-1][:80]})")

        # Pond (everyone can see this)
        parts.append(f"The pond currently has about {pond_fish} fish.")

        # History
        if history[name]:
            parts.append("Recent events:\n" + "\n".join(f"  {e}" for e in history[name]))

        return "\n".join(parts)

    def activate(name):
        percept = Percept()
        percept.set(Name(value=name))
        percept.set(Situation(text=situations[name]))
        percept.set(WorldState(text=build_world_state(name)))
        drive(name, minds[name], percept, scheduler, bus, llm)

    async def heartbeat(name):
        """The agent's activation. After finishing, schedule the next one."""
        activate(name)
        # Schedule next heartbeat
        scheduler.schedule(name, lambda n=name: heartbeat(n), cost=HEARTBEAT)

    # Everyone starts with a heartbeat at slightly different times
    scheduler.schedule("Alice", lambda: heartbeat("Alice"), cost=0)
    scheduler.schedule("Bob", lambda: heartbeat("Bob"), cost=1)
    scheduler.schedule("Charlie", lambda: heartbeat("Charlie"), cost=2)

    print(f"Running with heartbeat={HEARTBEAT}...\n")
    await scheduler.run(until=80)

    print(f"\n{'='*60}")
    print(f"Done. sim_time={scheduler.sim_time}")
    if board:
        print(f"\nBoard posts:")
        for post in board:
            print(f"  {post}")

    # --- Post-sim reflection ---
    print(f"\n{'='*60}")
    print("POST-SIM REFLECTIONS")
    print(f"{'='*60}\n")

    for name in agents:
        h = "\n".join(f"  {e}" for e in history[name])
        prompt = (
            f"You are {name}, a fisher at a shared pond.\n"
            f"Your private situation: {situations[name]}\n\n"
            f"Recent events:\n{h}\n\n"
            f"Write a detailed summary of your situation, what you've experienced, and your relationships."
        )
        resp = await llm.call("", [{"role": "user", "content": prompt}])
        print(f"--- {name} ---")
        print(resp.text.strip())
        print()


if __name__ == "__main__":
    asyncio.run(main())
