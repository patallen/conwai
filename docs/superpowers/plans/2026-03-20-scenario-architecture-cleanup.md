# Scenario Architecture Cleanup

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Clean up the scenario layer so the framework is composable, testable, and ready for additional scenarios without copy-pasting main.py.

**Architecture:** Extract composition logic from main.py into a scenario runner. Split the 627-line actions.py and 390-line world_events.py into focused modules. Replace module-level config globals with a typed dataclass. Add an LLMProvider protocol. Move PerceptionBuilder out of engine.py.

**Tech Stack:** Python 3.14, dataclasses, Protocol, pytest, asyncio

---

## File Structure

### New files
- `conwai/cognition/perception.py` — PerceptionBuilder protocol (moved from engine.py)
- `conwai/llm_protocol.py` — LLMProvider protocol
- `scenarios/bread_economy/runner.py` — Scenario composition and tick loop
- `scenarios/bread_economy/actions/` — Split from monolithic actions.py:
  - `__init__.py` — re-exports create_registry
  - `communication.py` — post_to_board, send_message
  - `economy.py` — pay, give, offer, accept + offer state class
  - `personal.py` — update_soul, update_journal, inspect, wait
  - `crafting.py` — forage, bake
  - `world.py` — submit_code, vote (thin wrappers)
  - `helpers.py` — charge(), _capped_add()
- `scenarios/bread_economy/events/` — Split from world_events.py:
  - `__init__.py` — re-exports WorldEvents
  - `questions.py` — QuestionSystem
  - `elections.py` — ElectionSystem
  - `ciphers.py` — CipherSystem
  - `world.py` — WorldEvents Phase that delegates to sub-systems

### Modified files
- `conwai/engine.py` — remove PerceptionBuilder, import from cognition
- `conwai/llm.py` — no changes to classes, just ensure they satisfy protocol
- `scenarios/bread_economy/config.py` — replace globals with ScenarioConfig dataclass
- `main.py` — thin entry point that calls runner

### Deleted files
- `scenarios/bread_economy/actions.py` — replaced by actions/ package
- `scenarios/bread_economy/world_events.py` — replaced by events/ package

---

## Task 1: Add LLMProvider protocol

**Files:**
- Create: `conwai/llm_protocol.py`
- Modify: `scenarios/bread_economy/processes/inference.py:18-19`
- Test: `tests/test_llm_protocol.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_llm_protocol.py
from conwai.llm import LLMClient, AnthropicLLMClient
from conwai.llm_protocol import LLMProvider


def test_openai_client_satisfies_protocol():
    assert issubclass(LLMClient, LLMProvider) or isinstance(LLMClient.__new__(LLMClient), LLMProvider)


def test_protocol_exists():
    from conwai.llm_protocol import LLMProvider
    assert hasattr(LLMProvider, "call")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_protocol.py -x -v`
Expected: FAIL — no module named conwai.llm_protocol

- [ ] **Step 3: Create the protocol**

```python
# conwai/llm_protocol.py
from __future__ import annotations

from typing import Protocol, runtime_checkable

from conwai.llm import LLMResponse


@runtime_checkable
class LLMProvider(Protocol):
    async def call(
        self, system: str, messages: list[dict], tools: list[dict] | None = None
    ) -> LLMResponse: ...
```

- [ ] **Step 4: Update InferenceProcess type hint**

In `scenarios/bread_economy/processes/inference.py`, change:
```python
from conwai.llm import LLMClient
```
to:
```python
from conwai.llm_protocol import LLMProvider
```
And change `client: LLMClient` to `client: LLMProvider` in `__init__`.

- [ ] **Step 5: Run tests to verify everything passes**

Run: `python -m pytest tests/ -x -q`

- [ ] **Step 6: Commit**

```
git add conwai/llm_protocol.py tests/test_llm_protocol.py scenarios/bread_economy/processes/inference.py
git commit -m "Add LLMProvider protocol, type InferenceProcess generically"
```

---

## Task 2: Move PerceptionBuilder to cognition layer

**Files:**
- Create: `conwai/cognition/perception.py`
- Modify: `conwai/engine.py:9,24-40,48`
- Modify: `conwai/cognition/__init__.py`
- Modify: `scenarios/bread_economy/world_events.py:17`

- [ ] **Step 1: Create cognition/perception.py with the protocol**

```python
# conwai/cognition/perception.py
from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from conwai.cognition.percept import ActionFeedback, Percept

if TYPE_CHECKING:
    from conwai.agent import Agent
    from conwai.bulletin_board import BulletinBoard
    from conwai.messages import MessageBus
    from conwai.store import ComponentStore


class PerceptionBuilder(Protocol):
    """What the engine needs from a perception system."""

    def build(
        self,
        agent: Agent,
        store: ComponentStore,
        board: BulletinBoard,
        bus: MessageBus,
        tick: int,
        action_feedback: list[ActionFeedback] | None = None,
    ) -> Percept: ...

    def notify(self, handle: str, message: str) -> None: ...

    def build_system_prompt(self) -> str: ...
```

- [ ] **Step 2: Update engine.py to import from cognition**

Remove the `PerceptionBuilder` class from engine.py. Replace with:
```python
from conwai.cognition.perception import PerceptionBuilder
```
Remove the `ActionFeedback` and `Percept` runtime imports from engine.py (only needed by PerceptionBuilder which moved). Keep `ActionFeedback` imported since BrainPhase uses it. Actually engine.py still needs ActionFeedback for BrainPhase, so keep that import.

- [ ] **Step 3: Update cognition/__init__.py to export PerceptionBuilder**

Add `PerceptionBuilder` to the exports.

- [ ] **Step 4: Update world_events.py import**

Change:
```python
from conwai.engine import PerceptionBuilder
```
to:
```python
from conwai.cognition.perception import PerceptionBuilder
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/ -x -q`

- [ ] **Step 6: Commit**

```
git add conwai/cognition/perception.py conwai/cognition/__init__.py conwai/engine.py scenarios/bread_economy/world_events.py
git commit -m "Move PerceptionBuilder protocol from engine to cognition layer"
```

---

## Task 3: Replace config globals with typed ScenarioConfig

**Files:**
- Modify: `scenarios/bread_economy/config.py`
- Modify: all scenario files that read `config.SOMETHING`

- [ ] **Step 1: Define ScenarioConfig dataclass**

Replace the `reload()` function and module globals with a dataclass at the top of config.py. Keep `reload()` as a function that returns a new `ScenarioConfig` instance. Store one module-level instance as `_current` and provide a `get_config()` accessor.

```python
# scenarios/bread_economy/config.py
from __future__ import annotations

import random as _random
from dataclasses import dataclass, field

from conwai.config import get, load


@dataclass
class ScenarioConfig:
    # Starting resources
    starting_coins: int = 500
    starting_flour: int = 0
    starting_water: int = 0
    starting_bread: int = 5
    starting_hunger: int = 100
    starting_thirst: int = 100

    # Economy
    energy_max: int = 1000
    energy_cost_flat: dict = field(default_factory=lambda: {"update_soul": 5})
    energy_gain: dict = field(default_factory=lambda: {"referenced": 10, "dm_received": 5})

    # Board
    board_max_posts: int = 30
    board_max_post_length: int = 200

    # Hunger
    hunger_max: int = 100
    hunger_decay_per_tick: int = 3
    hunger_auto_eat_threshold: int = 80
    hunger_eat_restore: int = 15
    hunger_eat_raw_restore: int = 5
    hunger_starve_coin_penalty: int = 10

    # Thirst
    thirst_decay_per_tick: int = 3
    thirst_auto_drink_threshold: int = 80
    thirst_drink_restore: int = 15
    thirst_dehydration_coin_penalty: int = 10
    passive_water_per_tick: int = 0

    # Foraging
    roles: list = field(default_factory=lambda: ["flour_forager", "water_forager", "baker"])
    forage_skill_by_role: dict = field(default_factory=lambda: {
        "flour_forager": {"flour": 4, "water": 1},
        "water_forager": {"flour": 1, "water": 4},
        "baker": {"flour": 1, "water": 1},
    })

    # Inventory
    inventory_cap: int = 100

    # Baking
    bake_cost: dict = field(default_factory=lambda: {"flour": 3, "water": 3})
    bake_yield: int = 2
    bake_baker_yield: int = 3

    # Spoilage
    bread_spoil_interval: int = 6
    bread_spoil_amount: int = 1

    # Brain
    context_window: int = 16000
    memory_max: int = 1000

    # Role descriptions
    role_descriptions: dict = field(default_factory=lambda: {
        "flour_forager": "You automatically forage and bake each tick. Your foraging yields vary — you produce more of some resources than others. Trade to get what you're short on.",
        "water_forager": "You automatically forage and bake each tick. Your foraging yields vary — you produce more of some resources than others. Trade to get what you're short on.",
    })

    raw_cfg: dict = field(default_factory=dict, repr=False)

    @classmethod
    def from_file(cls) -> ScenarioConfig:
        cfg = load()
        return cls(
            starting_coins=get(cfg, "starting", "coins", default=500),
            starting_flour=get(cfg, "starting", "flour", default=0),
            starting_water=get(cfg, "starting", "water", default=0),
            starting_bread=get(cfg, "starting", "bread", default=5),
            starting_hunger=get(cfg, "starting", "hunger", default=100),
            starting_thirst=get(cfg, "starting", "thirst", default=100),
            energy_max=get(cfg, "economy", "max_coins", default=1000),
            energy_cost_flat=get(cfg, "economy", "cost_flat", default={"update_soul": 5}),
            energy_gain=get(cfg, "economy", "gain", default={"referenced": 10, "dm_received": 5}),
            board_max_posts=get(cfg, "board", "max_posts", default=30),
            board_max_post_length=get(cfg, "board", "max_post_length", default=200),
            hunger_max=get(cfg, "hunger", "max", default=100),
            hunger_decay_per_tick=get(cfg, "hunger", "decay_per_tick", default=3),
            hunger_auto_eat_threshold=get(cfg, "hunger", "auto_eat_threshold", default=80),
            hunger_eat_restore=get(cfg, "hunger", "eat_restore", default=15),
            hunger_eat_raw_restore=get(cfg, "hunger", "eat_raw_restore", default=5),
            hunger_starve_coin_penalty=get(cfg, "hunger", "starve_coin_penalty", default=10),
            thirst_decay_per_tick=get(cfg, "thirst", "decay_per_tick", default=3),
            thirst_auto_drink_threshold=get(cfg, "thirst", "auto_drink_threshold", default=80),
            thirst_drink_restore=get(cfg, "thirst", "drink_restore", default=15),
            thirst_dehydration_coin_penalty=get(cfg, "thirst", "dehydration_coin_penalty", default=10),
            passive_water_per_tick=get(cfg, "thirst", "passive_water_per_tick", default=0),
            roles=get(cfg, "foraging", "roles", default=["flour_forager", "water_forager", "baker"]),
            forage_skill_by_role=get(cfg, "foraging", "skill_by_role", default={
                "flour_forager": {"flour": 4, "water": 1},
                "water_forager": {"flour": 1, "water": 4},
                "baker": {"flour": 1, "water": 1},
            }),
            inventory_cap=get(cfg, "inventory", "cap", default=100),
            bake_cost=get(cfg, "baking", "cost", default={"flour": 3, "water": 3}),
            bake_yield=get(cfg, "baking", "yield", default=2),
            bake_baker_yield=get(cfg, "baking", "baker_yield", default=3),
            bread_spoil_interval=get(cfg, "spoilage", "interval", default=6),
            bread_spoil_amount=get(cfg, "spoilage", "amount", default=1),
            context_window=get(cfg, "brain", "context_window", default=16000),
            memory_max=get(cfg, "brain", "memory_max", default=1000),
            role_descriptions=get(cfg, "roles", "descriptions", default={
                "flour_forager": "You automatically forage and bake each tick. Your foraging yields vary — you produce more of some resources than others. Trade to get what you're short on.",
                "water_forager": "You automatically forage and bake each tick. Your foraging yields vary — you produce more of some resources than others. Trade to get what you're short on.",
            }),
            raw_cfg=cfg,
        )
```

Keep `assign_traits()` and `register_components()` as module-level functions — they don't need to be on the config.

Add a module-level accessor pattern:
```python
_current: ScenarioConfig = ScenarioConfig.from_file()


def get_config() -> ScenarioConfig:
    return _current


def reload() -> None:
    global _current
    _current = ScenarioConfig.from_file()
```

- [ ] **Step 2: Update all consumers**

Every file that does `import scenarios.bread_economy.config as config` then `config.HUNGER_DECAY_PER_TICK` needs to change to `config.get_config().hunger_decay_per_tick`.

This is a mechanical find-and-replace across these files:
- `scenarios/bread_economy/systems.py` — all system classes
- `scenarios/bread_economy/actions.py` (or the new actions/ modules if already split)
- `scenarios/bread_economy/perception.py`
- `scenarios/bread_economy/world_events.py` (or events/)
- `main.py`

The pattern: `config.SOME_GLOBAL` becomes `config.get_config().some_field` (lowercase, matching the dataclass field name).

For hot-reload: `config.reload()` in main.py's tick loop stays the same.

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/ -x -q`

- [ ] **Step 4: Commit**

```
git commit -am "Replace config globals with typed ScenarioConfig dataclass"
```

---

## Task 4: Split actions.py into focused modules

**Files:**
- Create: `scenarios/bread_economy/actions/` package (6 files)
- Delete: `scenarios/bread_economy/actions.py` (after moving content)

- [ ] **Step 1: Create the actions package**

Create `scenarios/bread_economy/actions/__init__.py`:
```python
from scenarios.bread_economy.actions.registry import create_registry

__all__ = ["create_registry"]
```

- [ ] **Step 2: Create helpers.py**

Move `charge()` and `_capped_add()` to `scenarios/bread_economy/actions/helpers.py`.

- [ ] **Step 3: Create communication.py**

Move `_post_to_board()` and `_send_message()`.

- [ ] **Step 4: Create personal.py**

Move `_update_soul()`, `_update_journal()`, `_inspect()`, `_wait()`.

- [ ] **Step 5: Create economy.py**

Move `_pay()`, `_give()`, `_offer()`, `_accept()`, and the `_pending_offers`/`_next_offer_id` state. Wrap the offer state in a class:

```python
class OfferBook:
    def __init__(self, expiry: int = 12):
        self.expiry = expiry
        self._next_id = 1
        self._offers: dict[int, dict] = {}

    def expire(self, tick: int) -> None:
        expired = [oid for oid, o in self._offers.items() if tick - o["tick"] >= self.expiry]
        for oid in expired:
            del self._offers[oid]

    def create(self, data: dict) -> int:
        oid = self._next_id
        self._next_id += 1
        self._offers[oid] = data
        return oid

    def get(self, oid: int) -> dict | None:
        return self._offers.get(oid)

    def remove(self, oid: int) -> None:
        self._offers.pop(oid, None)

    def count_by_agent(self, handle: str) -> int:
        return sum(1 for o in self._offers.values() if o["from"] == handle)
```

- [ ] **Step 6: Create crafting.py**

Move `_forage()` and `_bake()`.

- [ ] **Step 7: Create world.py**

Move `_submit_code()` and `_vote()` wrappers.

- [ ] **Step 8: Create registry.py with create_registry()**

The `create_registry()` function imports handlers from each module and registers them. This is the only file that knows about all action modules.

- [ ] **Step 9: Delete old actions.py**

- [ ] **Step 10: Run tests**

Run: `python -m pytest tests/ -x -q`

- [ ] **Step 11: Commit**

```
git commit -am "Split actions.py into focused modules with OfferBook class"
```

---

## Task 5: Split world_events.py into independent systems

**Files:**
- Create: `scenarios/bread_economy/events/` package (4 files)
- Delete: `scenarios/bread_economy/world_events.py`

- [ ] **Step 1: Create the events package**

Create `scenarios/bread_economy/events/__init__.py`:
```python
from scenarios.bread_economy.events.world import WorldEvents

__all__ = ["WorldEvents"]
```

- [ ] **Step 2: Create questions.py**

Extract the question logic into a standalone class:
```python
class QuestionSystem:
    def __init__(self, board, interval: int = 60):
        self._board = board
        self.interval = interval
        self._used: set[int] = set()

    def tick(self, tick: int) -> None:
        if tick == 0 or tick % self.interval != 0:
            return
        self._ask_question()

    def _ask_question(self) -> None:
        ...  # same logic, moved from WorldEvents
```

- [ ] **Step 3: Create elections.py**

Extract election state and logic:
```python
class ElectionSystem:
    def __init__(self, board, store, perception, interval=50, duration=15, reward=200):
        ...

    def tick(self, tick: int) -> None:
        ...

    def cast_vote(self, agent, candidate: str) -> str:
        ...
```

- [ ] **Step 4: Create ciphers.py**

Extract cipher state and logic:
```python
class CipherSystem:
    def __init__(self, board, bus, pool, store, perception, interval=40, reward=300, penalty=10):
        ...

    def tick(self, tick: int) -> None:
        ...

    def submit_code(self, agent, guess: str) -> str:
        ...

    def get_status(self) -> dict | None:
        ...
```

- [ ] **Step 5: Create world.py coordinator**

```python
class WorldEvents:
    name = "world"

    def __init__(self, board, bus, pool, store, perception, **kwargs):
        self.questions = QuestionSystem(board, kwargs.get("question_interval", 60))
        self.elections = ElectionSystem(board, store, perception, ...)
        self.ciphers = CipherSystem(board, bus, pool, store, perception, ...)

    async def run(self, ctx) -> None:
        self.questions.tick(ctx.tick)
        self.ciphers.tick(ctx.tick)
        self.elections.tick(ctx.tick)
        self._save_state()

    # Delegate methods for action handlers
    def submit_code(self, agent, guess): return self.ciphers.submit_code(agent, guess)
    def cast_vote(self, agent, candidate): return self.elections.cast_vote(agent, candidate)
```

- [ ] **Step 6: Update imports in main.py / runner**

- [ ] **Step 7: Delete old world_events.py**

- [ ] **Step 8: Run tests**

Run: `python -m pytest tests/ -x -q`

- [ ] **Step 9: Commit**

```
git commit -am "Split world_events.py into QuestionSystem, ElectionSystem, CipherSystem"
```

---

## Task 6: Extract scenario runner from main.py

**Files:**
- Create: `scenarios/bread_economy/runner.py`
- Modify: `main.py` (shrink to ~15 lines)

- [ ] **Step 1: Create runner.py**

Move all composition logic from main.py into a `BreadEconomyRunner` class or a `setup()` + `run()` pair of functions in runner.py. The runner should:
- Accept a `ScenarioConfig` (or load one)
- Set up store, board, bus, events, perception, repo, pool
- Create the brain factory
- Load/create agents
- Build the engine with all phases
- Start the tick loop and handler watcher

```python
# scenarios/bread_economy/runner.py
async def run(config: ScenarioConfig | None = None) -> None:
    """Run the bread economy scenario."""
    if config is None:
        config = ScenarioConfig.from_file()
    # ... all the setup from main.py ...
    # ... tick loop ...
```

- [ ] **Step 2: Shrink main.py**

```python
# main.py
import asyncio
from conwai.infra.logging import setup_logging
from scenarios.bread_economy.runner import run

if __name__ == "__main__":
    setup_logging()
    asyncio.run(run())
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/ -x -q`

- [ ] **Step 4: Commit**

```
git commit -am "Extract scenario runner, shrink main.py to entry point"
```

---

## Execution Notes

- Tasks 1 and 2 are independent — can run in parallel
- Task 3 (config) should run before Tasks 4 and 5, since the split modules will reference the new config pattern
- Tasks 4 and 5 are independent of each other — can run in parallel after Task 3
- Task 6 depends on all prior tasks being complete
