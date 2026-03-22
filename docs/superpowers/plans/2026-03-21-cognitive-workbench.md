# Cognitive Workbench Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a minimal scenario for testing cognitive pipeline changes without bread economy noise.

**Architecture:** A new `scenarios/workbench/` scenario with two actions (broadcast, message), a simple perception builder, and an interactive runner. Reuses the existing cognitive processes from `scenarios/bread_economy/processes/` (MemoryCompression, MemoryRecall, ContextAssembly, InferenceProcess) via cross-scenario import. No economy, no world systems, no config dataclass.

**Tech Stack:** Python, asyncio, existing conwai framework (Engine, BlackboardBrain, BrainPhase, ComponentStore, BulletinBoard, MessageBus)

---

### Task 1: WorkbenchPercept and WorkbenchPerceptionBuilder

**Files:**
- Create: `scenarios/workbench/__init__.py`
- Create: `scenarios/workbench/perception.py`
- Create: `tests/test_workbench_perception.py`

- [ ] **Step 1: Write failing tests for WorkbenchPercept**

```python
# tests/test_workbench_perception.py
from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.cognition.percept import ActionFeedback
from conwai.messages import MessageBus
from conwai.store import ComponentStore
from scenarios.workbench.perception import WorkbenchPerceptionBuilder


def _make_store():
    store = ComponentStore()
    store.register_component("agent_info", {"role": "", "personality": ""})
    store.register_component("brain", {"messages": [], "diary": []})
    return store


def _init_agent(store, handle="A1", role="observer", personality="curious"):
    store.init_agent(handle, overrides={"agent_info": {"role": role, "personality": personality}})


def test_percept_includes_broadcast():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    board.post("WORLD", "hello everyone")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "hello everyone" in percept.to_prompt()
    assert percept.agent_id == "A1"
    assert percept.tick == 1


def test_percept_includes_dms():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    bus.send("Bob", "A1", "private info")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "private info" in percept.to_prompt()


def test_percept_includes_identity():
    store = _make_store()
    _init_agent(store, "A1", role="analyst", personality="methodical, quiet")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "methodical" in percept.identity
    assert "A1" in percept.identity


def test_percept_includes_action_feedback():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    feedback = [ActionFeedback(action="broadcast", args={"content": "hi"}, result="sent")]
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1, action_feedback=feedback)
    assert percept.action_feedback == feedback


def test_percept_includes_injected_stimulus():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    builder.inject("A1", "A strange sound echoes from the north.")
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    assert "strange sound" in percept.to_prompt()


def test_percept_no_activity():
    store = _make_store()
    _init_agent(store, "A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    builder = WorkbenchPerceptionBuilder()
    percept = builder.build(Agent(handle="A1"), store, board, bus, tick=1)
    text = percept.to_prompt()
    # Should still produce valid prompt text, not crash
    assert isinstance(text, str)
    assert len(text) > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/pat/Code/conwai && python -m pytest tests/test_workbench_perception.py -v`
Expected: ImportError — `scenarios.workbench.perception` does not exist

- [ ] **Step 3: Create empty package and implement perception**

```python
# scenarios/workbench/__init__.py
```

```python
# scenarios/workbench/perception.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from conwai.cognition.percept import ActionFeedback

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.store import ComponentStore


@dataclass
class WorkbenchPercept:
    agent_id: str
    tick: int
    identity: str
    prompt_text: str
    action_feedback: list[ActionFeedback] = field(default_factory=list)

    def to_prompt(self) -> str:
        return self.prompt_text


class WorkbenchPerceptionBuilder:
    """Builds percepts from broadcasts, DMs, and injected stimuli."""

    def __init__(self):
        self._stimuli: dict[str, list[str]] = {}

    def inject(self, handle: str, text: str) -> None:
        """Inject a stimulus that will appear in the agent's next percept."""
        self._stimuli.setdefault(handle, []).append(text)

    def notify(self, handle: str, message: str) -> None:
        """Alias for inject, satisfies PerceptionBuilder protocol."""
        self.inject(handle, message)

    def build_system_prompt(self) -> str:
        return (
            "You are an agent in a shared environment with other agents. "
            "Communicate, observe, and act. Keep responses concise: state your "
            "decision and reasoning in 1-2 sentences, then act."
        )

    def build(
        self,
        agent: Agent,
        store: ComponentStore,
        board: BulletinBoard | None = None,
        bus: MessageBus | None = None,
        tick: int = 0,
        action_feedback: list[ActionFeedback] | None = None,
    ) -> WorkbenchPercept:
        info = store.get(agent.handle, "agent_info")

        identity = (
            f"You are @{agent.handle}. "
            f"Your temperament is {info['personality']} — this is innate."
        )
        if info.get("role"):
            identity += f" Your role: {info['role']}."

        parts = []

        if board:
            new_posts = board.read_new(agent.handle)
            if new_posts:
                parts.append(
                    "Broadcast:\n"
                    + "\n".join(f"@{p.handle}: {p.content}" for p in new_posts)
                )

        if bus:
            new_dms = bus.receive(agent.handle)
            if new_dms:
                parts.append(
                    "\n".join(
                        f"DM from @{dm.from_handle}: {dm.content}" for dm in new_dms
                    )
                )

        stimuli = self._stimuli.pop(agent.handle, [])
        if stimuli:
            parts.extend(stimuli)

        if not parts:
            parts.append("Nothing new has happened.")

        prompt_text = "\n\n".join(parts)

        return WorkbenchPercept(
            agent_id=agent.handle,
            tick=tick,
            identity=identity,
            prompt_text=prompt_text,
            action_feedback=action_feedback or [],
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/pat/Code/conwai && python -m pytest tests/test_workbench_perception.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/pat/Code/conwai && git add scenarios/workbench/__init__.py scenarios/workbench/perception.py tests/test_workbench_perception.py && git commit -m "Add workbench scenario perception layer"
```

---

### Task 2: Actions (broadcast + message)

**Files:**
- Create: `scenarios/workbench/actions.py`
- Create: `tests/test_workbench_actions.py`

- [ ] **Step 1: Write failing tests**

```python
# tests/test_workbench_actions.py
import tempfile
from pathlib import Path

from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.engine import TickContext
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.storage import SQLiteStorage
from conwai.store import ComponentStore
from scenarios.workbench.actions import create_registry
from scenarios.workbench.perception import WorkbenchPerceptionBuilder


def _setup():
    store = ComponentStore()
    store.register_component("agent_info", {"role": "", "personality": ""})
    store.register_component("brain", {"messages": [], "diary": []})
    board = BulletinBoard()
    bus = MessageBus()
    events = EventLog(path=Path(":memory:"))
    perception = WorkbenchPerceptionBuilder()
    tmp = Path(tempfile.mkdtemp())
    storage = SQLiteStorage(tmp / "test.db")
    repo = AgentRepository(storage=storage)
    pool = AgentPool(repo, store, bus=bus)
    return store, board, bus, events, perception, pool


def _add(pool, store, handle):
    return pool.load_or_create(
        Agent(handle=handle),
        component_overrides={"agent_info": {"role": "test", "personality": "test"}},
    )


def _make_ctx(store, board, bus, events, perception, pool, tick=1):
    return TickContext(
        tick=tick, pool=pool, store=store,
        perception=perception, board=board, bus=bus, events=events,
    )


def test_broadcast_posts_to_board():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1")
    agent = pool.by_handle("A1")
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry = create_registry()

    result = registry.execute(agent, "broadcast", {"content": "hello world"}, ctx)
    assert "hello world" in result

    posts = board.read_new("OTHER")
    assert len(posts) == 1
    assert posts[0].content == "hello world"
    assert posts[0].handle == "A1"


def test_message_sends_dm():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1")
    _add(pool, store, "A2")
    agent = pool.by_handle("A1")
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry = create_registry()

    result = registry.execute(agent, "message", {"to": "A2", "content": "secret"}, ctx)
    assert "A2" in result

    dms = bus.receive("A2")
    assert len(dms) == 1
    assert dms[0].content == "secret"
    assert dms[0].from_handle == "A1"


def test_message_to_unknown_handle():
    store, board, bus, events, perception, pool = _setup()
    _add(pool, store, "A1")
    agent = pool.by_handle("A1")
    ctx = _make_ctx(store, board, bus, events, perception, pool)
    registry = create_registry()

    result = registry.execute(agent, "message", {"to": "nobody", "content": "hi"}, ctx)
    assert "unknown" in result.lower() or "not delivered" in result.lower()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/pat/Code/conwai && python -m pytest tests/test_workbench_actions.py -v`
Expected: ImportError — `scenarios.workbench.actions` does not exist

- [ ] **Step 3: Implement actions**

```python
# scenarios/workbench/actions.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from conwai.actions import Action, ActionRegistry

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.engine import TickContext

log = logging.getLogger("conwai")


def _broadcast(agent: Agent, ctx: TickContext, args: dict) -> str:
    content = args.get("content", "")
    ctx.board.post(agent.handle, content)
    ctx.events.log(agent.handle, "broadcast", {"content": content})
    log.info(f"[{agent.handle}] broadcast: {content}")
    return f"broadcast: {content}"


def _message(agent: Agent, ctx: TickContext, args: dict) -> str:
    to = args.get("to", "").lstrip("@")
    content = args.get("content", "")
    if not to:
        return "missing 'to' field"
    err = ctx.bus.send(agent.handle, to, content)
    if err:
        return f"message failed: {err}"
    ctx.events.log(agent.handle, "message_sent", {"to": to, "content": content})
    log.info(f"[{agent.handle}] -> [{to}]: {content}")
    return f"sent message to {to}"


def create_registry() -> ActionRegistry:
    registry = ActionRegistry()
    registry.register(
        Action(
            name="broadcast",
            description="Post a message to the shared broadcast channel. All agents will see it.",
            parameters={
                "content": {"type": "string", "description": "The message to broadcast"},
            },
            handler=_broadcast,
        )
    )
    registry.register(
        Action(
            name="message",
            description="Send a private message to another agent.",
            parameters={
                "to": {"type": "string", "description": "Handle of the recipient (e.g. @Alice)"},
                "content": {"type": "string", "description": "The message to send"},
            },
            handler=_message,
        )
    )
    return registry
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/pat/Code/conwai && python -m pytest tests/test_workbench_actions.py -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
cd /Users/pat/Code/conwai && git add scenarios/workbench/actions.py tests/test_workbench_actions.py && git commit -m "Add workbench actions: broadcast and message"
```

---

### Task 3: System prompt

**Files:**
- Create: `scenarios/workbench/prompts/system.md`

- [ ] **Step 1: Create the prompt**

```markdown
# Communication
You share a broadcast channel with other agents. Use `broadcast` to speak publicly and `message` to speak privately.

# Memory
Your memory is managed automatically. Recent interactions stay in your context. Older ones are compressed into diary entries that get recalled when relevant.

# How to respond
State your decision and reasoning in 1-2 sentences, then act. Do not restate information you already know.
```

- [ ] **Step 2: Commit**

```bash
cd /Users/pat/Code/conwai && mkdir -p scenarios/workbench/prompts && git add scenarios/workbench/prompts/system.md && git commit -m "Add workbench system prompt"
```

---

### Task 4: Interactive runner

**Files:**
- Create: `scenarios/workbench/runner.py`

This is the main entry point. Not TDD — this is a CLI application that wires everything together.

- [ ] **Step 1: Implement the runner**

```python
# scenarios/workbench/runner.py
"""
Cognitive workbench: minimal scenario for testing cognitive pipeline changes.

Usage:
    uv run python -m scenarios.workbench.runner [--model MODEL] [--base-url URL] [--agents N]

Commands:
    (any text)          — broadcast as WORLD, then tick
    @HANDLE message     — send DM from HANDLE to all agents, then tick
    !tick [N]           — advance N ticks silently
    !inspect [HANDLE]   — show agent state (defaults to first agent)
    !memory [HANDLE]    — show diary + recent summaries
    !brain [HANDLE]     — dump raw brain state
    !agents             — list all agents
    !quit               — exit
"""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.cognition import BlackboardBrain, Brain
from conwai.embeddings import FastEmbedder
from conwai.engine import BrainPhase, Engine
from conwai.events import EventLog
from conwai.llm import LLMClient
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.storage import SQLiteStorage
from conwai.store import ComponentStore
from scenarios.bread_economy.processes import (
    ContextAssembly,
    InferenceProcess,
    MemoryCompression,
    MemoryRecall,
)
from scenarios.workbench.actions import create_registry
from scenarios.workbench.perception import WorkbenchPerceptionBuilder

log = logging.getLogger("conwai")


def setup_logging():
    log.setLevel(logging.INFO)
    h = logging.StreamHandler(sys.stdout)
    h.setFormatter(logging.Formatter("%(asctime)s %(message)s", datefmt="%H:%M:%S"))
    log.addHandler(h)


async def run(args):
    data_dir = args.data_dir
    storage = SQLiteStorage(path=data_dir / "state.db")

    store = ComponentStore(storage=storage)
    store.register_component("agent_info", {"role": "", "personality": ""})
    store.register_component("brain", {"messages": [], "diary": []})
    store.load_all()

    board = BulletinBoard(storage=storage)
    bus = MessageBus(storage=storage)
    events = EventLog(path=data_dir / "events.db")
    perception = WorkbenchPerceptionBuilder()

    repo = AgentRepository(storage=storage)
    pool = AgentPool(repo, store, bus=bus)

    client = LLMClient(
        base_url=args.base_url,
        model=args.model,
        max_tokens=2048,
    )

    embedder = FastEmbedder()

    registry = create_registry()

    system_prompt = (Path(__file__).parent / "prompts" / "system.md").read_text()

    def make_brain() -> BlackboardBrain:
        return BlackboardBrain(
            processes=[
                MemoryCompression(
                    recent_ticks=16,
                    embedder=embedder,
                ),
                MemoryRecall(recall_limit=5, embedder=embedder),
                ContextAssembly(
                    context_window=10_000,
                    system_prompt=system_prompt,
                ),
                InferenceProcess(client=client, tools=registry.tool_definitions()),
            ],
            store=store,
        )

    # Load or create agents
    from faker import Faker

    fake = Faker()

    brains: dict[str, Brain] = {}
    loaded_handles = list(repo.list_handles())
    for handle in loaded_handles:
        agent = pool.load_or_create(Agent(handle=handle))
        if agent.alive:
            brains[agent.handle] = make_brain()

    existing_handles = {a.handle for a in pool.all()}
    for _ in range(len(brains), args.agents):
        handle = fake.first_name()
        while handle in existing_handles:
            handle = fake.first_name()
        existing_handles.add(handle)
        agent = pool.load_or_create(
            Agent(handle=handle, born_tick=0),
            component_overrides={"agent_info": {"role": "", "personality": "observant, adaptive"}},
        )
        brains[agent.handle] = make_brain()

    bus.register("WORLD")

    brain_phase = BrainPhase(actions=registry, brains=brains, perception=perception)

    engine = Engine(
        pool=pool, store=store, perception=perception,
        board=board, bus=bus, events=events,
    )
    engine.add_phase(brain_phase)

    tick_data = storage.load_component("WORLD", "tick")
    tick = tick_data["value"] if tick_data else 0

    agent_names = sorted(brains.keys())
    print(f"\n  Agents: {', '.join(f'@{h}' for h in agent_names)}")
    print(f"  Model:  {args.model}")
    print(f"  Tick:   {tick}")
    print(f"  Type anything to broadcast, @HANDLE for DM, !help for commands\n")

    while True:
        try:
            import readline  # noqa: F401 — enables line editing
            line = await asyncio.get_event_loop().run_in_executor(
                None, lambda: input(f"[tick {tick}] > ")
            )
        except (EOFError, KeyboardInterrupt):
            break

        line = line.strip()
        if not line:
            continue

        if line == "!quit":
            break
        elif line == "!help":
            print(__doc__)
            continue
        elif line == "!agents":
            for a in pool.alive():
                info = store.get(a.handle, "agent_info")
                print(f"  @{a.handle} — {info.get('personality', '')}")
            continue
        elif line.startswith("!inspect"):
            parts = line.split()
            handle = parts[1] if len(parts) > 1 else agent_names[0]
            if not store.has(handle, "agent_info"):
                print(f"  unknown agent: {handle}")
                continue
            info = store.get(handle, "agent_info")
            print(f"\n  @{handle}")
            print(f"  Role: {info.get('role', '(none)')}")
            print(f"  Personality: {info.get('personality', '(none)')}")
            print()
            continue
        elif line.startswith("!memory"):
            parts = line.split()
            handle = parts[1] if len(parts) > 1 else agent_names[0]
            if not store.has(handle, "brain"):
                print(f"  unknown agent: {handle}")
                continue
            brain_state = store.get(handle, "brain")
            diary = brain_state.get("diary", [])
            messages = brain_state.get("messages", [])
            summaries = [m for m in messages if m.get("_tick_summary")]
            print(f"\n  === RECENT SUMMARIES ({len(summaries)}) ===")
            for s in summaries[-5:]:
                print(f"  {s['content'][:120]}")
            print(f"\n  === DIARY ({len(diary)} entries) ===")
            for d in diary[-10:]:
                print(f"  {d['content'][:120]}")
                if d.get("embedding"):
                    print(f"    [embedded, {len(d['embedding'])} dims]")
            print()
            continue
        elif line.startswith("!brain"):
            parts = line.split()
            handle = parts[1] if len(parts) > 1 else agent_names[0]
            if not store.has(handle, "brain"):
                print(f"  unknown agent: {handle}")
                continue
            import json
            brain_state = store.get(handle, "brain")
            print(json.dumps(brain_state, indent=2)[:3000])
            if len(json.dumps(brain_state)) > 3000:
                print("...")
            continue
        elif line.startswith("!tick"):
            parts = line.split()
            n = int(parts[1]) if len(parts) > 1 else 1
            for _ in range(n):
                tick += 1
                storage.save_component("WORLD", "tick", {"value": tick})
                await engine.tick(tick)
            print(f"  advanced to tick {tick}")
            continue
        elif line.startswith("@"):
            # DM from a handle
            parts = line.split(" ", 1)
            from_handle = parts[0][1:]
            msg = parts[1] if len(parts) > 1 else ""
            for handle in agent_names:
                bus.send(from_handle, handle, msg)
            print(f"  [{from_handle}] -> [all]: {msg}")
        else:
            board.post("WORLD", line)
            events.log("WORLD", "broadcast", {"content": line})
            print(f"  [WORLD]: {line}")

        # Auto-tick after input
        tick += 1
        storage.save_component("WORLD", "tick", {"value": tick})
        await engine.tick(tick)


def main():
    parser = argparse.ArgumentParser(description="Cognitive workbench")
    parser.add_argument("--model", default="/mnt/models/Qwen3.5-9B-AWQ")
    parser.add_argument("--base-url", default="http://ai-lab.lan:8080/v1")
    parser.add_argument("--agents", type=int, default=1)
    parser.add_argument("--data-dir", default="data/workbench", type=Path)
    args = parser.parse_args()

    args.data_dir.mkdir(parents=True, exist_ok=True)
    setup_logging()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create `__main__.py` for module execution**

```python
# scenarios/workbench/__main__.py
from scenarios.workbench.runner import main

main()
```

- [ ] **Step 3: Verify it starts without errors**

Run: `cd /Users/pat/Code/conwai && python -m scenarios.workbench.runner --help`
Expected: Shows argparse help text with --model, --base-url, --agents, --data-dir options

- [ ] **Step 4: Run the full existing test suite to verify nothing broken**

Run: `cd /Users/pat/Code/conwai && python -m pytest tests/ -v --ignore=tests/test_dashboard.py`
Expected: All tests PASS (dashboard test ignored — it may have external deps)

- [ ] **Step 5: Commit**

```bash
cd /Users/pat/Code/conwai && git add scenarios/workbench/runner.py scenarios/workbench/__main__.py && git commit -m "Add workbench interactive runner"
```

---

### Task 5: Smoke test with real LLM

Not automated — manual verification that the full pipeline works end to end.

- [ ] **Step 1: Start the workbench with one agent**

Run: `cd /Users/pat/Code/conwai && python -m scenarios.workbench.runner --agents 1`

- [ ] **Step 2: Interact and verify cognitive pipeline works**

Try these in sequence:
1. Type: `Hello, who are you?` — agent should respond via broadcast or message
2. Type: `!memory` — should show tick summaries being created
3. Type: `!tick 3` — advance a few ticks silently
4. Type: `What do you remember about our earlier conversation?` — tests recall
5. Type: `!memory` — verify diary entries are accumulating

- [ ] **Step 3: Test multi-agent mode**

Run: `cd /Users/pat/Code/conwai && rm -rf data/workbench && python -m scenarios.workbench.runner --agents 3`

Try:
1. Type: `Introduce yourselves to each other` — all agents should respond
2. Type: `!agents` — verify all agents listed
3. Type: `@Alice Hi from outside` — verify DM delivery

- [ ] **Step 4: Commit spec and plan docs**

```bash
cd /Users/pat/Code/conwai && git add docs/superpowers/specs/2026-03-21-cognitive-workbench-design.md docs/superpowers/plans/2026-03-21-cognitive-workbench.md && git commit -m "Add cognitive workbench design spec and implementation plan"
```
