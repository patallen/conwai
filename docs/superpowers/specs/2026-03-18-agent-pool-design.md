# AgentPool Design

Extract agent lifecycle management from `main.py` into a dedicated `AgentPool` class. First step of a larger refactor toward composable systems.

## Problem

Agent management is scattered across `main.py`: creation (`make_agent`), the startup load-or-create loop, death detection, replacement spawning, and bus registration/unregistration. Adding new mechanics that interact with the agent population means touching `main.py` and remembering to update `ctx.agent_map`, the bus, and the repository in the right order.

## Design

### New file: `conwai/pool.py`

`AgentPool` is the single source of truth for the agent population. It replaces `ctx.agent_map`, the `agents` list in `main.py`, and `ctx.register_agent()`.

```python
class AgentPool:
    def __init__(self, repo: AgentRepository, bus: MessageBus):
        self._repo = repo
        self._bus = bus
        self._agents: dict[str, Agent] = {}  # handle -> Agent

    # --- Queries ---
    def all(self) -> list[Agent]: ...
    def alive(self) -> list[Agent]: ...
    def by_handle(self, handle: str) -> Agent | None: ...
    def handles(self) -> list[str]:
        """Returns handles of alive agents only (matches current agent_map behavior)."""

    # --- Lifecycle ---
    def load_or_create(self, handle: str, role: str, born_tick: int) -> Agent:
        """Load from disk if exists, otherwise create with starting values.
        Only registers alive agents on the message bus. Dead agents are
        added to the pool but left unregistered — replace_dead picks them up."""

    def spawn(self, role: str, born_tick: int) -> Agent:
        """Create a new agent with a generated handle and starting resources.
        Registers on bus. Returns the new agent."""

    def kill(self, handle: str) -> None:
        """Mark agent as dead, unregister from bus."""

    def replace_dead(self, board: BulletinBoard, events: EventLog, born_tick: int) -> list[Agent]:
        """Find dead agents, announce deaths on board and event log,
        spawn replacements, announce arrivals. The dead agent is removed
        from the pool and the replacement takes its slot. Returns list of
        newly spawned agents so the caller can wire up runtime dependencies."""

    def save(self, handle: str) -> None:
        """Persist a single agent to disk."""

    def save_all(self) -> None:
        """Persist all agents to disk."""
```

### Eviction policy

When `replace_dead` processes a dead agent, it removes the dead agent from `_agents` and adds the replacement under the new handle. Dead agents don't linger — once replaced, they exist only in the event log and on disk. This keeps `_agents` bounded to the active population size.

### Handle generation

Moved from `make_agent` in `main.py`. Uses the same pattern: prefix (currently the dead agent's first character, e.g. `"A"`) + 3 random hex chars, retry until the handle doesn't exist on disk.

### Context changes (`app.py`)

- Remove `agent_map: dict` field
- Remove `register_agent()` method
- Add `pool: AgentPool` field

### Callsite migration

All `ctx.agent_map` references become pool queries. These are mechanical replacements:

| Before | After |
|---|---|
| `ctx.agent_map[handle]` | `ctx.pool.by_handle(handle)` |
| `handle in ctx.agent_map` | `ctx.pool.by_handle(handle) is not None` |
| `for h, a in ctx.agent_map.items()` | `for a in ctx.pool.all()` (use `a.handle` instead of `h`) |
| `ctx.agent_map.keys()` | `ctx.pool.handles()` |
| `del ctx.agent_map[handle]` | inside `pool.kill()` |
| `ctx.register_agent(agent)` | inside pool lifecycle methods |

### Files changed

- **`conwai/pool.py`** — new file, AgentPool class
- **`conwai/app.py`** — remove `agent_map` and `register_agent`, add `pool`
- **`main.py`** — replace `make_agent`, startup loop, death/replacement block with pool calls. Handler watcher uses `ctx.pool.by_handle()`.
- **`conwai/default_actions.py`** — replace `ctx.agent_map` references with pool queries
- **`conwai/world.py`** — replace `ctx.agent_map` references with pool queries
- **`test_agent.py`** — replace `ctx.register_agent()` calls with pool setup
- **`test_compaction.py`** — replace `ctx.register_agent()` calls with pool setup

### What the pool does NOT own

- Tick execution (agents tick themselves, called from main.py)
- Config or config reloading
- LLM clients or action registries (wired by caller after spawn/load)
- Tax, spoilage, or any simulation mechanics (future systems)

### Runtime wiring

Agents currently own `core`, `compactor`, `actions`, and `context_window`. These are runtime dependencies that will move to systems in the future. For now, the caller wires them up after `load_or_create`, `spawn`, or `replace_dead`:

```python
pool = AgentPool(repo, ctx.bus)
for handle, role in agent_specs:
    agent = pool.load_or_create(handle, role, ctx.tick)
    agent.core = b200
    agent.compactor = h200
    agent.actions = registry
    agent.context_window = 10_000

# In tick loop:
new_agents = pool.replace_dead(ctx.board, ctx.events, ctx.tick)
for agent in new_agents:
    agent.core = b200
    agent.compactor = h200
    agent.actions = registry
    agent.context_window = 10_000
```

When agents become pure data, the wiring loops get deleted.

### main.py after

```python
async def main():
    setup_logging()
    ctx = Context()
    # ... tick loading, LLM client setup ...

    repo = AgentRepository()
    pool = AgentPool(repo, ctx.bus)
    ctx.pool = pool

    roles = ["flour_forager"] * 6 + ["water_forager"] * 6 + ["baker"] * 4
    for i, role in enumerate(roles, 1):
        agent = pool.load_or_create(f"A{i}", role, ctx.tick)
        agent.core = b200
        agent.compactor = h200
        agent.actions = registry
        agent.context_window = 10_000

    ctx.bus.register("HANDLER")
    ctx.bus.register("WORLD")
    world = WorldEvents()
    ctx.world = world

    asyncio.create_task(watch_handler_file(ctx))

    while True:
        config.reload()
        await wait_for_llm()
        ctx.tick += 1
        Path("data/tick").write_text(str(ctx.tick))
        world.tick(ctx)

        # Tax
        if ctx.tick % 24 == 0:
            for agent in pool.alive():
                if agent.coins > 0:
                    tax = max(1, int(agent.coins * 0.01))
                    agent.coins -= tax
                    agent._energy_log.append(f"coins -{tax} (daily tax)")
            ctx.log("WORLD", "tax", {"tick": ctx.tick})

        # Spoilage
        if config.BREAD_SPOIL_INTERVAL > 0 and ctx.tick % config.BREAD_SPOIL_INTERVAL == 0:
            for agent in pool.alive():
                if agent.bread > 0:
                    spoiled = min(agent.bread, config.BREAD_SPOIL_AMOUNT)
                    agent.bread -= spoiled
                    agent._energy_log.append(f"{spoiled} bread spoiled")

        # Death + replacement
        new_agents = pool.replace_dead(ctx.board, ctx.events, ctx.tick)
        for agent in new_agents:
            agent.core = b200
            agent.compactor = h200
            agent.actions = registry
            agent.context_window = 10_000

        # Tick alive agents
        tasks = []
        for agent in pool.alive():
            async def tick_and_save(a=agent, t=ctx.tick):
                start = time.monotonic()
                await a.tick(ctx)
                pool.save(a.handle)
                log.info(f"[{a.handle}] tick {t} took {time.monotonic() - start:.1f}s")
            tasks.append(asyncio.create_task(tick_and_save()))
        await asyncio.gather(*tasks)
```
