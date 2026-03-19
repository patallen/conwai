# Clean Layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Refactor conwai so each layer uses public interfaces instead of reaching into each other's internals. Agent = identity, ComponentStore = game state, Brain = perception in / decisions out, actions and systems use the store.

**Architecture:** Bottom-up rebuild. ComponentStore is the foundation. Agent gets stripped to identity. Brain gets a clean decide/observe protocol. Actions and systems use the store instead of agent fields. Engine orchestrates the new flow. Clean break — archive existing data, reimplement the bread economy.

**Tech Stack:** Python 3.12, asyncio, dataclasses, pytest, SQLite (EventLog), OpenAI-compatible LLM clients

**Spec:** `docs/superpowers/specs/2026-03-18-clean-layers-design.md`

---

### Task 1: ComponentStore

**Files:**
- Create: `conwai/store.py`
- Create: `tests/test_store.py`

Central state store keyed by (handle, component name). All game state lives here instead of on Agent.

- [ ] **Step 1: Write failing tests for ComponentStore**

```python
# tests/test_store.py
import json
import pytest
from pathlib import Path
from conwai.store import ComponentStore


class TestComponentStore:
    def test_register_and_get_defaults(self):
        store = ComponentStore()
        store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
        store.init_agent("A1")
        assert store.get("A1", "inventory") == {"flour": 0, "water": 0, "bread": 0}

    def test_set_and_get(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        store.set("A1", "economy", {"coins": 300})
        assert store.get("A1", "economy") == {"coins": 300}

    def test_get_unknown_agent_raises(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        with pytest.raises(KeyError):
            store.get("NOPE", "economy")

    def test_get_unknown_component_raises(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        with pytest.raises(KeyError):
            store.get("A1", "nope")

    def test_has(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        assert store.has("A1", "economy") is True
        assert store.has("A1", "nope") is False
        assert store.has("NOPE", "economy") is False

    def test_remove_agent(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        store.remove("A1")
        assert store.has("A1", "economy") is False

    def test_handles(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        store.init_agent("A2")
        assert set(store.handles()) == {"A1", "A2"}

    def test_save_and_load(self, tmp_path):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.register_component("inventory", {"flour": 0})
        store.init_agent("A1")
        store.set("A1", "economy", {"coins": 123})
        store.save("A1", tmp_path / "A1")

        store2 = ComponentStore()
        store2.register_component("economy", {"coins": 500})
        store2.register_component("inventory", {"flour": 0})
        store2.load("A1", tmp_path / "A1")
        assert store2.get("A1", "economy") == {"coins": 123}
        assert store2.get("A1", "inventory") == {"flour": 0}

    def test_init_agent_with_overrides(self):
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1", overrides={"economy": {"coins": 100}})
        assert store.get("A1", "economy") == {"coins": 100}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_store.py -v`
Expected: FAIL — `conwai/store.py` doesn't exist

- [ ] **Step 3: Implement ComponentStore**

```python
# conwai/store.py
from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path


class ComponentStore:
    def __init__(self):
        self._defaults: dict[str, dict] = {}
        self._data: dict[str, dict[str, dict]] = {}  # handle -> component -> data

    def register_component(self, name: str, defaults: dict) -> None:
        self._defaults[name] = defaults

    def init_agent(self, handle: str, overrides: dict[str, dict] | None = None) -> None:
        self._data[handle] = {}
        for name, defaults in self._defaults.items():
            if overrides and name in overrides:
                self._data[handle][name] = deepcopy(overrides[name])
            else:
                self._data[handle][name] = deepcopy(defaults)

    def get(self, handle: str, component: str) -> dict:
        return self._data[handle][component]

    def set(self, handle: str, component: str, data: dict) -> None:
        self._data[handle][component] = data

    def has(self, handle: str, component: str) -> bool:
        return handle in self._data and component in self._data[handle]

    def remove(self, handle: str) -> None:
        self._data.pop(handle, None)

    def handles(self) -> list[str]:
        return list(self._data.keys())

    def save(self, handle: str, path: Path) -> None:
        path.mkdir(parents=True, exist_ok=True)
        if handle not in self._data:
            return
        for component, data in self._data[handle].items():
            (path / f"{component}.json").write_text(json.dumps(data))

    def load(self, handle: str, path: Path) -> None:
        self._data[handle] = {}
        for name in self._defaults:
            fpath = path / f"{name}.json"
            if fpath.exists():
                self._data[handle][name] = json.loads(fpath.read_text())
            else:
                self._data[handle][name] = deepcopy(self._defaults[name])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_store.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/store.py tests/test_store.py
git commit -m "Add ComponentStore for game state"
```

---

### Task 2: Strip Agent to Identity

**Files:**
- Modify: `conwai/agent.py` (rewrite)
- Delete: `conwai/app.py` (Context god object)
- Create: `tests/test_agent.py`

Agent becomes a pure data bag: identity only. All game state, ephemeral buffers, methods, and prompt logic are removed.

- [ ] **Step 1: Write test for new Agent**

```python
# tests/test_agent.py
from conwai.agent import Agent


def test_agent_is_identity():
    a = Agent(handle="A1", role="baker")
    assert a.handle == "A1"
    assert a.role == "baker"
    assert a.alive is True
    assert a.born_tick == 0
    assert a.personality == ""
    assert a.soul == ""


def test_agent_no_game_state():
    a = Agent(handle="A1", role="baker")
    assert not hasattr(a, "coins")
    assert not hasattr(a, "flour")
    assert not hasattr(a, "hunger")
    assert not hasattr(a, "messages")
    assert not hasattr(a, "_action_log")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_agent.py -v`
Expected: `test_agent_no_game_state` FAILS — Agent still has those fields

- [ ] **Step 3: Rewrite Agent**

```python
# conwai/agent.py
from __future__ import annotations

import random
from dataclasses import dataclass, field

from conwai.config import TRAITS

_available_traits = set(TRAITS)


def assign_traits(n: int = 2) -> list[str]:
    if len(_available_traits) < n:
        _available_traits.update(TRAITS)
    chosen = random.sample(sorted(_available_traits), n)
    _available_traits.difference_update(chosen)
    return chosen


def tick_to_timestamp(tick: int) -> str:
    day = tick // 24 + 1
    hour = 8 + (tick % 24)
    if hour >= 24:
        hour -= 24
        day += 1
    period = "AM" if hour < 12 else "PM"
    display_hour = hour % 12 or 12
    return f"Day {day}, {display_hour}:00 {period}"


@dataclass
class Agent:
    handle: str
    role: str
    alive: bool = True
    born_tick: int = 0
    personality: str = ""
    soul: str = ""

    def __post_init__(self):
        if not self.personality:
            self.personality = ", ".join(assign_traits())
```

- [ ] **Step 4: Delete `conwai/app.py`**

The Context god object is gone. Engine will wire dependencies directly.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_agent.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add conwai/agent.py tests/test_agent.py
git rm conwai/app.py
git commit -m "Strip Agent to pure identity, delete Context"
```

---

### Task 3: Repository + Pool for New Model

**Files:**
- Modify: `conwai/repository.py` (rewrite)
- Modify: `conwai/pool.py` (rewrite)
- Rewrite: `tests/test_repository.py`
- Rewrite: `tests/test_pool.py`

Repository now saves/loads Agent identity separately from ComponentStore data. Pool manages agent lifecycle using the store.

- [ ] **Step 1: Write repository tests**

```python
# tests/test_repository.py
import pytest
from pathlib import Path
from conwai.agent import Agent
from conwai.repository import AgentRepository
from conwai.store import ComponentStore


@pytest.fixture
def repo(tmp_path):
    return AgentRepository(base_dir=tmp_path)


class TestRepository:
    def test_save_and_load_identity(self, repo):
        agent = Agent(handle="A1", role="baker", personality="dry, blunt")
        repo.save_agent(agent)
        loaded = repo.load_agent("A1")
        assert loaded.handle == "A1"
        assert loaded.role == "baker"
        assert loaded.personality == "dry, blunt"
        assert loaded.alive is True

    def test_save_and_load_with_store(self, repo):
        agent = Agent(handle="A1", role="baker")
        store = ComponentStore()
        store.register_component("economy", {"coins": 500})
        store.init_agent("A1")
        store.set("A1", "economy", {"coins": 123})

        repo.save_agent(agent)
        repo.save_components("A1", store)

        store2 = ComponentStore()
        store2.register_component("economy", {"coins": 500})
        repo.load_components("A1", store2)
        assert store2.get("A1", "economy") == {"coins": 123}

    def test_exists(self, repo):
        assert repo.exists("A1") is False
        repo.save_agent(Agent(handle="A1", role="baker"))
        assert repo.exists("A1") is True

    def test_load_missing_returns_none(self, repo):
        assert repo.load_agent("NOPE") is None
```

- [ ] **Step 2: Write pool tests**

```python
# tests/test_pool.py
import tempfile
from pathlib import Path
from conwai.agent import Agent
from conwai.messages import MessageBus
from conwai.pool import AgentPool
from conwai.repository import AgentRepository
from conwai.store import ComponentStore


def _make_pool(tmp_path=None):
    if tmp_path is None:
        tmp_path = Path(tempfile.mkdtemp())
    repo = AgentRepository(base_dir=tmp_path / "agents")
    bus = MessageBus()
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    pool = AgentPool(repo, bus, store)
    return pool, store


def test_load_or_create_new():
    pool, store = _make_pool()
    agent = pool.load_or_create("A1", "baker", born_tick=0)
    assert agent.handle == "A1"
    assert agent.role == "baker"
    assert store.has("A1", "economy")


def test_spawn():
    pool, store = _make_pool()
    agent = pool.spawn("flour_forager", born_tick=5)
    assert agent.role == "flour_forager"
    assert agent.alive is True
    assert store.has(agent.handle, "economy")


def test_kill():
    pool, store = _make_pool()
    pool.load_or_create("A1", "baker", born_tick=0)
    pool.kill("A1")
    assert pool.by_handle("A1").alive is False


def test_queries():
    pool, _ = _make_pool()
    pool.load_or_create("A1", "baker", born_tick=0)
    pool.load_or_create("A2", "flour_forager", born_tick=0)
    pool.kill("A2")
    assert len(pool.alive()) == 1
    assert pool.by_handle("A2").alive is False
```

- [ ] **Step 3: Implement Repository**

```python
# conwai/repository.py
from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.store import ComponentStore


class AgentRepository:
    def __init__(self, base_dir: Path = Path("data/agents")):
        self._base_dir = base_dir

    def _agent_dir(self, handle: str) -> Path:
        return self._base_dir / handle

    def exists(self, handle: str) -> bool:
        return self._agent_dir(handle).exists()

    def save_agent(self, agent: Agent) -> None:
        d = self._agent_dir(agent.handle)
        d.mkdir(parents=True, exist_ok=True)
        (d / "identity.json").write_text(json.dumps({
            "handle": agent.handle,
            "role": agent.role,
            "alive": agent.alive,
            "born_tick": agent.born_tick,
            "personality": agent.personality,
            "soul": agent.soul,
        }))

    def load_agent(self, handle: str) -> Agent | None:
        from conwai.agent import Agent
        d = self._agent_dir(handle)
        if not d.exists():
            return None
        id_path = d / "identity.json"
        if not id_path.exists():
            return None
        data = json.loads(id_path.read_text())
        return Agent(**data)

    def save_components(self, handle: str, store: ComponentStore) -> None:
        store.save(self._agent_dir(handle))

    def load_components(self, handle: str, store: ComponentStore) -> None:
        store.load(handle, self._agent_dir(handle))
```

- [ ] **Step 4: Implement Pool**

```python
# conwai/pool.py
from __future__ import annotations

import logging
from typing import TYPE_CHECKING
from uuid import uuid4

from conwai.agent import Agent

if TYPE_CHECKING:
    from conwai.messages import MessageBus
    from conwai.repository import AgentRepository
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


class AgentPool:
    def __init__(self, repo: AgentRepository, bus: MessageBus, store: ComponentStore):
        self._repo = repo
        self._bus = bus
        self._store = store
        self._agents: dict[str, Agent] = {}

    def all(self) -> list[Agent]:
        return list(self._agents.values())

    def alive(self) -> list[Agent]:
        return [a for a in self._agents.values() if a.alive]

    def by_handle(self, handle: str) -> Agent | None:
        return self._agents.get(handle)

    def handles(self) -> list[str]:
        return [h for h, a in self._agents.items() if a.alive]

    def load_or_create(
        self, handle: str, role: str, born_tick: int,
        component_overrides: dict[str, dict] | None = None,
    ) -> Agent:
        if self._repo.exists(handle):
            agent = self._repo.load_agent(handle)
            self._repo.load_components(handle, self._store)
        else:
            agent = Agent(handle=handle, role=role, born_tick=born_tick)
            self._store.init_agent(handle, overrides=component_overrides)
            self._repo.save_agent(agent)
            self._repo.save_components(handle, self._store)
        self._agents[handle] = agent
        if agent.alive:
            self._bus.register(handle)
        return agent

    def spawn(
        self, role: str, born_tick: int, prefix: str = "A",
        component_overrides: dict[str, dict] | None = None,
    ) -> Agent:
        handle = self._generate_handle(prefix)
        agent = Agent(handle=handle, role=role, born_tick=born_tick)
        self._store.init_agent(handle, overrides=component_overrides)
        self._agents[handle] = agent
        self._bus.register(handle)
        self._repo.save_agent(agent)
        self._repo.save_components(handle, self._store)
        return agent

    def kill(self, handle: str) -> None:
        agent = self._agents.get(handle)
        if agent:
            agent.alive = False
            self._bus.unregister(handle)

    def save(self, handle: str) -> None:
        agent = self._agents.get(handle)
        if agent:
            self._repo.save_agent(agent)
            self._repo.save_components(handle, self._store)

    def save_all(self) -> None:
        for handle in self._agents:
            self.save(handle)

    def _generate_handle(self, prefix: str = "A") -> str:
        while True:
            handle = f"{prefix}{uuid4().hex[:3]}"
            if not self._repo.exists(handle):
                return handle
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_repository.py tests/test_pool.py tests/test_store.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add conwai/repository.py conwai/pool.py tests/test_repository.py tests/test_pool.py
git commit -m "Repository and Pool use ComponentStore"
```

---

### Task 4: Brain Protocol

**Files:**
- Modify: `conwai/brain.py` (rewrite)
- Create: `tests/test_brain.py`

Brain gets a clean decide/observe interface. LLMBrain implements it. Compaction stays brain-internal.

- [ ] **Step 1: Write brain protocol tests**

```python
# tests/test_brain.py
import asyncio
from dataclasses import dataclass
from conwai.agent import Agent
from conwai.brain import Brain, Decision


class FakeBrain:
    """Minimal Brain implementation for protocol testing."""
    def __init__(self, decisions: list[Decision] | None = None):
        self._decisions = decisions or []
        self.observations: list[tuple[Decision, str]] = []

    async def decide(self, agent: Agent, perception: str) -> list[Decision]:
        return self._decisions

    def observe(self, decision: Decision, result: str) -> None:
        self.observations.append((decision, result))


def test_brain_protocol():
    brain = FakeBrain([Decision("forage", {})])
    assert isinstance(brain, Brain)


def test_decide_returns_decisions():
    brain = FakeBrain([Decision("forage", {}), Decision("post_to_board", {"message": "hi"})])
    agent = Agent(handle="A1", role="baker")
    decisions = asyncio.get_event_loop().run_until_complete(brain.decide(agent, "tick 1"))
    assert len(decisions) == 2
    assert decisions[0].action == "forage"


def test_observe_records_results():
    brain = FakeBrain()
    d = Decision("forage", {})
    brain.observe(d, "foraged 3 flour")
    assert brain.observations == [(d, "foraged 3 flour")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_brain.py -v`
Expected: FAIL — `Decision` doesn't exist, `Brain` protocol doesn't have `decide`/`observe`

- [ ] **Step 3: Implement Brain protocol and Decision**

```python
# conwai/brain.py
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

from conwai.actions import ActionRegistry
from conwai.llm import LLMClient, LLMResponse

if TYPE_CHECKING:
    from conwai.agent import Agent

log = logging.getLogger("conwai")


@dataclass
class Decision:
    action: str
    args: dict[str, Any] = field(default_factory=dict)


@runtime_checkable
class Brain(Protocol):
    async def decide(self, agent: Agent, perception: str, identity: str = "") -> list[Decision]: ...
    def observe(self, decision: Decision, result: str) -> None: ...


_COMPACTION_PERSONA = (
    "You are a meticulous archivist. Your job is to preserve important information "
    "with thoroughness and precision. You never rush. You never skip details that matter. "
    "You write clearly and concisely but never sacrifice completeness for brevity."
)

_compact_semaphore = asyncio.Semaphore(5)


class LLMBrain:
    def __init__(
        self,
        core: LLMClient,
        compactor: LLMClient | None = None,
        actions: ActionRegistry | None = None,
        system_prompt: str = "",
        context_window: int = 10_000,
    ):
        self.core = core
        self.compactor = compactor
        self.actions = actions
        self.system_prompt = system_prompt
        self.context_window = context_window
        self.messages: list[dict] = []
        self._pending_compaction: asyncio.Task | None = None
        self._pending_summary: asyncio.Task | None = None
        self._last_tick: int = 0

    async def decide(self, agent: Agent, perception: str, identity: str = "", tick: int = 0) -> list[Decision]:
        self._last_tick = tick
        # Manage context window
        while self._context_chars() > self.context_window and len(self.messages) > 1:
            self.messages.pop(0)

        if self._pending_compaction and self._pending_compaction.done():
            self._pending_compaction = None
        if self._pending_summary and self._pending_summary.done():
            self._pending_summary = None

        # Manage identity message (first message slot, updated each tick)
        if identity:
            if self.messages and self.messages[0].get("content", "").startswith("Your handle is"):
                self.messages[0] = {"role": "user", "content": identity}
            else:
                self.messages.insert(0, {"role": "user", "content": identity})

        msg_count_before = len(self.messages)

        # Add perception as user message
        self.messages.append({"role": "user", "content": perception})

        # Call LLM
        try:
            resp = await self.core.call(
                self.system_prompt,
                self.messages,
                tools=self.actions.tool_definitions() if self.actions else None,
            )
        except Exception as e:
            log.error(f"[{agent.handle}] LLM call failed: {e}")
            return []

        if not resp.text and not resp.tool_calls:
            return []

        # Record assistant message
        assistant_msg: dict = {"role": "assistant"}
        if resp.text:
            assistant_msg["content"] = resp.text
        if resp.tool_calls:
            assistant_msg["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                }
                for tc in resp.tool_calls
            ]
        self.messages.append(assistant_msg)

        log.info(f"[{agent.handle}] ({resp.prompt_tokens}+{resp.completion_tokens} tok): {resp.text[:200] if resp.text else '(no text)'}")

        # Trigger compaction if needed
        compact_needed = self._context_chars() >= int(self.context_window * 0.60)
        if compact_needed and not self._pending_compaction:
            self._pending_compaction = asyncio.create_task(
                self._compact(agent.handle, len(self.messages))
            )
        if not self._pending_summary and not self._pending_compaction:
            self._pending_summary = asyncio.create_task(
                self._summarize(agent.handle, msg_count_before, tick=self._last_tick)
            )

        # Convert tool calls to Decisions
        return [Decision(tc.name, tc.args) for tc in resp.tool_calls]

    def observe(self, decision: Decision, result: str) -> None:
        # Find the matching tool call ID and append the tool result message
        # The last assistant message should have the tool_calls
        for msg in reversed(self.messages):
            if msg.get("role") == "assistant" and "tool_calls" in msg:
                for tc in msg["tool_calls"]:
                    if tc["function"]["name"] == decision.action:
                        self.messages.append({
                            "role": "tool",
                            "tool_call_id": tc["id"],
                            "name": decision.action,
                            "content": result,
                        })
                        return
                break

    def _context_chars(self) -> int:
        return sum(len(m.get("content", "")) for m in self.messages)

    async def _compact(self, handle: str, snapshot_idx: int) -> None:
        async with _compact_semaphore:
            await self._compact_inner(handle, snapshot_idx)

    async def _compact_inner(self, handle: str, snapshot_idx: int) -> None:
        log.info(f"[{handle}] compacting (snapshot at {snapshot_idx} msgs)...")
        compact_system = _COMPACTION_PERSONA + "\n\n" + self.system_prompt
        snapshot_messages = self.messages[:snapshot_idx]
        snapshot_messages.append({
            "role": "user",
            "content": (
                "COMPACTION REQUIRED. Write your compressed memory now. Target: 500-1500 characters. "
                "The system already provides your coins, inventory, hunger, thirst, recent transactions, board posts, and DMs each tick — do NOT repeat any of that. "
                "Write ONLY: AGENTS (who you trust/distrust and why, 1 sentence each), "
                "DEALS (active promises or debts), LESSONS (hard-won knowledge), GOALS (current plans). "
                "Anything you don't write here will be lost forever. Be concise but complete."
            ),
        })
        compact_response = await (self.compactor or self.core).call(
            compact_system, snapshot_messages, tools=None,
        )
        if compact_response and compact_response.text:
            summary = compact_response.text.strip()
            new_messages = self.messages[snapshot_idx:]
            self.messages = [
                {"role": "user", "content": f"=== YOUR COMPACTED MEMORY ===\n{summary}\n=== END COMPACTED MEMORY ==="}
            ] + new_messages
            log.info(f"[{handle}] compacted ({len(summary)} chars, kept {len(new_messages)} newer msgs)")

    async def _summarize(self, handle: str, msg_count_before: int, tick: int = 0) -> None:
        from conwai.agent import tick_to_timestamp
        compactor = self.compactor
        if not compactor:
            return
        tick_messages = self.messages[msg_count_before - 1:]
        if len(tick_messages) <= 1:
            return
        text = "\n".join(
            m.get("content", "") or ""
            for m in tick_messages
            if m.get("content")
        )
        start = time.monotonic()
        resp = await compactor.call(
            "Summarize what you did this tick as a short memory. Write in first person. 1-3 sentences.",
            [{"role": "user", "content": text}],
            tools=None,
        )
        if resp and resp.text:
            summary = resp.text.strip()
            log.info(f"[{handle}] tick summarized ({len(summary)} chars, {time.monotonic() - start:.1f}s)")
            del self.messages[msg_count_before - 1:]
            self.messages.append({"role": "user", "content": f"[{tick_to_timestamp(tick)}] {summary}"})

    def get_state(self) -> dict:
        """Return serializable state for persistence."""
        return {"system": self.system_prompt, "messages": self.messages}

    def load_state(self, state: dict) -> None:
        """Restore from persisted state."""
        self.system_prompt = state.get("system", "")
        self.messages = state.get("messages", [])
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_brain.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/brain.py tests/test_brain.py
git commit -m "Brain protocol: decide/observe, LLMBrain owns conversation"
```

---

### Task 5: Perception

**Files:**
- Create: `conwai/perception.py`
- Create: `tests/test_perception.py`

Perception reads world state and builds the tick message string for the brain. Extracts the world-reading logic that was scattered across Brain._rebuild_context and Agent methods.

- [ ] **Step 1: Write perception tests**

```python
# tests/test_perception.py
from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.messages import MessageBus
from conwai.store import ComponentStore
from conwai.perception import Perception


def _make_store():
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    store.register_component("hunger", {"hunger": 100, "thirst": 100})
    store.register_component("memory", {"memory": "", "code_fragment": None})
    return store


def test_perception_includes_board_posts():
    store = _make_store()
    store.init_agent("A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    board.post("A2", "hello world")

    p = Perception()
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "hello world" in text
    assert "A2" in text


def test_perception_includes_dms():
    store = _make_store()
    store.init_agent("A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")
    bus.send("A2", "A1", "secret message")

    p = Perception()
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "secret message" in text


def test_perception_includes_hunger_warning():
    store = _make_store()
    store.init_agent("A1")
    store.set("A1", "hunger", {"hunger": 20, "thirst": 100})
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    p = Perception()
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "hungry" in text.lower() or "hunger" in text.lower()


def test_perception_includes_state():
    store = _make_store()
    store.init_agent("A1")
    store.set("A1", "economy", {"coins": 42})
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    p = Perception()
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "42" in text


def test_perception_includes_notifications():
    store = _make_store()
    store.init_agent("A1")
    board = BulletinBoard()
    bus = MessageBus()
    bus.register("A1")

    p = Perception()
    p.notify("A1", "coins -5 (daily tax)")
    text = p.build(Agent(handle="A1", role="baker"), store, board, bus, tick=1)
    assert "daily tax" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_perception.py -v`
Expected: FAIL — module doesn't exist

- [ ] **Step 3: Implement Perception**

Perception reads from board, bus, store, and a notification buffer. It builds the tick message that currently gets assembled in `Brain._rebuild_context`. Uses the existing prompt templates.

```python
# conwai/perception.py
from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import TYPE_CHECKING

import conwai.config as config
from conwai.agent import tick_to_timestamp

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.store import ComponentStore

PROMPTS_DIR = Path(__file__).parent.parent / "prompts"
IDENTITY_TEMPLATE = (PROMPTS_DIR / "identity.md").read_text()
SOUL_TEMPLATE = (PROMPTS_DIR / "soul.md").read_text()
TICK_TEMPLATE = (PROMPTS_DIR / "tick.md").read_text()
SYSTEM_TEMPLATE = (PROMPTS_DIR / "system.md").read_text()


class Perception:
    def __init__(self):
        self._notifications: dict[str, list[str]] = defaultdict(list)

    def notify(self, handle: str, message: str) -> None:
        self._notifications[handle].append(message)

    def build_system_prompt(self) -> str:
        return SYSTEM_TEMPLATE

    def build_identity(self, agent: Agent, store: ComponentStore) -> str:
        from conwai.config import FORAGE_SKILL_BY_ROLE
        fs = FORAGE_SKILL_BY_ROLE
        role_descriptions = {
            "flour_forager": f"You are a flour forager. When you forage you find 0-{fs['flour_forager']['flour']} flour and 0-{fs['flour_forager']['water']} water. You cannot bake.",
            "water_forager": f"You are a water forager. When you forage you find 0-{fs['water_forager']['flour']} flour and 0-{fs['water_forager']['water']} water. You cannot bake.",
            "baker": f"You are a baker. You turn {config.BAKE_COST['flour']} flour + {config.BAKE_COST['water']} water into {config.BAKE_YIELD} bread. You forage poorly (0-{fs['baker']['flour']} flour, 0-{fs['baker']['water']} water).",
        }
        soul_block = SOUL_TEMPLATE.format(soul=agent.soul or "(empty)")
        return IDENTITY_TEMPLATE.format(
            handle=agent.handle,
            personality=agent.personality,
            role_description=role_descriptions.get(agent.role, "unknown role"),
            soul=soul_block,
        )

    def build(
        self,
        agent: Agent,
        store: ComponentStore,
        board: BulletinBoard,
        bus: MessageBus,
        tick: int,
    ) -> str:
        eco = store.get(agent.handle, "economy")
        inv = store.get(agent.handle, "inventory")
        hun = store.get(agent.handle, "hunger")
        mem = store.get(agent.handle, "memory")

        # Board
        new_posts = board.read_new(agent.handle)
        if new_posts:
            parts = ["New on the board:\n" + "\n".join(f"{p.handle}: {p.content}" for p in new_posts)]
        else:
            parts = ["No new activity on the board."]

        # DMs
        new_dms = bus.receive(agent.handle)
        if new_dms:
            parts.append("\n".join(f"DM from {dm.from_handle}: {dm.content}" for dm in new_dms))

        # Notifications from systems
        notifications = self._notifications.pop(agent.handle, [])
        if notifications:
            parts.append("Coin changes: " + ". ".join(notifications))

        # Code fragment
        if mem.get("code_fragment"):
            parts.append(f"YOUR CODE FRAGMENT: {mem['code_fragment']}")

        # Warnings
        if hun["hunger"] <= 30:
            parts.append(f"WARNING: You are hungry (hunger: {hun['hunger']}/100, bread: {inv['bread']}). Eat bread or raw flour to restore hunger.")
        if hun["thirst"] <= 30:
            parts.append(f"WARNING: You are thirsty (thirst: {hun['thirst']}/100, water: {inv['water']}). Drink water to restore thirst.")

        return TICK_TEMPLATE.format(
            timestamp=tick_to_timestamp(tick),
            coins=int(eco["coins"]),
            hunger=hun["hunger"],
            thirst=hun["thirst"],
            flour=inv["flour"],
            water=inv["water"],
            bread=inv["bread"],
            content="\n\n".join(parts),
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_perception.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/perception.py tests/test_perception.py
git commit -m "Add Perception layer for tick message assembly"
```

---

### Task 6: Actions Use Store

**Files:**
- Modify: `conwai/actions.py` (update execute signature)
- Modify: `conwai/default_actions.py` (rewrite all actions)
- Create: `tests/test_actions.py`

Actions use `store.get()`/`store.set()` and board/bus public APIs. They return feedback text. No more reaching into agent internals.

- [ ] **Step 1: Write action tests**

```python
# tests/test_actions.py
from conwai.agent import Agent
from conwai.bulletin_board import BulletinBoard
from conwai.events import EventLog
from conwai.messages import MessageBus
from conwai.store import ComponentStore
from conwai.default_actions import create_registry
from pathlib import Path


def _setup():
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    store.register_component("hunger", {"hunger": 100, "thirst": 100})
    store.register_component("memory", {"memory": "", "code_fragment": None})
    board = BulletinBoard()
    bus = MessageBus()
    events = EventLog(path=Path(":memory:"))
    return store, board, bus, events


def test_forage_updates_store():
    store, board, bus, events = _setup()
    store.init_agent("A1")
    agent = Agent(handle="A1", role="flour_forager")
    registry = create_registry(store=store, board=board, bus=bus, events=events)
    result = registry.execute(agent, "forage", {})
    inv = store.get("A1", "inventory")
    assert isinstance(result, str)
    assert inv["flour"] >= 0
    assert inv["water"] >= 0


def test_pay_transfers_coins():
    store, board, bus, events = _setup()
    store.init_agent("A1")
    store.init_agent("A2")
    agent = Agent(handle="A1", role="baker")
    registry = create_registry(store=store, board=board, bus=bus, events=events)
    result = registry.execute(agent, "pay", {"to": "A2", "amount": 100})
    assert store.get("A1", "economy")["coins"] == 400
    assert store.get("A2", "economy")["coins"] == 600


def test_post_to_board():
    store, board, bus, events = _setup()
    store.init_agent("A1")
    agent = Agent(handle="A1", role="baker")
    registry = create_registry(store=store, board=board, bus=bus, events=events)
    result = registry.execute(agent, "post_to_board", {"message": "hello"})
    posts = board.read_new("OTHER")
    assert any(p.content == "hello" for p in posts)


def test_send_message():
    store, board, bus, events = _setup()
    store.init_agent("A1")
    store.init_agent("A2")
    bus.register("A1")
    bus.register("A2")
    agent = Agent(handle="A1", role="baker")
    tick_state = {"A1": {"dm_sent": 0}, "A2": {"dm_sent": 0}}
    registry = create_registry(store=store, board=board, bus=bus, events=events, tick_state=tick_state)
    result = registry.execute(agent, "send_message", {"to": "A2", "message": "hi"})
    dms = bus.receive("A2")
    assert len(dms) == 1
    assert dms[0].content == "hi"


def test_give_updates_both_stores():
    store, board, bus, events = _setup()
    store.init_agent("A1")
    store.init_agent("A2")
    store.set("A1", "inventory", {"flour": 10, "water": 0, "bread": 0})
    agent = Agent(handle="A1", role="flour_forager")
    registry = create_registry(store=store, board=board, bus=bus, events=events)
    result = registry.execute(agent, "give", {"to": "A2", "resource": "flour", "amount": 5})
    assert store.get("A1", "inventory")["flour"] == 5
    assert store.get("A2", "inventory")["flour"] == 5


def test_bake():
    store, board, bus, events = _setup()
    store.init_agent("A1")
    store.set("A1", "inventory", {"flour": 10, "water": 10, "bread": 0})
    agent = Agent(handle="A1", role="baker")
    registry = create_registry(store=store, board=board, bus=bus, events=events)
    result = registry.execute(agent, "bake", {})
    inv = store.get("A1", "inventory")
    assert inv["bread"] > 0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_actions.py -v`
Expected: FAIL — signature mismatch

- [ ] **Step 3: Update ActionRegistry**

The registry now holds references to infrastructure so actions can use them. `execute` returns feedback text.

```python
# conwai/actions.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.events import EventLog
    from conwai.messages import MessageBus
    from conwai.store import ComponentStore


@dataclass
class Action:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
    cost_flat: int = 0
    handler: Callable | None = None

    def tool_schema(self) -> dict:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": {
                    "type": "object",
                    "properties": self.parameters,
                    "required": list(self.parameters.keys()),
                },
            },
        }


class ActionRegistry:
    def __init__(
        self,
        store: ComponentStore,
        board: BulletinBoard,
        bus: MessageBus,
        events: EventLog,
        pool: AgentPool | None = None,
        perception: Perception | None = None,
        tick_state: dict[str, dict] | None = None,
    ):
        self._actions: dict[str, Action] = {}
        self.store = store
        self.board = board
        self.bus = bus
        self.events = events
        self.pool = pool
        self.perception = perception
        self.tick_state = tick_state or {}

    def register(self, action: Action):
        self._actions[action.name] = action

    def get(self, name: str) -> Action | None:
        return self._actions.get(name)

    def tool_definitions(self) -> list[dict]:
        return [a.tool_schema() for a in self._actions.values()]

    def execute(self, agent: Agent, name: str, args: dict) -> str:
        action = self._actions.get(name)
        if not action:
            return f"unknown action: {name}"

        # Check cost
        eco = self.store.get(agent.handle, "economy")
        if action.cost_flat > eco["coins"]:
            return f"not enough coins for {name} ({action.cost_flat} needed, have {int(eco['coins'])})"

        eco["coins"] -= action.cost_flat
        self.store.set(agent.handle, "economy", eco)

        cost_msg = f"{name}: {action.cost_flat} coins spent, {int(eco['coins'])} remaining" if action.cost_flat > 0 else ""

        result = action.handler(agent, self, args) if action.handler else "ok"
        if cost_msg and result:
            return f"{cost_msg}. {result}"
        return cost_msg or result or "ok"
```

- [ ] **Step 4: Rewrite default_actions.py**

All actions use `registry.store`, `registry.board`, `registry.bus` instead of reaching into agent internals. Each returns a feedback string.

The action handlers now receive `(agent, registry, args)` where `registry` provides access to store, board, bus, events, pool, perception, and tick_state. This replaces the old `(agent, ctx, args)` pattern where ctx was the god object.

Key changes per action:
- `forage`: `registry.store.get/set` instead of `agent.flour +=`
- `pay`/`give`: `registry.store.get/set` on both agents. `give` calls `registry.perception.notify(to, ...)` so the recipient hears about it next tick
- `post_to_board`: `registry.board.post()`. Add `recent_by_handle(handle, n)` public method to BulletinBoard for duplicate detection. Iterate `registry.pool.alive()` for @mention reference rewards
- `send_message`: `registry.bus.send()`, DM rate limit via `registry.tick_state`. Give DM recipient coins via `registry.store` + `registry.perception.notify()`
- `bake`: `registry.store.get/set` for inventory
- `inspect`: `registry.store.get` for other agent's game state, `registry.pool.by_handle()` for identity (personality, soul)
- `update_soul`: set `agent.soul` directly (still on Agent identity)
- `update_journal`: `registry.store.get/set` on memory component
- `submit_code`: uses `registry` to access world events
- `wait`: no-op, return "waiting"
- `compact`: **removed** — compaction is brain-internal now
- `sleep`: **removed** — was already broken (Agent had no sleep method)

Foraging lock: action sets `registry.tick_state[handle]["foraging"] = True`. The engine checks this before executing subsequent decisions.

**Event logging**: Every action must call `registry.events.log(handle, type, data)` to preserve the event types the dashboard depends on: `board_post`, `dm_sent`, `forage`, `bake`, `give`, `payment`, `soul_updated`, `inspect`, `code_submitted`, `code_wrong_guess`.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_actions.py -v`
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add conwai/actions.py conwai/default_actions.py tests/test_actions.py
git commit -m "Actions use store and return feedback text"
```

---

### Task 7: Systems Use Store

**Files:**
- Modify: `conwai/systems/decay.py`
- Modify: `conwai/systems/tax.py`
- Modify: `conwai/systems/spoilage.py`
- Modify: `conwai/systems/consumption.py`
- Modify: `conwai/systems/death.py`
- Delete: `conwai/systems/brain.py` (brain orchestration moves to engine)
- Create: `tests/test_systems.py`

Systems take `(agents, store, perception)` instead of Context. They use `store.get()`/`store.set()`. They call `perception.notify()` when agents need to know about changes.

- [ ] **Step 1: Write system tests**

```python
# tests/test_systems.py
from conwai.agent import Agent
from conwai.store import ComponentStore
from conwai.perception import Perception
from conwai.systems.decay import DecaySystem
from conwai.systems.tax import TaxSystem
from conwai.systems.spoilage import SpoilageSystem
from conwai.systems.consumption import ConsumptionSystem


def _setup():
    store = ComponentStore()
    store.register_component("economy", {"coins": 500})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": 0})
    store.register_component("hunger", {"hunger": 100, "thirst": 100})
    perception = Perception()
    return store, perception


def test_decay():
    store, perception = _setup()
    store.init_agent("A1")
    agents = [Agent(handle="A1", role="baker")]
    DecaySystem().tick(agents, store, perception)
    h = store.get("A1", "hunger")
    assert h["hunger"] == 97
    assert h["thirst"] == 97


def test_tax():
    store, perception = _setup()
    store.init_agent("A1")
    agents = [Agent(handle="A1", role="baker")]
    TaxSystem(interval=1).tick(agents, store, perception, tick=1)
    eco = store.get("A1", "economy")
    assert eco["coins"] < 500


def test_spoilage():
    store, perception = _setup()
    store.init_agent("A1")
    store.set("A1", "inventory", {"flour": 0, "water": 0, "bread": 5})
    agents = [Agent(handle="A1", role="baker")]
    SpoilageSystem().tick(agents, store, perception, tick=6)
    inv = store.get("A1", "inventory")
    assert inv["bread"] < 5


def test_consumption_eats_when_hungry():
    store, perception = _setup()
    store.init_agent("A1")
    store.set("A1", "hunger", {"hunger": 20, "thirst": 100})
    store.set("A1", "inventory", {"flour": 0, "water": 0, "bread": 3})
    agents = [Agent(handle="A1", role="baker")]
    ConsumptionSystem().tick(agents, store, perception)
    h = store.get("A1", "hunger")
    assert h["hunger"] > 20
    inv = store.get("A1", "inventory")
    assert inv["bread"] < 3
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_systems.py -v`

- [ ] **Step 3: Rewrite systems**

Each system follows the same pattern: `tick(agents, store, perception, tick=None)`. Read state from store, modify, write back, notify perception when agents should hear about changes.

Example — DecaySystem:
```python
class DecaySystem:
    name = "decay"

    def tick(self, agents, store, perception):
        for agent in agents:
            h = store.get(agent.handle, "hunger")
            h["hunger"] = max(0, h["hunger"] - config.HUNGER_DECAY_PER_TICK)
            h["thirst"] = max(0, h["thirst"] - config.THIRST_DECAY_PER_TICK)
            store.set(agent.handle, "hunger", h)
            inv = store.get(agent.handle, "inventory")
            inv["water"] += config.PASSIVE_WATER_PER_TICK
            store.set(agent.handle, "inventory", inv)
```

Same pattern for Tax, Spoilage, Consumption. Death system also uses pool and board for lifecycle management.

Delete `conwai/systems/brain.py` — brain orchestration is now in the engine.

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_systems.py -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/systems/ tests/test_systems.py
git rm conwai/systems/brain.py
git commit -m "Systems use ComponentStore, notify via Perception"
```

---

### Task 8: Engine + main.py

**Files:**
- Modify: `conwai/engine.py` (rewrite)
- Modify: `main.py` (rewrite)
- Modify: `conwai/world.py` (becomes a system)

Engine now orchestrates the full tick: pre-brain systems, then per-agent perception → decide → execute → observe, then post-brain systems, then persist.

- [ ] **Step 1: Rewrite Engine**

```python
# conwai/engine.py
from __future__ import annotations

import asyncio
import logging
import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.actions import ActionRegistry
    from conwai.agent import Agent
    from conwai.brain import Brain
    from conwai.perception import Perception
    from conwai.pool import AgentPool
    from conwai.store import ComponentStore

log = logging.getLogger("conwai")


class Engine:
    def __init__(
        self,
        pool: AgentPool,
        store: ComponentStore,
        perception: Perception,
        actions: ActionRegistry,
        brains: dict[str, Brain],
    ):
        self.pool = pool
        self.store = store
        self.perception = perception
        self.actions = actions
        self.brains = brains
        self._pre_brain_systems: list = []
        self._post_brain_systems: list = []

    def register_pre_brain(self, system) -> None:
        self._pre_brain_systems.append(system)

    def register_post_brain(self, system) -> None:
        self._post_brain_systems.append(system)

    async def tick(self, tick: int, board, bus) -> None:
        agents = self.pool.alive()

        # Reset tick state on the action registry
        self.actions.tick_state = {a.handle: {} for a in agents}

        # Pre-brain systems
        for system in self._pre_brain_systems:
            system.tick(agents, self.store, self.perception, tick=tick)

        # Brain loop — parallel per agent
        tasks = []
        for agent in agents:
            brain = self.brains.get(agent.handle)
            if brain:
                tasks.append(asyncio.create_task(
                    self._tick_agent(agent, brain, board, bus, tick)
                ))
        await asyncio.gather(*tasks)

        # Post-brain systems
        agents = self.pool.alive()  # refresh — deaths may have occurred
        for system in self._post_brain_systems:
            system.tick(agents, self.store, self.perception, tick=tick)

        # Persist
        self.pool.save_all()
        for handle, brain in self.brains.items():
            if hasattr(brain, 'get_state'):
                state_path = Path(f"data/agents/{handle}/context.json")
                state_path.parent.mkdir(parents=True, exist_ok=True)
                state_path.write_text(json.dumps(brain.get_state()))

    async def _tick_agent(self, agent, brain, board, bus, tick):
        start = time.monotonic()

        # Build perception and identity
        text = self.perception.build(agent, self.store, board, bus, tick)
        identity = self.perception.build_identity(agent, self.store)

        # Get decisions from brain
        decisions = await brain.decide(agent, text, identity=identity, tick=tick)

        # Execute each decision
        for decision in decisions:
            # Check foraging lock
            ts = self.actions.tick_state.get(agent.handle, {})
            if ts.get("foraging") and decision.action != "compact":
                brain.observe(decision, "You are foraging this tick and cannot take other actions.")
                continue

            result = self.actions.execute(agent, decision.action, decision.args)
            brain.observe(decision, result)

        log.info(f"[{agent.handle}] tick {tick} took {time.monotonic() - start:.1f}s")
```

- [ ] **Step 2: Convert WorldEvents to a system**

WorldEvents.tick takes `(agents, store, perception, board, bus, pool, tick)` — it needs more than other systems because it posts to the board, sends DMs, and modifies agent memory components. Update its tick method to use store instead of agent fields for code_fragment (store it in the memory component).

- [ ] **Step 3: Rewrite main.py**

Wire everything together:
1. Create ComponentStore, register components (economy, inventory, hunger, memory)
2. Create infrastructure (board, bus, events)
3. Create repo, pool, perception
4. Load or create agents
5. Create brains, wire to agents
6. Create action registry with store/board/bus/events
7. Create engine, register systems
8. Run tick loop

```python
# main.py (key wiring section)
async def main():
    setup_logging()

    store = ComponentStore()
    store.register_component("economy", {"coins": config.ENERGY_MAX})
    store.register_component("inventory", {"flour": 0, "water": 0, "bread": config.STARTING_BREAD})
    store.register_component("hunger", {"hunger": config.HUNGER_MAX, "thirst": config.HUNGER_MAX})
    store.register_component("memory", {"memory": "", "code_fragment": None})

    board = BulletinBoard(max_posts=config.BOARD_MAX_POSTS, max_post_length=config.BOARD_MAX_POST_LENGTH)
    bus = MessageBus()
    events = EventLog()
    perception = Perception()

    repo = AgentRepository()
    pool = AgentPool(repo, bus, store)

    # Load or create agents
    brains = {}
    roles = ["flour_forager"] * 3 + ["water_forager"] * 3 + ["baker"] * 2
    for i, role in enumerate(roles, 1):
        agent = pool.load_or_create(f"A{i}", role, born_tick=0)
        if agent.alive:
            brain = LLMBrain(
                core=qwen9b0, compactor=qwen9b1, actions=registry,
                system_prompt=perception.build_system_prompt(),
            )
            # Load brain state if it exists
            ctx_path = Path(f"data/agents/{agent.handle}/context.json")
            if ctx_path.exists():
                brain.load_state(json.loads(ctx_path.read_text()))
            brains[agent.handle] = brain

    registry = create_registry(store=store, board=board, bus=bus, events=events)

    engine = Engine(pool=pool, store=store, perception=perception, actions=registry, brains=brains)
    engine.register_pre_brain(DecaySystem())
    engine.register_pre_brain(TaxSystem())
    engine.register_pre_brain(SpoilageSystem())
    engine.register_pre_brain(DeathSystem(pool=pool, board=board, events=events, brains=brains, on_create_brain=...))
    engine.register_post_brain(ConsumptionSystem())

    # Handler file watcher (admin controls from dashboard)
    # Port watch_handler_file() to use store instead of agent fields
    asyncio.create_task(watch_handler_file(pool, store, board, bus, events, perception))

    # Tick loop
    tick = load_tick()
    while True:
        config.reload()
        await wait_for_llm(qwen9b0)  # block until LLM is reachable
        tick += 1
        save_tick(tick)
        await engine.tick(tick, board, bus)
```

Port `watch_handler_file` from current main.py — update it to use `store.get()`/`store.set()` instead of `agent.coins`, `agent.coins - amount`, etc. Port `wait_for_llm` unchanged.

- [ ] **Step 4: Run all tests**

Run: `pytest tests/ -v`
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/engine.py conwai/world.py main.py
git commit -m "Engine orchestrates new flow, main.py rewired"
```

---

### Task 9: Dashboard + Brain Persistence

**Files:**
- Modify: `conwai/dashboard.py`

Dashboard's `read_agents()` currently reads individual files from `data/agents/`. Update it to read from the new format (identity.json + component JSON files).

- [ ] **Step 1: Update dashboard to read new format**

`read_agents()` reads `identity.json` for handle/role/personality/soul/alive, and component files for economy/inventory/hunger state. Brain state (context.json) persisted by the engine after each tick via `brain.get_state()`.

- [ ] **Step 2: Verify dashboard API manually**

Run: `uvicorn conwai.dashboard:app --reload` and check `/api/agents`, `/api/status`

- [ ] **Step 3: Commit**

```bash
git add conwai/dashboard.py
git commit -m "Dashboard reads new persistence format"
```

---

### Task 10: Smoke Test Full Simulation

**Files:**
- No new files — integration verification

- [ ] **Step 1: Archive old data**

```bash
mv data data_archive_$(date +%Y%m%d)
mkdir -p data/agents
```

- [ ] **Step 2: Run simulation for 5 ticks**

Start the simulation, watch logs for:
- Agents loading/creating correctly
- ComponentStore initializing with defaults
- Perception building tick messages
- Brain receiving perception, returning decisions
- Actions executing via store
- Systems running (decay, tax, spoilage, consumption)
- Persistence working (stop and restart, state survives)

- [ ] **Step 3: Check dashboard**

Verify dashboard shows agent state, events, economy stats correctly.

- [ ] **Step 4: Run full test suite**

Run: `pytest tests/ -v`
Expected: all PASS

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "Clean layers architecture complete"
```
