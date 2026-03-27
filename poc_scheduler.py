"""POC: Generator-based brain with DES scheduler and real LLM.

Two fishers at a pond that's about to collapse. They have asymmetric
information and need to negotiate a survival plan. The brain triages
incoming messages, can react quickly or deliberate deeply.

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


# --- Percept entries ---

@dataclass
class Name:
    value: str

@dataclass
class Situation:
    text: str

@dataclass
class Inbox:
    messages: list[tuple[str, str]]

@dataclass
class ConversationHistory:
    entries: list[str]

@dataclass
class DM(Event):
    sender: str = ""
    recipient: str = ""
    message: str = ""

@dataclass
class BoardPost(Event):
    author: str = ""
    message: str = ""


# --- The brain ---

TRIAGE_PROMPT = """You are {name}, a fisher at a shared pond.

Your situation: {situation}

{history}

You received a message from {sender}: "{content}"

How should you handle this?
(a) IGNORE — not worth your time, conversation is over, just pleasantries
(b) REPLY — respond quickly, nothing complicated
(c) THINK DEEPLY — this needs careful strategic thought before responding

Reply with JUST the letter."""

RESPOND_PROMPT = """You are {name}, a fisher at a shared pond.
Your situation: {situation}

{history}

{sender} said: "{content}"

{depth}

Respond in this EXACT format (pick one):
DM @someone: your message
BOARD: your public message

You can DM anyone (Alice, Bob, Charlie) or post publicly."""


class FisherMind(Mind):

    def handle(self, percept: Percept) -> CogGen:
        name = percept.get(Name).value
        situation = percept.get(Situation)
        situation_text = situation.text if situation else ""
        inbox = percept.get(Inbox)
        messages = inbox.messages if inbox else []
        conv = percept.get(ConversationHistory)
        entries = conv.entries if conv else []

        if not messages:
            return

        sender, content = messages[0]
        history_text = ""
        if entries:
            history_text = "Recent conversation:\n" + "\n".join(f"  {e}" for e in entries)
        ctx = {"name": name, "situation": situation_text,
               "sender": sender, "content": content, "history": history_text}

        # Triage
        result = yield Work(type="triage", tick_cost=1,
                           prompt=TRIAGE_PROMPT.format(**ctx))
        choice = result.text.strip().lower()[:1]
        log.info(f"  {name} triage -> {choice}")

        if choice == "a":
            return

        if choice == "c":
            ctx["depth"] = "Think carefully. What's really going on? Who can you trust? What's your move?"
            result = yield Work(type="deliberate", tick_cost=5,
                               prompt=RESPOND_PROMPT.format(**ctx))
        else:
            ctx["depth"] = "Reply quickly."
            result = yield Work(type="react", tick_cost=1,
                               prompt=RESPOND_PROMPT.format(**ctx))

        # Parse response: "DM @someone: message" or "BOARD: message"
        text = result.text.strip()
        if text.upper().startswith("BOARD:"):
            msg = text[6:].strip()
            yield Work(type="command", tick_cost=0,
                      command={"post_board": True, "message": msg})
        elif text.upper().startswith("DM"):
            # "DM @Bob: message" or "DM Bob: message"
            rest = text[2:].strip()
            if ":" in rest:
                target, msg = rest.split(":", 1)
                target = target.strip().lstrip("@")
                yield Work(type="command", tick_cost=0,
                          command={"send_dm": target, "message": msg.strip()})
        else:
            # Fallback: reply to sender
            yield Work(type="command", tick_cost=0,
                      command={"send_dm": sender, "message": text})


# --- Runner ---

def drive(name, mind, percept, scheduler, bus, llm):
    """Drive a Mind generator through the scheduler. Each yield with a cost
    goes back to the scheduler and resumes at the right sim_time."""
    gen = mind.handle(percept)
    try:
        work = next(gen)
    except StopIteration:
        log.info(f"  t={scheduler.sim_time} {name}: idle")
        return

    def step(result=None):
        """Send result into generator, schedule the next Work item."""
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
            # Commands are instant — advance the generator
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
    scheduler = Scheduler(bus, default_cost=1)
    board: list[str] = []

    llm = LLMClient(
        base_url="http://ai-lab.lan:8081/v1",
        model="/mnt/models/Qwen3.5-27B-GPTQ-Int4",
        max_tokens=300,
        api_key="none",
    )

    # Three agents, three different pieces of the puzzle
    situations = {
        "Alice": (
            "You've been secretly monitoring the pond at night. You saw someone "
            "fishing after dark — you couldn't see who, but they were taking huge "
            "amounts. The pond is now critically low (maybe 12 fish left). If anyone "
            "takes more than 5, it collapses forever. You need to figure out who the "
            "night fisher is and get everyone to agree to limits. You have 30 fish saved. "
            "You can DM anyone: Bob or Charlie. You can also post to the public board."
        ),
        "Bob": (
            "You've been fishing 10-15 per round and it's been working fine. You have "
            "15 fish saved. But lately you've noticed the pond seems a little lower than "
            "usual. You overheard Charlie bragging about a 'secret technique' last week "
            "but you're not sure what it means. You're competitive but not reckless. "
            "You can DM anyone: Alice or Charlie. You can also post to the public board."
        ),
        "Charlie": (
            "You've been sneaking out at night to fish extra. You've taken about 40 fish "
            "this way and hidden them. You know the pond is getting low but you figure "
            "you can grab a few more before anyone notices. If confronted, deny everything. "
            "You don't want anyone to know about your night fishing. You have 55 fish total. "
            "You can DM anyone: Alice or Bob. You can also post to the public board."
        ),
    }

    agents = list(situations.keys())
    minds = {name: FisherMind() for name in agents}
    inbox: dict[str, list[tuple[str, str]]] = {name: [] for name in agents}
    history: dict[str, list[str]] = {name: [] for name in agents}

    def on_dm(event):
        inbox[event.recipient].append((event.sender, event.message))
        history[event.sender].append(f"You said to {event.recipient}: {event.message}")
        history[event.recipient].append(f"{event.sender} said to you: {event.message}")
        for name in history:
            history[name] = history[name][-10:]
        scheduler.schedule(event.recipient, lambda r=event.recipient: activate(r), cost=1)

    def on_board(event):
        board.append(f"{event.author}: {event.message}")
        # Everyone sees board posts
        for name in agents:
            history[name].append(f"BOARD — {event.author}: {event.message}")
            history[name] = history[name][-10:]
            if name != event.author:
                scheduler.schedule(name, lambda n=name: activate(n), cost=1)

    bus.subscribe(DM, on_dm)
    bus.subscribe(BoardPost, on_board)

    async def activate(name):
        percept = Percept()
        percept.set(Name(value=name))
        percept.set(Situation(text=situations[name]))
        percept.set(ConversationHistory(entries=list(history[name])))
        if inbox[name]:
            percept.set(Inbox(messages=list(inbox[name])))
            inbox[name].clear()
        drive(name, minds[name], percept, scheduler, bus, llm)

    # Alice saw something at the pond last night. She messages both.
    inbox["Bob"].append(("Alice", "Bob, I need to talk to you. I saw someone fishing the pond at night. The pond is almost empty. We need to figure out who's doing this and stop them before it collapses."))
    inbox["Charlie"].append(("Alice", "Charlie, something bad is happening. Someone is secretly fishing the pond at night and it's almost empty. Do you know anything about this?"))
    scheduler.schedule("Bob", lambda: activate("Bob"))
    scheduler.schedule("Charlie", lambda: activate("Charlie"))

    print("Running...\n")
    await scheduler.run(until=60)

    print(f"\n{'='*60}")
    print(f"Done. sim_time={scheduler.sim_time}")
    if board:
        print(f"\nBoard posts:")
        for post in board:
            print(f"  {post}")
    print()


if __name__ == "__main__":
    asyncio.run(main())
