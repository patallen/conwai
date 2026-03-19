# Clean Layers Architecture

## Problem

Recent refactoring moved code between files but didn't change who knows about what. Agent is supposed to be data but has methods and ephemeral tick state. Brain reaches into agent internals for prompt assembly. Actions mutate everything directly. Context is a god object. There's no boundary between framework and simulation.

## Approach

Enforce strict layers with clear dependency direction. Each layer has defined access and a defined output type. Mutation only happens through Effects applied by the Engine.

## Design

### Agent — Pure Identity

Agent is a data bag with no methods. Only identity and role — no game state, no ephemeral buffers, no prompt logic.

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

All simulation state (coins, flour, hunger, etc.) lives in the ComponentStore, not on Agent. This means new systems can add state without editing Agent.

### ComponentStore — Simulation State

Central state store keyed by (handle, component name). Systems register what components they need. When an agent spawns, the store initializes components with defaults. Persistence serializes the whole store.

```python
class ComponentStore:
    def get(self, handle: str, component: str) -> dict: ...
    def set(self, handle: str, component: str, data: dict): ...
    def has(self, handle: str, component: str) -> bool: ...
```

Example components for the bread economy:
- `"hunger"`: `{"hunger": 100, "thirst": 100}`
- `"economy"`: `{"coins": 500}`
- `"inventory"`: `{"flour": 0, "water": 0, "bread": 0}`
- `"memory"`: `{"memory": "", "code_fragment": None}`

### Effects — The Only Way to Mutate

Actions and systems never write to the store directly. They return Effects. The engine applies them.

```python
@dataclass
class Effect:
    handle: str
    component: str
    changes: dict[str, Any]
```

This means:
- The engine is the single point of mutation — validates, applies, logs in one place
- Logging is automatic — every Effect is visible
- Testing is trivial — call a function, check returned Effects
- Actions that affect multiple agents just return multiple Effects

### Systems — World Mechanics

Systems process agents each tick and return Effects. They read from the store and agent identity but never write directly.

```python
class DecaySystem:
    def tick(self, agents: list[Agent], store: ComponentStore) -> list[Effect]:
        effects = []
        for agent in agents:
            hunger = store.get(agent.handle, "hunger")
            effects.append(Effect(agent.handle, "hunger", {
                "hunger": max(0, hunger["hunger"] - 3),
                "thirst": max(0, hunger["thirst"] - 3),
            }))
        return effects
```

Systems get whatever dependencies they need (agents, store, board, bus, etc.) — the engine wires them in. Systems that currently live as special cases (WorldEvents) become regular systems.

### Perception — Read the World, Format for Brain

Perception reads from everything (store, board, bus, event log) but writes nothing. It builds the tick message string that the brain receives.

This is simulation-specific. The bread economy perception builds the current tick format with hunger warnings, board posts, DM history, inventory state, etc. A different simulation would build different perception.

```python
class Perception:
    def build(self, agent: Agent, store: ComponentStore,
              board: BulletinBoard, bus: MessageBus, tick: int) -> str:
        # Reads whatever it needs, produces text
        ...
```

### Brain — Perception In, Decisions Out

Brain receives the formatted perception text and returns a list of decisions. It owns its internal state (message history, system prompt, compaction) but doesn't know about world state.

```python
class Brain(Protocol):
    async def decide(self, agent: Agent, perception: str) -> list[Decision]:
        ...

@dataclass
class Decision:
    action: str
    args: dict[str, Any]
```

The current LLMBrain becomes an implementation that internally manages conversation history, calls the LLM, handles compaction. From the outside it's just perception in, decisions out.

A scripted brain is trivial:
```python
class ScriptedBrain:
    async def decide(self, agent, perception):
        return [Decision("forage", {})]
```

Brain doesn't call actions. Brain doesn't read the board. Brain doesn't process inboxes.

### Actions — Pure Functions Returning Effects

Actions read from the store and return Effects. They never mutate directly.

```python
def forage(agent: Agent, store: ComponentStore, args: dict) -> list[Effect]:
    skills = config.FORAGE_SKILL_BY_ROLE[agent.role]
    flour = random.randint(0, skills["flour"])
    water = random.randint(0, skills["water"])
    return [Effect(agent.handle, "inventory", {"flour": flour, "water": water})]

def pay(agent: Agent, store: ComponentStore, args: dict) -> list[Effect]:
    amount = args["amount"]
    return [
        Effect(agent.handle, "economy", {"coins": -amount}),
        Effect(args["to"], "economy", {"coins": +amount}),
    ]
```

### Engine — Orchestration

The engine owns the tick lifecycle and is the single point of mutation.

```
Engine.tick():
    tick_ctx = TickContext(tick=self.tick)

    # 1. Pre-brain systems
    for system in [decay, tax, spoilage, death]:
        effects = system.tick(agents, store)
        self.apply(effects)

    # 2. Brain loop (parallel per agent)
    for agent in alive_agents:
        text = perception.build(agent, store, board, bus, tick)
        decisions = await brain.decide(agent, text)
        for decision in decisions:
            effects = action_registry.execute(agent, store, decision)
            self.apply(effects)

    # 3. Post-brain systems
    for system in [consumption]:
        effects = system.tick(agents, store)
        self.apply(effects)

    # 4. Persist
    store.save_dirty()
```

### Layer Access Summary

| Layer | Reads | Writes | Produces |
|---|---|---|---|
| Agent | — | — | Identity data |
| ComponentStore | handle + component | — | State lookups |
| Systems | Agents, store, infrastructure | Nothing directly | Effects |
| Perception | Agents, store, board, bus, anything | Nothing | Text for brain |
| Brain | Agent identity, perception text | Own internal state | Decisions |
| Actions | Agent identity, store | Nothing directly | Effects |
| Engine | Everything | Applies Effects to store | Orchestration |

### What Gets Deleted

- `Context` dataclass (god object) — engine wires dependencies directly
- All methods on `Agent` (`_build_system_prompt`, `_build_identity_message`, `_format_state_sections`, `gain_coins`, `write_memory`, `record_*`)
- All ephemeral fields on Agent (`_inbox`, `_action_log`, `_energy_log`, `_board_history`, `_dm_history`, `_ledger`, `_dm_sent_this_tick`, `_foraging`, `messages`, `system_prompt`)
- Direct mutation in actions and systems

### Migration

Clean break. Archive existing simulation data. Reimplement the bread economy simulation against the new architecture to validate it. Compare behavior against existing experimental findings.
