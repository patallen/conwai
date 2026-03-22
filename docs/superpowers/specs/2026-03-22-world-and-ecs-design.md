# World and ECS Rework

## Problem

The engine passes a `TickContext` god object to every system. It bundles the agent pool, component store, perception builder, bulletin board, message bus, and event log into a single dataclass with optional fields. Every system gets access to everything regardless of what it needs. The engine constructor takes scenario-specific arguments (board, bus, events) that don't belong in the framework.

Meanwhile, `AgentPool` and `ComponentStore` are separate objects that both manage per-entity state. The component store deepcopies on every get/set, requiring awkward round-trip mutations. Entity lifecycle (alive/dead) is tracked in the pool, outside the ECS.

## Design

### World

`World` is the single object that holds all simulation state. It replaces `AgentPool`, `ComponentStore`, and the ad-hoc infrastructure fields on `TickContext`/`Engine`.

Three responsibilities:

- **Components** (per-entity, type-keyed): what `ComponentStore` does now
- **Resources** (singleton, type-keyed via TypeMap): replaces the optional fields on TickContext
- **Entities** (lifecycle): what `AgentPool` does now

```python
class World:
    # Components - per-entity typed state
    def get[T: Component](self, entity: str, comp: type[T]) -> T
    def set(self, entity: str, comp: Component) -> None
    def has(self, entity: str, comp: type[Component]) -> bool

    # Resources - singleton typed state (backed by TypeMap)
    def get_resource[T](self, typ: type[T]) -> T
    def set_resource[T](self, val: T) -> None
    def has_resource(self, typ: type) -> bool

    # Entities
    def spawn(self, entity_id: str) -> str
    def destroy(self, entity_id: str) -> None
    def entities(self) -> list[str]

    # Queries
    def query(self, *component_types) -> Iterator[tuple[str, ...]]
```

Entities are just IDs. What makes something an agent is having agent-specific components (brain state, identity, etc.), not being a special type. Non-agent entities (market stalls, world objects) are possible.

Entity destruction tags rather than removes (details deferred). Dead entities can still be inspected.

### Entity initialization

World supports registering component types with defaults. When an entity is spawned, it can receive default components automatically, or components can be set manually after spawn. This replaces `ComponentStore.register()` and `init_agent()`.

```python
# Register defaults (scenario setup)
world.register(Hunger, Hunger(hunger=100, thirst=100))
world.register(Inventory, Inventory())

# Spawn with defaults
world.spawn("agent_alice")  # gets default Hunger, Inventory, etc.

# Spawn with overrides
world.spawn("agent_alice", overrides=[Hunger(hunger=50)])

# Bare entity (no defaults)
world.spawn("market_stall", defaults=False)
world.set("market_stall", Inventory(flour=100))
```

### No deepcopy

Components are returned by reference. Systems mutate in place. No get/set round-trip.

```python
# Current (deepcopy + set back)
h = ctx.store.get(agent.handle, Hunger)
h.hunger -= decay_rate
ctx.store.set(agent.handle, h)

# New (mutate in place)
h = world.get(entity, Hunger)
h.hunger -= decay_rate
```

This matches how every standard ECS works (Bevy, EnTT, esper). The deepcopy was defensive programming that cost ergonomics for no practical benefit given that systems run sequentially.

### Systems

Systems receive World and operate on it. No TickContext.

```python
class System(Protocol):
    name: str
    async def run(self, world: World) -> None: ...
```

Systems query for the components they need rather than iterating a pool:

```python
class DecaySystem:
    name = "decay"

    async def run(self, world: World) -> None:
        for entity, h, inv in world.query(Hunger, Inventory):
            h.hunger = max(0, h.hunger - decay_rate)
            inv.water += passive_water
```

Singleton state accessed via resources:

```python
class TaxSystem:
    name = "tax"

    async def run(self, world: World) -> None:
        tick = world.get_resource(TickNumber)
        if tick.value % self.interval != 0:
            return
        for entity, eco in world.query(Economy):
            ...
```

`BrainPhase` becomes `BrainSystem`, just another system. It queries for entities with brain-related components and runs cognition on them.

### Engine

The engine owns a World, holds systems, runs them sequentially.

```python
class Engine:
    def __init__(self, world: World):
        self.world = world
        self._systems: list[System] = []

    def add_system(self, system: System) -> None:
        self._systems.append(system)

    async def tick(self) -> None:
        for system in self._systems:
            await system.run(self.world)
```

The engine knows nothing about agents, brains, scenarios, or domain concepts. It knows World and Systems.

Tick number is a resource on World. The engine increments it at the start of each tick (or a dedicated system does).

### Resources

Resources are singleton typed state on World, backed by a TypeMap. Scenarios register them at setup.

```python
# Scenario runner registers resources
world.set_resource(BulletinBoard(...))
world.set_resource(MessageBus(...))
world.set_resource(TickNumber(0))
world.set_resource(EventLog(...))
```

The engine never registers or references any resources. It doesn't know what a BulletinBoard is.

### Persistence

- **Components**: persist via storage backend, same as now. Moves from ComponentStore to World.
- **Resources**: data resources serialize (TickNumber, board, bus). Behavior resources (perception builder, action registry) reconstruct on startup.
- **Entities**: the entity list persists. Which entities exist and their state is part of the snapshot.
- **Brain state**: unchanged. BrainSystem loads/saves blackboard state through World's component store.

## Migration mapping

| Current | Becomes |
|---|---|
| `AgentPool` | Entity methods on World |
| `ComponentStore` | Component methods on World |
| `TickContext` | Deleted |
| `Phase` protocol | `System` protocol (`run(world)`) |
| `BrainPhase` | `BrainSystem` |
| `Engine.__init__(pool, store, perception, board, bus, events)` | `Engine.__init__(world)` |
| `ctx.tick` | `world.get_resource(TickNumber)` |
| `ctx.board` | `world.get_resource(BulletinBoard)` |
| `ctx.bus` | `world.resource(MessageBus)` |
| `ctx.events` | `world.resource(EventLog)` |
| `ctx.pool.alive()` | `world.entities()` or query |
| `ctx.store.get(handle, T)` | `world.get(entity, T)` |
| `ctx.store.set(handle, c)` | Mutate in place |
| `Agent.alive` | Component or destruction tag |
| `Agent.born_tick` | Component |
| `ctx.tick_state` | Internal to `ActionRegistry` (not world state) |
| `ctx.perception` | `world.resource(PerceptionBuilder)` or internal to BrainSystem |
| `ComponentStore.register()` | `world.register()` |
| `ComponentStore.init_agent()` | `world.spawn()` with registered defaults |

## Not in scope

- **Typed event system**: separate design. The current stringly-typed EventLog continues as-is.
- **Percept/Blackboard/TypeMap**: unchanged, stays in cognition layer.
- **Declarative system requirements** (reads/writes): future addition. Systems currently have implicit dependencies via what they query.
- **Parallel system execution**: future addition. Sequential for now.
- **Decorator registration** (`@resource`, `@component`): future ergonomic layer.
- **Dead entity tagging**: design deferred. For now, `destroy()` removes the entity.
