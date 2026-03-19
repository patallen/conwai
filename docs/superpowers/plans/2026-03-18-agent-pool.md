# AgentPool Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract agent lifecycle management into an `AgentPool` class, replacing `ctx.agent_map` as the single source of truth for the agent population.

**Architecture:** New `conwai/pool.py` with `AgentPool` wrapping `AgentRepository` and `MessageBus`. All `ctx.agent_map` references across 5 files become pool queries. Context loses `agent_map`/`register_agent`, gains `pool`.

**Tech Stack:** Python dataclasses, existing AgentRepository/MessageBus

**Spec:** `docs/superpowers/specs/2026-03-18-agent-pool-design.md`

---

### Task 1: Create AgentPool with tests

**Files:**
- Create: `conwai/pool.py`
- Create: `tests/test_pool.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_pool.py
import tempfile
from pathlib import Path
from conwai.agent import Agent
from conwai.config import STARTING_BREAD
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository


def _make_pool(tmp_path: Path | None = None) -> tuple[AgentPool, AgentRepository, MessageBus]:
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp_path / "agents")
    bus = MessageBus()
    pool = AgentPool(repo, bus)
    return pool, repo, bus


def test_load_or_create_new():
    pool, repo, bus = _make_pool()
    agent = pool.load_or_create("A1", "baker", born_tick=0)
    assert agent.handle == "A1"
    assert agent.role == "baker"
    assert agent.alive is True
    assert pool.by_handle("A1") is agent
    assert "A1" in bus._known_handles


def test_load_or_create_existing():
    tmp = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp / "agents")
    agent = Agent(handle="A1", role="baker", coins=42, born_tick=0)
    repo.create(agent)

    bus = MessageBus()
    pool = AgentPool(repo, bus)
    loaded = pool.load_or_create("A1", "baker", born_tick=0)
    assert loaded.coins == 42
    assert loaded.alive is True
    assert "A1" in bus._known_handles


def test_load_or_create_dead_agent_not_registered_on_bus():
    tmp = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp / "agents")
    agent = Agent(handle="A1", role="baker", alive=False, born_tick=0)
    repo.create(agent)

    bus = MessageBus()
    pool = AgentPool(repo, bus)
    loaded = pool.load_or_create("A1", "baker", born_tick=0)
    assert loaded.alive is False
    assert "A1" not in bus._known_handles
    assert pool.by_handle("A1") is loaded


def test_spawn():
    pool, repo, bus = _make_pool()
    agent = pool.spawn("flour_forager", born_tick=5)
    assert agent.role == "flour_forager"
    assert agent.born_tick == 5
    assert agent.alive is True
    assert agent.bread == STARTING_BREAD
    assert pool.by_handle(agent.handle) is agent
    assert agent.handle in bus._known_handles
    assert repo.exists(agent.handle)


def test_kill():
    pool, repo, bus = _make_pool()
    pool.load_or_create("A1", "baker", born_tick=0)
    pool.kill("A1")
    agent = pool.by_handle("A1")
    assert agent.alive is False
    assert "A1" not in bus._known_handles


def test_queries():
    pool, _, _ = _make_pool()
    pool.load_or_create("A1", "baker", born_tick=0)
    pool.load_or_create("A2", "flour_forager", born_tick=0)
    pool.load_or_create("A3", "baker", born_tick=0)
    pool.kill("A2")

    assert len(pool.all()) == 3
    assert len(pool.alive()) == 2
    assert set(pool.handles()) == {"A1", "A3"}
    assert pool.by_handle("A2").alive is False
    assert pool.by_handle("NOPE") is None


def test_replace_dead():
    pool, _, _ = _make_pool()
    pool.load_or_create("A1", "baker", born_tick=0)
    pool.load_or_create("A2", "flour_forager", born_tick=0)
    pool.kill("A2")

    from conwai.bulletin_board import BulletinBoard
    from conwai.events import EventLog
    board = BulletinBoard()
    events = EventLog(db_path=":memory:")
    new_agents = pool.replace_dead(board, events, born_tick=10)

    assert len(new_agents) == 1
    assert new_agents[0].role == "flour_forager"
    assert new_agents[0].alive is True
    assert new_agents[0].born_tick == 10
    # Dead agent evicted
    assert pool.by_handle("A2") is None
    # Replacement is in pool
    assert pool.by_handle(new_agents[0].handle) is not None
    assert len(pool.alive()) == 2
    assert len(pool.all()) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /Users/pat/Code/conwai && python -m pytest tests/test_pool.py -v`
Expected: ImportError — `conwai.pool` doesn't exist

- [ ] **Step 3: Implement AgentPool**

```python
# conwai/pool.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from conwai.agent import Agent
from conwai.config import STARTING_BREAD
from conwai.repository import AgentRepository

if TYPE_CHECKING:
    from conwai.bulletin_board import BulletinBoard
    from conwai.events import EventLog
    from conwai.messages import MessageBus

log = logging.getLogger("conwai")


class AgentPool:
    def __init__(self, repo: AgentRepository, bus: MessageBus):
        self._repo = repo
        self._bus = bus
        self._agents: dict[str, Agent] = {}

    # --- Queries ---

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def alive(self) -> list[Agent]:
        return [a for a in self._agents.values() if a.alive]

    def by_handle(self, handle: str) -> Agent | None:
        return self._agents.get(handle)

    def handles(self) -> list[str]:
        return [h for h, a in self._agents.items() if a.alive]

    # --- Lifecycle ---

    def load_or_create(self, handle: str, role: str, born_tick: int) -> Agent:
        if self._repo.exists(handle):
            agent = self._repo.load(handle)
        else:
            agent = Agent(handle=handle, role=role, born_tick=born_tick, bread=STARTING_BREAD)
            self._repo.create(agent)
        self._agents[handle] = agent
        if agent.alive:
            self._bus.register(handle)
        return agent

    def spawn(self, role: str, born_tick: int, prefix: str = "A") -> Agent:
        handle = self._generate_handle(prefix)
        agent = Agent(handle=handle, role=role, born_tick=born_tick, bread=STARTING_BREAD)
        self._repo.create(agent)
        self._agents[handle] = agent
        self._bus.register(handle)
        return agent

    def kill(self, handle: str) -> None:
        agent = self._agents.get(handle)
        if agent:
            agent.alive = False
            self._bus.unregister(handle)

    def replace_dead(self, board: BulletinBoard, events: EventLog, born_tick: int) -> list[Agent]:
        new_agents = []
        dead = [a for a in self._agents.values() if not a.alive]
        for agent in dead:
            self._bus.unregister(agent.handle)
            del self._agents[agent.handle]
            board.post("WORLD", f"{agent.handle} has died. A new member is joining.")
            log.info(f"[WORLD] {agent.handle} DIED")

            replacement = self.spawn(agent.role, born_tick, prefix=agent.handle[0])
            board.post("WORLD", f"New member {replacement.handle} has joined.")
            events.log("WORLD", "agent_spawned", {"handle": replacement.handle, "replaced": agent.handle})
            log.info(f"[WORLD] {replacement.handle} spawned (replacing {agent.handle})")
            new_agents.append(replacement)
        return new_agents

    # --- Persistence ---

    def save(self, handle: str) -> None:
        agent = self._agents.get(handle)
        if agent:
            self._repo.save(agent)

    def save_all(self) -> None:
        for agent in self._agents.values():
            self._repo.save(agent)

    # --- Internal ---

    def _generate_handle(self, prefix: str = "A") -> str:
        while True:
            handle = f"{prefix}{uuid4().hex[:3]}"
            if not self._repo.exists(handle):
                return handle
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /Users/pat/Code/conwai && python -m pytest tests/test_pool.py -v`
Expected: All 8 tests pass

- [ ] **Step 5: Commit**

```bash
git add conwai/pool.py tests/test_pool.py
git commit -m "Add AgentPool class with lifecycle management and tests"
```

---

### Task 2: Update Context to use pool

**Files:**
- Modify: `conwai/app.py`

- [ ] **Step 1: Replace agent_map with pool on Context**

Remove `agent_map` field and `register_agent` method. Add `pool` field (default `None` since it's wired by the caller).

```python
# conwai/app.py
import asyncio
from dataclasses import dataclass, field

from conwai.bulletin_board import BulletinBoard
from conwai.config import BOARD_MAX_POSTS, BOARD_MAX_POST_LENGTH
from conwai.events import EventLog
from conwai.messages import MessageBus


@dataclass
class Context:
    board: BulletinBoard = field(
        default_factory=lambda: BulletinBoard(
            max_posts=BOARD_MAX_POSTS, max_post_length=BOARD_MAX_POST_LENGTH
        )
    )
    bus: MessageBus = field(default_factory=MessageBus)
    events: EventLog = field(default_factory=EventLog)
    pool: object = field(default=None, repr=False)
    world: object = field(default=None, repr=False)
    tick: int = 0
    compact_semaphore: asyncio.Semaphore = field(
        default_factory=lambda: asyncio.Semaphore(5)
    )

    def log(self, handle: str, event_type: str, data: dict | None = None):
        self.events.log(handle, event_type, data)
```

- [ ] **Step 2: Commit**

```bash
git add conwai/app.py
git commit -m "Replace agent_map with pool on Context"
```

---

### Task 3: Migrate default_actions.py

**Files:**
- Modify: `conwai/default_actions.py:22-24` (`_post_to_board` — `ctx.agent_map.items()`)
- Modify: `conwai/default_actions.py:44-45` (`_send_message` — `ctx.agent_map[to]`)
- Modify: `conwai/default_actions.py:86` (`_inspect` — `ctx.agent_map.get()`)
- Modify: `conwai/default_actions.py:126` (`_pay` — `ctx.agent_map.get()`)
- Modify: `conwai/default_actions.py:181` (`_give` — `ctx.agent_map.get()`)

- [ ] **Step 1: Replace all agent_map references**

`_post_to_board` line 22-24:
```python
# Before:
for h, a in ctx.agent_map.items():
    if h != agent.handle and h in content:
        a.gain_coins("referenced on board", config.ENERGY_GAIN["referenced"])
# After:
for a in ctx.pool.all():
    if a.handle != agent.handle and a.handle in content:
        a.gain_coins("referenced on board", config.ENERGY_GAIN["referenced"])
```

`_send_message` line 44-45:
```python
# Before:
if to in ctx.agent_map:
    ctx.agent_map[to].gain_coins("received DM", config.ENERGY_GAIN["dm_received"])
# After:
recipient = ctx.pool.by_handle(to)
if recipient:
    recipient.gain_coins("received DM", config.ENERGY_GAIN["dm_received"])
```

`_inspect` line 86:
```python
# Before:
other = ctx.agent_map.get(handle)
# After:
other = ctx.pool.by_handle(handle)
```

`_pay` line 126:
```python
# Before:
other = ctx.agent_map.get(to)
# After:
other = ctx.pool.by_handle(to)
```

`_give` line 181:
```python
# Before:
other = ctx.agent_map.get(to)
# After:
other = ctx.pool.by_handle(to)
```

- [ ] **Step 2: Commit**

```bash
git add conwai/default_actions.py
git commit -m "Migrate default_actions.py from agent_map to pool"
```

---

### Task 4: Migrate world.py

**Files:**
- Modify: `conwai/world.py:69` (`_start_code_challenge` — `ctx.agent_map.keys()`)
- Modify: `conwai/world.py:85` (`_start_code_challenge` — `ctx.agent_map.get()`)
- Modify: `conwai/world.py:118` (`_clear_fragments` — `ctx.agent_map.get()`)
- Modify: `conwai/world.py:146-147` (`submit_code` — `ctx.agent_map`)

- [ ] **Step 1: Replace all agent_map references**

`_start_code_challenge` line 69:
```python
# Before:
handles = list(ctx.agent_map.keys())
# After:
handles = ctx.pool.handles()
```

`_start_code_challenge` line 85:
```python
# Before:
agent = ctx.agent_map.get(handle)
# After:
agent = ctx.pool.by_handle(handle)
```

`_clear_fragments` line 118:
```python
# Before:
agent = ctx.agent_map.get(handle)
# After:
agent = ctx.pool.by_handle(handle)
```

`submit_code` lines 146-147:
```python
# Before:
if handle != agent.handle and handle in ctx.agent_map:
    other = ctx.agent_map[handle]
# After:
other = ctx.pool.by_handle(handle)
if other and handle != agent.handle:
```

- [ ] **Step 2: Commit**

```bash
git add conwai/world.py
git commit -m "Migrate world.py from agent_map to pool"
```

---

### Task 5: Migrate main.py

**Files:**
- Modify: `main.py`

This is the biggest change. Remove `make_agent`, startup loop, and death/replacement block. Replace with pool calls.

- [ ] **Step 1: Update imports and setup**

Add `from conwai.pool import AgentPool`. Remove the `make_agent` function (lines 140-153).

- [ ] **Step 2: Replace startup loop (lines 155-184)**

```python
repo = AgentRepository()
pool = AgentPool(repo, ctx.bus)
ctx.pool = pool

roles = ["flour_forager"] * 6 + ["water_forager"] * 6 + ["baker"] * 4
for i, role in enumerate(roles, 1):
    agent = pool.load_or_create(f"A{i}", role, ctx.tick)
    if agent.alive:
        agent.core = b200
        agent.compactor = h200
        agent.actions = registry
        agent.context_window = 10_000
```

- [ ] **Step 3: Replace handler watcher agent_map refs (lines 40-81)**

All `ctx.agent_map[handle]` → `ctx.pool.by_handle(handle)`.
All `parts[1] in ctx.agent_map` → `ctx.pool.by_handle(parts[1]) is not None`.
All `handle in ctx.agent_map` → `ctx.pool.by_handle(handle) is not None`.

- [ ] **Step 4: Replace death/replacement block (lines 233-251)**

```python
new_agents = pool.replace_dead(ctx.board, ctx.events, ctx.tick)
for agent in new_agents:
    agent.core = b200
    agent.compactor = h200
    agent.actions = registry
    agent.context_window = 10_000
```

- [ ] **Step 5: Replace tick loop agent iteration (lines 253-265)**

```python
tasks = []
for agent in pool.alive():
    async def tick_and_save(a=agent, t=ctx.tick):
        start = time.monotonic()
        await a.tick(ctx)
        pool.save(a.handle)
        elapsed = time.monotonic() - start
        log.info(f"[{a.handle}] tick {t} took {elapsed:.1f}s")
    tasks.append(asyncio.create_task(tick_and_save()))
await asyncio.gather(*tasks)
```

- [ ] **Step 6: Update tax/spoilage loops to use pool.alive()**

```python
# Tax
if ctx.tick % 24 == 0:
    for agent in pool.alive():
        ...

# Spoilage
if config.BREAD_SPOIL_INTERVAL > 0 and ctx.tick % config.BREAD_SPOIL_INTERVAL == 0:
    for agent in pool.alive():
        ...
```

- [ ] **Step 7: Commit**

```bash
git add main.py
git commit -m "Migrate main.py to use AgentPool"
```

---

### Task 6: Update test files

**Files:**
- Modify: `test_agent.py:49,59`
- Modify: `test_compaction.py:416`

- [ ] **Step 1: Update test_agent.py**

Replace `ctx.register_agent(agent)` with pool setup:

```python
from conwai.pool import AgentPool
from conwai.repository import AgentRepository

repo = AgentRepository()

# In run():
pool = AgentPool(repo, ctx.bus)
ctx.pool = pool
# Replace ctx.register_agent(agent) with:
pool._agents[agent.handle] = agent
pool._bus.register(agent.handle)
# Same for fake agents
```

- [ ] **Step 2: Update test_compaction.py**

Replace `ctx.register_agent(agent)` with:
```python
from conwai.pool import AgentPool
from conwai.messages import MessageBus

bus = MessageBus()
pool = AgentPool(AgentRepository(base_dir=Path(tempfile.mkdtemp()) / "agents"), bus)
ctx = Context()
ctx.pool = pool
pool._agents[agent.handle] = agent
bus.register(agent.handle)
```

- [ ] **Step 3: Run all tests**

Run: `cd /Users/pat/Code/conwai && python -m pytest tests/ -v`
Expected: All pass

- [ ] **Step 4: Commit**

```bash
git add test_agent.py test_compaction.py
git commit -m "Update test harnesses to use AgentPool"
```

---

### Task 7: Verify no remaining agent_map references

- [ ] **Step 1: Grep for agent_map**

Run: `cd /Users/pat/Code/conwai && grep -r "agent_map" --include="*.py" .`
Expected: No matches (except possibly docs/plans)

- [ ] **Step 2: Grep for register_agent**

Run: `cd /Users/pat/Code/conwai && grep -r "register_agent" --include="*.py" .`
Expected: No matches

- [ ] **Step 3: Final commit if cleanup needed**
