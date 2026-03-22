# World and ECS Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace TickContext, AgentPool, and ComponentStore with a unified World object that systems query directly.

**Architecture:** World holds all simulation state: per-entity components (type-keyed), singleton resources (TypeMap), and entity lifecycle. Systems receive World and query what they need. Engine becomes `Engine(world)` + a list of systems. TickContext is deleted.

**Tech Stack:** Python 3.12+, dataclasses, pytest, sqlite (existing storage layer)

**Spec:** `docs/superpowers/specs/2026-03-22-world-and-ecs-design.md`

---

## File Structure

**Create:**
- `conwai/world.py` - World class (components, resources, entities, queries, persistence)
- `tests/test_world.py` - World tests

**Modify (framework):**
- `conwai/engine.py` - Engine takes World, System protocol replaces Phase, BrainPhase -> BrainSystem
- `conwai/actions.py` - ActionRegistry uses World instead of TickContext
- `conwai/cognition/perception.py` - PerceptionBuilder protocol takes (entity_id, world)

**Modify (bread economy scenario):**
- `scenarios/bread_economy/systems.py` - All systems: `run(world)` instead of `run(ctx)`
- `scenarios/bread_economy/perception.py` - BreadPerceptionBuilder uses World
- `scenarios/bread_economy/actions/economy.py` - Handlers take (entity_id, world, args)
- `scenarios/bread_economy/actions/personal.py` - Same
- `scenarios/bread_economy/actions/communication.py` - Same
- `scenarios/bread_economy/actions/crafting.py` - Same
- `scenarios/bread_economy/actions/world.py` - Same
- `scenarios/bread_economy/actions/helpers.py` - `charge()` takes World instead of store
- `scenarios/bread_economy/actions/registry.py` - Wiring changes
- `scenarios/bread_economy/events/world.py` - WorldEvents uses World
- `scenarios/bread_economy/events/elections.py` - ElectionSystem uses World
- `scenarios/bread_economy/events/ciphers.py` - CipherSystem uses World
- `scenarios/bread_economy/events/questions.py` - QuestionSystem uses World
- `scenarios/bread_economy/runner.py` - Wire through World
- `scenarios/bread_economy/dashboard.py` - Read from World if needed

**Modify (workbench scenario):**
- `scenarios/workbench/actions.py` - Handlers take (entity_id, world, args)
- `scenarios/workbench/perception.py` - Uses World
- `scenarios/workbench/runner.py` - Wire through World

**Modify (harness):**
- `harness.py` - Uses World

**Modify (tests):**
- `tests/test_systems.py` - Use World instead of TickContext
- `tests/test_actions.py` - Use World instead of TickContext
- `tests/test_perception.py` - Use World
- `tests/test_store.py` - Replace with test_world.py or update
- `tests/test_pool.py` - Replace with World entity tests
- `tests/test_workbench_actions.py` - Use World
- `tests/test_workbench_perception.py` - Use World
- `tests/test_blackboard.py` - Update BrainState tests to use World
- `tests/test_storage.py` - Remove `test_store_write_through` and `test_store_load_all` (they use ComponentStore; covered by test_world.py). Keep pure SQLiteStorage tests.
- `tests/test_repository.py` - Update or remove

**Delete (after migration):**
- `conwai/pool.py` - Absorbed into World
- `conwai/store.py` - Absorbed into World
- `conwai/agent.py` - Entity is just an ID now
- `conwai/repository.py` - Absorbed into World
- `tests/test_pool.py` - Replaced by test_world.py
- `tests/test_store.py` - Replaced by test_world.py
- `tests/test_agent.py` - Entity is just a string
- `tests/test_repository.py` - Absorbed

---

### Task 1: Create World class with component storage

**Files:**
- Create: `conwai/world.py`
- Create: `tests/test_world.py`

- [ ] **Step 1: Write failing tests for component get/set/has**

```python
# tests/test_world.py
from dataclasses import dataclass
from conwai.component import Component
from conwai.world import World


@dataclass
class Health(Component):
    hp: int = 100


@dataclass
class Position(Component):
    x: int = 0
    y: int = 0


def test_set_and_get_component():
    world = World()
    world.spawn("e1")
    world.set("e1", Health(hp=50))
    h = world.get("e1", Health)
    assert h.hp == 50


def test_has_component():
    world = World()
    world.spawn("e1")
    assert not world.has("e1", Health)
    world.set("e1", Health())
    assert world.has("e1", Health)


def test_get_returns_reference_not_copy():
    world = World()
    world.spawn("e1")
    world.set("e1", Health(hp=100))
    h = world.get("e1", Health)
    h.hp = 50
    assert world.get("e1", Health).hp == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_world.py -v`
Expected: FAIL (module not found)

- [ ] **Step 3: Implement World with component storage**

```python
# conwai/world.py
from __future__ import annotations

import logging
from copy import deepcopy
from typing import TYPE_CHECKING

from conwai.component import Component

if TYPE_CHECKING:
    from conwai.storage import Storage

log = logging.getLogger("conwai")


class World:
    def __init__(self, storage: Storage | None = None):
        self._entities: set[str] = set()
        self._components: dict[str, dict[type, Component]] = {}
        self._defaults: dict[type, Component] = {}
        self._types: dict[str, type[Component]] = {}
        self._resources: dict[type, object] = {}
        self._storage = storage

    # -- Components ----------------------------------------------------------

    def get[T: Component](self, entity: str, comp: type[T]) -> T:
        return self._components[entity][comp]  # type: ignore[return-value]

    def set(self, entity: str, comp: Component) -> None:
        if entity not in self._entities:
            raise KeyError(f"Entity {entity!r} does not exist")
        self._components[entity][type(comp)] = comp
        if self._storage:
            self._storage.save_component(
                entity, type(comp).component_name(), comp.to_dict()
            )

    def has(self, entity: str, comp: type[Component]) -> bool:
        return entity in self._components and comp in self._components[entity]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_world.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/world.py tests/test_world.py
git commit -m "Add World class with component storage"
```

---

### Task 2: Add entity lifecycle and registration

**Files:**
- Modify: `conwai/world.py`
- Modify: `tests/test_world.py`

- [ ] **Step 1: Write failing tests for spawn, destroy, entities, register**

```python
def test_spawn_and_entities():
    world = World()
    world.spawn("e1")
    world.spawn("e2")
    assert set(world.entities()) == {"e1", "e2"}


def test_destroy_removes_entity():
    world = World()
    world.spawn("e1")
    world.destroy("e1")
    assert "e1" not in world.entities()


def test_register_defaults():
    world = World()
    world.register(Health, Health(hp=50))
    world.spawn("e1")
    assert world.get("e1", Health).hp == 50


def test_spawn_with_overrides():
    world = World()
    world.register(Health, Health(hp=50))
    world.register(Position, Position(x=0, y=0))
    world.spawn("e1", overrides=[Health(hp=99)])
    assert world.get("e1", Health).hp == 99
    assert world.get("e1", Position).x == 0


def test_spawn_without_defaults():
    world = World()
    world.register(Health, Health(hp=50))
    world.spawn("e1", defaults=False)
    assert not world.has("e1", Health)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_world.py -v`
Expected: FAIL

- [ ] **Step 3: Implement entity lifecycle and registration**

Add to `World` class:

```python
    # -- Registration --------------------------------------------------------

    def register[T: Component](self, comp_type: type[T], default: T | None = None) -> None:
        self._defaults[comp_type] = default if default is not None else comp_type()
        self._types[comp_type.component_name()] = comp_type

    # -- Entities ------------------------------------------------------------

    def spawn(
        self,
        entity_id: str,
        overrides: list[Component] | None = None,
        defaults: bool = True,
    ) -> str:
        self._entities.add(entity_id)
        self._components[entity_id] = {}
        if defaults:
            override_map = {type(c): c for c in (overrides or [])}
            for comp_type, default in self._defaults.items():
                comp = override_map.get(comp_type, deepcopy(default))
                self.set(entity_id, comp)
        return entity_id

    def destroy(self, entity_id: str) -> None:
        self._entities.discard(entity_id)
        self._components.pop(entity_id, None)

    def entities(self) -> list[str]:
        return list(self._entities)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_world.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/world.py tests/test_world.py
git commit -m "Add entity lifecycle and component registration to World"
```

---

### Task 3: Add resources and queries

**Files:**
- Modify: `conwai/world.py`
- Modify: `tests/test_world.py`

- [ ] **Step 1: Write failing tests for resources and queries**

```python
@dataclass
class TickNumber:
    value: int = 0


def test_set_and_get_resource():
    world = World()
    world.set_resource(TickNumber(42))
    assert world.get_resource(TickNumber).value == 42


def test_has_resource():
    world = World()
    assert not world.has_resource(TickNumber)
    world.set_resource(TickNumber(0))
    assert world.has_resource(TickNumber)


def test_resource_returns_reference():
    world = World()
    world.set_resource(TickNumber(0))
    t = world.get_resource(TickNumber)
    t.value = 5
    assert world.get_resource(TickNumber).value == 5


def test_query_single_component():
    world = World()
    world.spawn("e1", defaults=False)
    world.spawn("e2", defaults=False)
    world.set("e1", Health(hp=10))
    world.set("e2", Health(hp=20))
    results = list(world.query(Health))
    assert len(results) == 2
    entities = {r[0] for r in results}
    assert entities == {"e1", "e2"}


def test_query_multiple_components():
    world = World()
    world.spawn("e1", defaults=False)
    world.spawn("e2", defaults=False)
    world.set("e1", Health(hp=10))
    world.set("e1", Position(x=1, y=2))
    world.set("e2", Health(hp=20))  # no Position
    results = list(world.query(Health, Position))
    assert len(results) == 1
    entity, h, p = results[0]
    assert entity == "e1"
    assert h.hp == 10
    assert p.x == 1


def test_query_returns_references():
    world = World()
    world.spawn("e1", defaults=False)
    world.set("e1", Health(hp=100))
    for entity, h in world.query(Health):
        h.hp = 50
    assert world.get("e1", Health).hp == 50
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_world.py -v`
Expected: FAIL

- [ ] **Step 3: Implement resources and queries**

Add to `World` class:

```python
    # -- Resources -----------------------------------------------------------

    def get_resource[T](self, typ: type[T]) -> T:
        return self._resources[typ]  # type: ignore[return-value]

    def set_resource[T](self, val: T) -> None:
        self._resources[type(val)] = val

    def has_resource(self, typ: type) -> bool:
        return typ in self._resources

    # -- Queries -------------------------------------------------------------

    def query(self, *component_types: type[Component]):
        for entity_id in self._entities:
            entity_comps = self._components.get(entity_id, {})
            components = []
            for ct in component_types:
                comp = entity_comps.get(ct)
                if comp is None:
                    break
                components.append(comp)
            else:
                yield (entity_id, *components)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_world.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/world.py tests/test_world.py
git commit -m "Add resources and queries to World"
```

---

### Task 4: Add persistence to World

**Files:**
- Modify: `conwai/world.py`
- Modify: `tests/test_world.py`

- [ ] **Step 1: Write failing tests for persistence**

```python
from conwai.storage import SQLiteStorage
from pathlib import Path
import tempfile


def test_set_persists_to_storage(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    world = World(storage=storage)
    world.spawn("e1", defaults=False)
    world.set("e1", Health(hp=42))
    data = storage.load_component("e1", "health")
    assert data == {"hp": 42}


def test_load_all_restores_state(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    # Save state
    world1 = World(storage=storage)
    world1.register(Health)
    world1.spawn("e1", defaults=False)
    world1.set("e1", Health(hp=42))

    # Load into fresh world
    world2 = World(storage=storage)
    world2.register(Health)
    world2.load_all()
    assert "e1" in world2.entities()
    assert world2.get("e1", Health).hp == 42


def test_destroy_persists(tmp_path):
    storage = SQLiteStorage(tmp_path / "test.db")
    world = World(storage=storage)
    world.register(Health)
    world.spawn("e1")
    world.destroy("e1")
    # Fresh load should not find entity
    world2 = World(storage=storage)
    world2.register(Health)
    world2.load_all()
    assert "e1" not in world2.entities()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_world.py::test_load_all_restores_state -v`
Expected: FAIL (load_all not implemented)

- [ ] **Step 3: Implement persistence**

Add to `World` class:

```python
    # -- Persistence ---------------------------------------------------------

    def load_all(self) -> None:
        if not self._storage:
            return
        for entity_id in self._storage.list_entities():
            self._entities.add(entity_id)
            if entity_id not in self._components:
                self._components[entity_id] = {}
            for comp_name in self._storage.list_components(entity_id):
                comp_type = self._types.get(comp_name)
                if comp_type is None:
                    continue
                data = self._storage.load_component(entity_id, comp_name)
                if data is not None:
                    self._components[entity_id][comp_type] = comp_type.from_dict(data)
```

Update `destroy()` to also remove from storage:

```python
    def destroy(self, entity_id: str) -> None:
        self._entities.discard(entity_id)
        self._components.pop(entity_id, None)
        if self._storage:
            for comp_name in self._storage.list_components(entity_id):
                # Clear persisted components so entity doesn't reload
                self._storage.save_component(entity_id, comp_name, {"_destroyed": True})
```

Note: The exact destruction persistence strategy is deferred per spec. For now, marking components signals the entity is gone. A cleaner approach (delete rows, or a dedicated entity table) can come later.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_world.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/world.py tests/test_world.py
git commit -m "Add persistence to World"
```

---

### Task 5: Update Engine and System protocol

**Files:**
- Modify: `conwai/engine.py`
- Reference: `conwai/world.py`

- [ ] **Step 1: Update Engine to use World and rename Phase to System**

Replace `conwai/engine.py` contents. Key changes:
- Delete `TickContext` dataclass
- Rename `Phase` protocol to `System` with `run(self, world: World)`
- `Engine.__init__` takes `World` only
- `Engine.tick()` takes no args, increments a `TickNumber` resource
- Keep `BrainPhase` as `BrainSystem` (updated in next task)

```python
# conwai/engine.py
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from conwai.cognition.percept import ActionFeedback
from conwai.cognition.types import BrainState
from conwai.processes.types import WorkingMemory

if TYPE_CHECKING:
    from conwai.actions import ActionRegistry
    from conwai.cognition.blackboard import BlackboardBrain
    from conwai.cognition.perception import PerceptionBuilder
    from conwai.typemap import Percept
    from conwai.world import World

log = logging.getLogger("conwai")


@dataclass
class TickNumber:
    value: int = 0


@runtime_checkable
class System(Protocol):
    name: str

    async def run(self, world: World) -> None: ...


class BrainSystem:
    name = "brain"

    def __init__(
        self,
        actions: ActionRegistry,
        brains: dict[str, BlackboardBrain],
        perception: PerceptionBuilder,
    ):
        self.actions = actions
        self.brains = brains
        self.perception = perception
        self._action_feedback: dict[str, list[ActionFeedback]] = {}

    async def run(self, world: World) -> None:
        alive = world.entities()
        alive_set = set(alive)
        self._action_feedback = {
            h: fb for h, fb in self._action_feedback.items() if h in alive_set
        }
        self.actions.begin_tick(world, [h for h in alive if h in self.brains])
        tasks = [
            asyncio.create_task(self._tick_agent(handle, world))
            for handle in alive
            if handle in self.brains
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for handle, result in zip(
            [h for h in alive if h in self.brains], results
        ):
            if isinstance(result, Exception):
                log.error(f"[{handle}] brain error: {result}")

    async def _tick_agent(self, handle: str, world: World) -> None:
        start = time.monotonic()
        brain = self.brains[handle]
        feedback = self._action_feedback.pop(handle, [])

        tick = world.get_resource(TickNumber)
        percept: Percept = self.perception.build(handle, world, action_feedback=feedback)

        if not brain.bb.has(WorkingMemory):
            if world.has(handle, BrainState):
                world.get(handle, BrainState).load_into(brain.bb)

        decisions = await brain.think(percept)

        world.set(handle, BrainState.save_from(brain.bb))

        tick_feedback: list[ActionFeedback] = []
        for decision in decisions:
            result = self.actions.execute(handle, decision.action, decision.args, world)
            tick_feedback.append(ActionFeedback(
                action=decision.action,
                args=decision.args,
                result=result,
            ))

        if tick_feedback:
            self._action_feedback[handle] = tick_feedback

        log.info(f"[{handle}] tick {tick.value} took {time.monotonic() - start:.1f}s")


class Engine:
    def __init__(self, world: World):
        self.world = world
        self._systems: list[System] = []

    def add_system(self, system: System) -> None:
        self._systems.append(system)
        log.info(f"[ENGINE] registered system: {system.name}")

    async def tick(self) -> None:
        tick = self.world.get_resource(TickNumber)
        tick.value += 1
        log.info(f"[ENGINE] tick {tick.value}")

        for system in self._systems:
            await system.run(self.world)
```

- [ ] **Step 2: Verify the module imports cleanly**

Run: `uv run python -c "from conwai.engine import Engine, System, BrainSystem, TickNumber; print('ok')"`
Expected: "ok"

- [ ] **Step 3: Commit**

```bash
git add conwai/engine.py
git commit -m "Replace TickContext with World in Engine, rename Phase to System"
```

---

### Task 6: Update ActionRegistry

**Files:**
- Modify: `conwai/actions.py`

- [ ] **Step 1: Update ActionRegistry to use World instead of TickContext**

Key changes:
- `begin_tick(world, handles)` - tick_state becomes internal dict, tick read from world
- `execute(entity_id, name, args, world)` - takes entity string, not Agent
- `Action.handler` callable signature: `(entity_id: str, world: World, args: dict) -> str`

```python
# conwai/actions.py
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from conwai.world import World


@dataclass
class Action:
    name: str
    description: str
    parameters: dict = field(default_factory=dict)
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
    def __init__(self):
        self._actions: dict[str, Action] = {}
        self._tick_state: dict[str, dict] = {}

    def register(self, action: Action):
        self._actions[action.name] = action

    def get(self, name: str) -> Action | None:
        return self._actions.get(name)

    def tool_definitions(self) -> list[dict]:
        return [a.tool_schema() for a in self._actions.values()]

    def begin_tick(self, world: World, handles: list[str]) -> None:
        self._tick_state = {h: {} for h in handles}

    def execute(self, entity_id: str, name: str, args: dict, world: World) -> str:
        action = self._actions.get(name)
        if not action:
            return f"unknown action: {name}"

        ts = self._tick_state.get(entity_id, {})
        if ts.get("blocked"):
            return ts["blocked"]

        result = action.handler(entity_id, world, args) if action.handler else "ok"
        return result or "ok"
```

- [ ] **Step 2: Verify module imports**

Run: `uv run python -c "from conwai.actions import ActionRegistry, Action; print('ok')"`
Expected: "ok"

- [ ] **Step 3: Commit**

```bash
git add conwai/actions.py
git commit -m "Update ActionRegistry to use World instead of TickContext"
```

---

### Task 7: Update PerceptionBuilder protocol

**Files:**
- Modify: `conwai/cognition/perception.py`

- [ ] **Step 1: Update the PerceptionBuilder protocol**

The protocol signature changes from `(agent, store, board, bus, tick, action_feedback)` to `(entity_id, world, action_feedback)`.

Read current file and update the `build` method signature in the protocol. The protocol is likely minimal - just update it.

```python
class PerceptionBuilder(Protocol):
    def build(
        self,
        entity_id: str,
        world: World,
        action_feedback: list[ActionFeedback] | None = None,
    ) -> Percept: ...

    def notify(self, handle: str, message: str) -> None: ...

    def build_system_prompt(self) -> str: ...
```

`notify` and `build_system_prompt` signatures are unchanged (they don't take store/pool/ctx). Only `build` changes.

- [ ] **Step 2: Commit**

```bash
git add conwai/cognition/perception.py
git commit -m "Update PerceptionBuilder protocol to take (entity_id, world)"
```

---

### Task 8: Migrate bread economy perception builder

**Files:**
- Modify: `scenarios/bread_economy/perception.py`

- [ ] **Step 1: Update BreadPerceptionBuilder.build() signature and body**

Change `build(self, agent, store, board, bus, tick, action_feedback)` to `build(self, entity_id, world, action_feedback)`.

Inside the method:
- `agent.handle` -> `entity_id`
- `store.get(agent.handle, X)` -> `world.get(entity_id, X)`
- `board.read_new(agent.handle)` -> `world.get_resource(BulletinBoard).read_new(entity_id)`
- `bus.receive(agent.handle)` -> `world.get_resource(MessageBus).receive(entity_id)`
- `tick` -> `world.get_resource(TickNumber).value`

Also update `build_identity(self, agent, store)` to `build_identity(self, entity_id, world)`.

Update imports: remove `Agent`, `ComponentStore`. Add `World`, `TickNumber`, `BulletinBoard`, `MessageBus`.

- [ ] **Step 2: Commit**

```bash
git add scenarios/bread_economy/perception.py
git commit -m "Migrate BreadPerceptionBuilder to use World"
```

---

### Task 9: Migrate bread economy action handlers

**Files:**
- Modify: `scenarios/bread_economy/actions/crafting.py`
- Modify: `scenarios/bread_economy/actions/economy.py`
- Modify: `scenarios/bread_economy/actions/personal.py`
- Modify: `scenarios/bread_economy/actions/communication.py`
- Modify: `scenarios/bread_economy/actions/world.py`
- Modify: `scenarios/bread_economy/actions/helpers.py`
- Modify: `scenarios/bread_economy/actions/registry.py`

- [ ] **Step 1: Update all action handler signatures**

Every handler changes from `(agent: Agent, ctx: TickContext, args: dict)` to `(entity_id: str, world: World, args: dict)`.

Inside each handler:
- `agent.handle` -> `entity_id`
- `ctx.store.get(entity_id, X)` -> `world.get(entity_id, X)`
- `ctx.store.set(entity_id, X)` -> mutate in place (remove set calls for components you already hold a reference to, keep set for fresh components)
- `ctx.pool.alive()` -> `world.entities()`
- `ctx.pool.by_handle(h)` -> check `h in world.entities()`
- `ctx.board.post(...)` -> `world.get_resource(BulletinBoard).post(...)`
- `ctx.bus.send(...)` -> `world.get_resource(MessageBus).send(...)`
- `ctx.events.log(...)` -> `world.get_resource(EventLog).log(...)`
- `ctx.perception.notify(...)` -> `world.get_resource(PerceptionBuilder).notify(...)`
- `ctx.tick` -> `world.get_resource(TickNumber).value`
- `ctx.tick_state` -> `world.get_resource(ActionRegistry)._tick_state` or pass tick_state through ActionRegistry

**Note on tick_state:** Currently action handlers in `communication.py` and `crafting.py` access `ctx.tick_state` to mark agents as blocked. Since tick_state is now internal to ActionRegistry, these handlers need a way to set it. Options:
- ActionRegistry passes tick_state as a 4th arg to handlers
- Handlers call `world.get_resource(ActionRegistry)._tick_state[entity_id]["blocked"] = msg`
- ActionRegistry exposes a `block(entity_id, msg)` method

Also update `scenarios/bread_economy/actions/helpers.py`:
- `charge(store, handle, amount, reason)` -> `charge(world, entity_id, amount, reason)`
- `store.get(handle, Economy)` -> `world.get(entity_id, Economy)`
- Remove `store.set()` call (mutate in place - the `eco` reference is already modified)

Use the `block()` method approach - add to ActionRegistry:

```python
def block(self, entity_id: str, reason: str) -> None:
    if entity_id in self._tick_state:
        self._tick_state[entity_id]["blocked"] = reason
```

Then handlers call `world.get_resource(ActionRegistry).block(entity_id, msg)`.

For this to work, ActionRegistry must be registered as a resource:
```python
world.set_resource(actions)  # in runner setup
```

- [ ] **Step 2: Update registry.py wiring**

The action registry file wires handlers to actions. Update handler references if needed.

- [ ] **Step 3: Verify all action modules import cleanly**

Run: `uv run python -c "from scenarios.bread_economy.actions.crafting import *; print('ok')"`
Repeat for economy, personal, communication, world.

- [ ] **Step 4: Commit**

```bash
git add scenarios/bread_economy/actions/
git commit -m "Migrate bread economy action handlers to use World"
```

---

### Task 10: Migrate bread economy systems

**Files:**
- Modify: `scenarios/bread_economy/systems.py`

- [ ] **Step 1: Update all system signatures from `run(ctx)` to `run(world)`**

For each system:
- `async def run(self, ctx: TickContext)` -> `async def run(self, world: World)`
- `ctx.pool.alive()` -> iterate via `world.query(ComponentTypes)`
- `ctx.store.get(handle, X)` -> `world.get(handle, X)` or via query results
- `ctx.store.set(handle, X)` -> remove (mutate in place)
- `ctx.tick` -> `world.get_resource(TickNumber).value`
- `ctx.perception.notify(h, msg)` -> `world.get_resource(PerceptionBuilder).notify(h, msg)` (import the concrete type used)
- `ctx.pool.kill(h)` -> `world.destroy(h)`

Example - DecaySystem:
```python
class DecaySystem:
    name = "decay"

    async def run(self, world: World) -> None:
        cfg = get_config()
        for entity, h, inv in world.query(Hunger, Inventory):
            h.hunger = max(0, h.hunger - cfg.hunger_decay_per_tick)
            h.thirst = max(0, h.thirst - cfg.thirst_decay_per_tick)
            inv.water += cfg.passive_water_per_tick
```

Example - TaxSystem:
```python
class TaxSystem:
    name = "tax"

    def __init__(self, interval: int = 24, rate: float = 0.01):
        self.interval = interval
        self.rate = rate

    async def run(self, world: World) -> None:
        from conwai.engine import TickNumber
        tick = world.get_resource(TickNumber).value
        if tick % self.interval != 0:
            return
        perception = world.get_resource(BreadPerceptionBuilder)
        for entity, eco in world.query(Economy):
            if eco.coins > 0:
                tax = max(1, int(eco.coins * self.rate))
                eco.coins -= tax
                perception.notify(entity, f"coins -{tax} (daily tax)")
        log.info(f"[WORLD] daily tax collected (tick {tick})")
```

Note: Systems that call `ctx.perception.notify()` need to get the perception builder as a resource. The runner will register it: `world.set_resource(perception_builder)`.

For DeathSystem, the `on_death` callback signature changes from `(agent, ctx)` to `(entity_id, world)`.

- [ ] **Step 2: Verify module imports**

Run: `uv run python -c "from scenarios.bread_economy.systems import DecaySystem; print('ok')"`
Expected: "ok"

- [ ] **Step 3: Commit**

```bash
git add scenarios/bread_economy/systems.py
git commit -m "Migrate bread economy systems to use World"
```

---

### Task 11: Migrate bread economy events

**Files:**
- Modify: `scenarios/bread_economy/events/world.py`
- Modify: `scenarios/bread_economy/events/elections.py`
- Modify: `scenarios/bread_economy/events/ciphers.py`
- Modify: `scenarios/bread_economy/events/questions.py`

- [ ] **Step 1: Update WorldEvents to use World**

WorldEvents currently takes board, bus, pool, store, perception in its constructor and wraps sub-systems. Change it to:
- `run(self, world: World)` instead of `run(self, ctx: TickContext)`
- Sub-systems receive World or pull resources from it
- Constructor simplifies: `WorldEvents(world)` or individual sub-systems are initialized with what they need and WorldEvents just coordinates

Read each events file, update constructors and tick methods to use World instead of individual store/pool/board/perception references.

For ElectionSystem and CipherSystem, they currently store references to pool, store, perception, board, bus. Change to store a reference to World (or pull from World in their tick methods).

- [ ] **Step 2: Commit**

```bash
git add scenarios/bread_economy/events/
git commit -m "Migrate bread economy events to use World"
```

---

### Task 12: Migrate bread economy runner

**Files:**
- Modify: `scenarios/bread_economy/runner.py`

- [ ] **Step 1: Update runner to create and wire World**

The runner currently creates: storage, store, repo, pool, board, bus, events, perception, engine. Change to:

1. Create storage (unchanged)
2. Create World with storage
3. Register components on World
4. Register resources on World (board, bus, events, perception, actions)
5. Load or spawn entities via World
6. Create Engine(world)
7. Register systems

Key changes:
- `store = ComponentStore(storage)` -> `world = World(storage=storage)`
- `store.register(X, default)` -> `world.register(X, default)`
- `pool.load_or_create(agent, overrides)` -> `world.spawn(handle, overrides=overrides)` (check if entity exists in storage first via `world.load_all()`)
- `engine = Engine(pool, store, perception, board, bus, events)` -> `engine = Engine(world)`
- `engine.add_phase(system)` -> `engine.add_system(system)`
- BrainSystem constructed with (actions, brains, perception) - same as before

Also update `process_commands()` to use World instead of individual store/pool/etc references.

- [ ] **Step 2: Verify runner imports and initializes**

Run: `uv run python -c "from scenarios.bread_economy.runner import *; print('ok')"`

- [ ] **Step 3: Commit**

```bash
git add scenarios/bread_economy/runner.py
git commit -m "Migrate bread economy runner to use World"
```

---

### Task 13: Migrate workbench scenario

**Files:**
- Modify: `scenarios/workbench/actions.py`
- Modify: `scenarios/workbench/perception.py`
- Modify: `scenarios/workbench/runner.py`

- [ ] **Step 1: Update workbench action handlers**

Same pattern as bread economy: `(agent, ctx, args)` -> `(entity_id, world, args)`.

- [ ] **Step 2: Update workbench perception builder**

Same pattern: `build(agent, store, board, bus, tick, feedback)` -> `build(entity_id, world, feedback)`.

- [ ] **Step 3: Update workbench runner**

Same pattern as bread economy runner: create World, register components/resources, wire engine.

- [ ] **Step 4: Commit**

```bash
git add scenarios/workbench/
git commit -m "Migrate workbench scenario to use World"
```

---

### Task 14: Migrate harness

**Files:**
- Modify: `harness.py`

- [ ] **Step 1: Update harness to use World**

The harness is a single-agent test harness. Same migration pattern as runners:
- Create World instead of separate pool/store
- Register components and resources on World
- Wire through World

- [ ] **Step 2: Commit**

```bash
git add harness.py
git commit -m "Migrate harness to use World"
```

---

### Task 15: Migrate tests

**Files:**
- Modify: `tests/test_systems.py`
- Modify: `tests/test_actions.py`
- Modify: `tests/test_perception.py`
- Modify: `tests/test_workbench_actions.py`
- Modify: `tests/test_workbench_perception.py`
- Modify: `tests/test_blackboard.py`

- [ ] **Step 1: Update test_systems.py**

Replace TickContext creation with World setup:
- Create World, register components, spawn entities, set resources
- Pass World to system.run() instead of TickContext
- Assertions use world.get() instead of ctx.store.get()
- Remove all TickContext, AgentPool, ComponentStore imports

- [ ] **Step 2: Update test_actions.py**

Same pattern: World replaces TickContext in test fixtures.

- [ ] **Step 3: Update test_perception.py**

Perception builders now take (entity_id, world, feedback). Set up World with components and resources.

- [ ] **Step 4: Update test_workbench_actions.py and test_workbench_perception.py**

Same pattern.

- [ ] **Step 5: Update test_blackboard.py**

BrainState tests use World.get/set instead of ComponentStore.

- [ ] **Step 5b: Update test_storage.py**

Remove `test_store_write_through` and `test_store_load_all` (they instantiate ComponentStore which is being deleted). These scenarios are already covered by Task 4's World persistence tests. Keep the pure SQLiteStorage tests (they test the storage layer directly, no ComponentStore).

- [ ] **Step 6: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add tests/
git commit -m "Migrate all tests to use World"
```

---

### Task 16: Delete old code

**Files:**
- Delete: `conwai/pool.py`
- Delete: `conwai/store.py`
- Delete: `conwai/agent.py`
- Delete: `conwai/repository.py`
- Delete: `tests/test_pool.py`
- Delete: `tests/test_store.py`
- Delete: `tests/test_agent.py`
- Delete: `tests/test_repository.py`

- [ ] **Step 1: Verify no remaining imports of old modules**

Run: `grep -r "from conwai.pool\|from conwai.store\|from conwai.agent\|from conwai.repository\|import AgentPool\|import ComponentStore\|import Agent\b\|import AgentRepository" --include="*.py" .`

Fix any remaining references.

- [ ] **Step 2: Delete old files**

```bash
rm conwai/pool.py conwai/store.py conwai/agent.py conwai/repository.py
rm tests/test_pool.py tests/test_store.py tests/test_agent.py tests/test_repository.py
```

- [ ] **Step 3: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 4: Commit**

```bash
git add -A
git commit -m "Remove AgentPool, ComponentStore, Agent, AgentRepository"
```

---

### Task 17: Update dashboard

**Files:**
- Modify: `scenarios/bread_economy/dashboard.py`

- [ ] **Step 1: Update dashboard to read from World or storage directly**

The dashboard currently reads from storage (sqlite) directly via `_storage.load_component()`. This still works since World writes through to the same storage. Check if the dashboard references AgentPool, ComponentStore, or TickContext and update those references.

If the dashboard only reads from storage, minimal changes are needed. If it references pool/store objects, switch to World.

- [ ] **Step 2: Verify dashboard starts**

Run: `uv run python -c "from scenarios.bread_economy.dashboard import *; print('ok')"`

- [ ] **Step 3: Commit**

```bash
git add scenarios/bread_economy/dashboard.py
git commit -m "Update dashboard for World compatibility"
```

---

### Task 18: Final verification and cleanup

- [ ] **Step 1: Run full test suite**

Run: `uv run pytest tests/ -v`
Expected: ALL PASS

- [ ] **Step 2: Run a short simulation**

Run: `uv run python -m scenarios.bread_economy.runner` (or however the sim starts)
Verify agents think and act for a few ticks without errors.

- [ ] **Step 3: Verify no remaining references to deleted concepts**

```bash
grep -r "TickContext\|AgentPool\|ComponentStore\b" --include="*.py" . | grep -v __pycache__ | grep -v test_world
```

Should return nothing (or only comments/docs).

- [ ] **Step 4: Final commit if any cleanup was needed**

```bash
git add -A
git commit -m "Final cleanup for World/ECS rework"
```
