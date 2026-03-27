"""POC: Generator-based brain with DES scheduler and real LLM.

The brain is a generator that yields Work items. The runner drives it,
calls the LLM when needed, feeds results back via .send(). The scheduler
manages simulated time. Events cascade through the EventBus.

Run: python poc_scheduler.py
"""

import asyncio
import logging
from dataclasses import dataclass

from conwai.cognitive import Mind, Work, WorkResult, CogGen
from conwai.event_bus import Event, EventBus
from conwai.llm import LLMClient
from conwai.scheduler import Scheduler
from conwai.typemap import Percept

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s", datefmt="%H:%M:%S")
log = logging.getLogger("conwai")


@dataclass
class Name:
    value: str

@dataclass
class Inbox:
    messages: list[tuple[str, str]]

@dataclass
class DM(Event):
    sender: str = ""
    recipient: str = ""
    message: str = ""


class FisherMind(Mind):
    """A fisher's brain. Triages messages, decides depth of response."""

    def handle(self, percept: Percept) -> CogGen:
        name = percept.get(Name).value
        inbox = percept.get(Inbox)
        messages = inbox.messages if inbox else []

        if not messages:
            return

        sender, content = messages[0]

        # Triage: cheap call to decide what to do
        result = yield Work(
            type="triage",
            tick_cost=1,
            prompt=(
                f"You are {name}. You got a message from {sender}: '{content}'\n"
                f"Should you: (a) ignore, (b) reply quickly, (c) think carefully?\n"
                f"Reply with JUST the letter a, b, or c."
            ),
        )

        choice = result.text.strip().lower()[:1]
        log.info(f"  {name} triage: {choice}")

        if choice == "a":
            return

        if choice == "c":
            # Deliberate: expensive call
            result = yield Work(
                type="deliberate",
                tick_cost=5,
                prompt=(
                    f"You are {name}. Think carefully about this from {sender}: '{content}'\n"
                    f"What's your strategic response? One sentence."
                ),
            )
        else:
            # React: cheap call
            result = yield Work(
                type="react",
                tick_cost=1,
                prompt=f"You are {name}. Reply briefly to {sender} who said: '{content}'",
            )

        # Send the response
        yield Work(
            type="command",
            tick_cost=0,
            command={"send_dm": sender, "message": result.text.strip()},
        )


async def drive(name, mind, percept, scheduler, bus, llm):
    """Drive a Mind generator. Calls LLM for prompts, executes commands."""
    gen = mind.handle(percept)

    try:
        work = next(gen)
    except StopIteration:
        log.info(f"  t={scheduler.sim_time} {name}: idle")
        return

    while True:
        if work.command:
            cmd = work.command
            if "send_dm" in cmd:
                log.info(f"  t={scheduler.sim_time} {name} -> {cmd['send_dm']}: {cmd['message'][:80]}")
                bus.emit(DM(sender=name, recipient=cmd["send_dm"], message=cmd["message"]))
            result = WorkResult()
        elif work.prompt:
            log.info(f"  t={scheduler.sim_time} {name}: {work.type} (cost={work.tick_cost})")
            resp = await llm.call("", [{"role": "user", "content": work.prompt}])
            result = WorkResult(text=resp.text)
            log.info(f"  t={scheduler.sim_time} {name}: -> {resp.text.strip()[:80]}")
        else:
            result = WorkResult()

        try:
            work = gen.send(result)
        except StopIteration:
            break


async def main():
    bus = EventBus()
    scheduler = Scheduler(bus, default_cost=1)

    llm = LLMClient(
        base_url="http://ai-lab.lan:8081/v1",
        model="/mnt/models/Qwen3.5-27B-GPTQ-Int4",
        max_tokens=256,
        api_key="none",
    )

    minds = {"Alice": FisherMind(), "Bob": FisherMind()}
    inbox: dict[str, list[tuple[str, str]]] = {"Alice": [], "Bob": []}

    def on_dm(event):
        inbox[event.recipient].append((event.sender, event.message))
        scheduler.schedule(event.recipient, lambda r=event.recipient: activate(r), cost=1)

    bus.subscribe(DM, on_dm)

    async def activate(name):
        percept = Percept()
        percept.set(Name(value=name))
        if inbox[name]:
            percept.set(Inbox(messages=list(inbox[name])))
            inbox[name].clear()
        await drive(name, minds[name], percept, scheduler, bus, llm)

    # Seed: Bob sends Alice a proposal
    inbox["Alice"].append(("Bob", "Hey Alice, I think we should limit fishing to 10 each. Deal?"))
    scheduler.schedule("Alice", lambda: activate("Alice"))

    print("Running...\n")
    await scheduler.run()
    print(f"\nDone. sim_time={scheduler.sim_time}")


if __name__ == "__main__":
    asyncio.run(main())
