# Clean Layers Architecture

## Problem

Everything reaches into everything else's internals. Agent has methods and ephemeral tick state. Brain reads agent private fields to assemble prompts. Actions access `ctx.board._posts` and mutate agent fields directly. Context is a god object. No boundary between framework and simulation.

## Approach

Clean interfaces between layers. Things use public APIs instead of reaching into each other's guts. No grand abstractions — just boundaries that make sense for a ~2000 line codebase.

## Design

### Agent — Pure Identity

No methods. No game state. No ephemeral buffers.

```python
@dataclass
class Agent:
    handle: str
    role: str
    alive: bool = True
    born_tick: int = 0
    personality: str = ""
    soul: str = ""
```

### ComponentStore — Game State

All simulation state lives here, keyed by (handle, component). New systems add new components without editing Agent.

```python
class ComponentStore:
    def get(self, handle: str, component: str) -> dict: ...
    def set(self, handle: str, component: str, data: dict): ...
    def has(self, handle: str, component: str) -> bool: ...
    def remove(self, handle: str): ...
    def save(self): ...
    def load(self, handle: str): ...
```

Bread economy components:
- `"hunger"`: `{"hunger": 100, "thirst": 100}`
- `"economy"`: `{"coins": 500}`
- `"inventory"`: `{"flour": 0, "water": 0, "bread": 0}`
- `"memory"`: `{"memory": "", "code_fragment": None}`

### Brain — Perception In, Decisions Out

Brain receives a perception string, returns what the agent wants to do. Owns its internal state (message history, compaction). Doesn't know about the board, the bus, the store, or what flour is.

```python
class Brain(Protocol):
    async def decide(self, agent: Agent, perception: str) -> list[Decision]: ...
    def observe(self, decision: Decision, result: str) -> None: ...

@dataclass
class Decision:
    action: str
    args: dict[str, Any]
```

`decide()` returns the LLM's tool calls as Decisions. The engine executes them and calls `observe()` with the result text so the brain can update its conversation history.

Compaction is brain-internal. The brain decides when and how to compact based on its own context window. No `compact` action needed.

A scripted brain is trivial:
```python
class ScriptedBrain:
    async def decide(self, agent, perception):
        return [Decision("forage", {})]
    def observe(self, decision, result):
        pass
```

### Perception — Reads the World, Formats for Brain

Simulation-specific. Reads from the store, board, bus — whatever it needs. Writes nothing.

```python
class Perception:
    def build(self, agent: Agent, store: ComponentStore,
              board: BulletinBoard, bus: MessageBus, tick: int) -> str: ...
```

This is where `_rebuild_context`'s world-reading logic goes: reading new posts, DMs, formatting hunger warnings, building the tick message. Currently scattered between Brain and Agent.

### Actions — Use Public Interfaces

Actions take the agent, the store, and whatever infrastructure they need. They mutate through public APIs. They return feedback text for the brain.

```python
def forage(agent: Agent, store: ComponentStore, args: dict) -> str:
    skills = config.FORAGE_SKILL_BY_ROLE[agent.role]
    flour = random.randint(0, skills["flour"])
    water = random.randint(0, skills["water"])
    inv = store.get(agent.handle, "inventory")
    inv["flour"] += flour
    inv["water"] += water
    store.set(agent.handle, "inventory", inv)
    return f"foraged {flour} flour, {water} water"

def post_to_board(agent: Agent, store: ComponentStore, board: BulletinBoard,
                  args: dict) -> str:
    board.post(agent.handle, args["message"])
    return "posted"
```

No reaching into `agent._action_log`. No accessing `ctx.board._posts`. Actions use `store.get()`/`store.set()` and `board.post()`. They return a string — the engine feeds it back to the brain via `observe()`.

Actions that need the board get the board. Actions that need the bus get the bus. The ActionRegistry wires this — actions declare their dependencies.

### Systems — Same Idea

Systems read/write through the store and infrastructure APIs. No private field access.

```python
class DecaySystem:
    name = "decay"

    def tick(self, agents: list[Agent], store: ComponentStore):
        for agent in agents:
            h = store.get(agent.handle, "hunger")
            h["hunger"] = max(0, h["hunger"] - 3)
            h["thirst"] = max(0, h["thirst"] - 3)
            store.set(agent.handle, "hunger", h)
```

WorldEvents becomes a system. DeathSystem uses the pool's public API to kill/spawn.

### Engine — Orchestration

Owns the tick lifecycle. Passes each layer only what it needs. No god object.

```
Engine.tick():
    # 1. Pre-brain systems
    for system in [decay, tax, spoilage, death, world_events]:
        system.tick(agents, store, ...)

    # 2. Brain loop (parallel per agent)
    for agent in alive_agents:
        text = perception.build(agent, store, board, bus, tick)
        decisions = brain.decide(agent, text)
        for decision in decisions:
            result = action_registry.execute(agent, store, decision)
            brain.observe(decision, result)

    # 3. Post-brain systems
    for system in [consumption]:
        system.tick(agents, store, ...)

    # 4. Persist
    store.save()
```

### Tick-Scoped State

Ephemeral per-tick state (`dm_sent_this_tick`, `foraging`) lives in a simple dict the engine creates and discards each tick. Actions that need it (send_message checks DM count, forage sets the lock) receive it as a parameter.

```python
tick_state: dict[str, dict] = {handle: {} for handle in alive_handles}
```

No class needed. It's a dict. It dies at tick end.

### What Changes

| Current | New home |
|---|---|
| Agent methods (`_build_system_prompt`, etc.) | Perception |
| Agent ephemeral fields (`_action_log`, etc.) | Tick-scoped dict or gone |
| Agent game state (coins, flour, hunger) | ComponentStore |
| Agent conversation state (messages, system_prompt) | Brain internals |
| Brain._rebuild_context world-reading | Perception |
| Brain._process_tool_calls | Engine orchestration + brain.observe() |
| Context god object | Engine wires dependencies directly |
| Actions mutating agent._fields | Actions use store.get()/set() |
| Actions accessing ctx.board._posts | Actions use board's public API |

### Migration

Clean break. Archive `data/`. Reimplement the bread economy against the new architecture. Validate against existing experimental findings.
