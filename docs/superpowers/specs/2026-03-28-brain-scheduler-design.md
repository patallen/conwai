# Brain-Scheduler Integration

## Overview

Move the Brain from a synchronous pipeline (`think(percept) -> decisions`) to a scheduler-aware entry point (`perceive(percept, scheduler, handle) -> None`). The Brain triages incoming percepts, schedules cognitive work onto the Scheduler with costs, and outputs decisions through a pluggable action adapter.

## Brain Protocol

```python
class Brain(Protocol):
    def perceive(self, percept: Percept, scheduler: Scheduler, handle: str) -> None:
        """Triage a percept and schedule cognitive work."""
        ...

    def save_state(self) -> dict: ...
    def load_state(self, data: dict) -> None: ...
```

- `perceive()` is synchronous and non-blocking — it calls `scheduler.schedule()` (which just pushes onto the heap) and returns immediately. Any async work (embedding, LLM calls, etc.) is scheduled as tasks, not executed inline.
- The Brain uses `handle` as a key prefix for scheduler tasks (e.g. `"{handle}:inference"`) to avoid collisions with other agents.
- The Brain manages its own concurrency constraints internally (e.g. can't start a second inference while one is in-flight). This is the Brain's concern, not the framework's.
- What the Brain needs at construction time (LLM clients, embedders, etc.) is entirely up to the concrete implementation. The protocol does not prescribe dependencies.

## Action Adapter

Inspired by ACT-R's motor module / device interface. The adapter is the bridge between cognition and the environment. It is part of the Brain's architecture but not part of cognition — cognitive processes never see it.

```python
class ActionAdapter(Protocol):
    async def execute(self, handle: str, decisions: list[Decision]) -> list[ActionResult]:
        ...
```

A standard implementation ships with the framework:

```python
class WorldActionAdapter:
    def __init__(self, world: World, registry: ActionRegistry):
        self.world = world
        self.registry = registry

    async def execute(self, handle, decisions):
        self.world.set(handle, PendingActions(entries=decisions))
        results = []
        for d in decisions:
            result = self.registry.execute(handle, d.action, d.args, self.world)
            results.append(ActionResult(action=d.action, args=d.args, result=result))
        self.world.set(handle, ActionFeedback(entries=results))
        return results
```

- The Brain is constructed with an adapter.
- The Brain calls the adapter after all cognitive processes complete — processes themselves never see the adapter. For example, the pipeline brain runs its process list, extracts Decisions from the blackboard, then calls `self.adapter.execute(handle, decisions)`.
- PendingActions is written before execution so the system can be snapshotted between "decided" and "acted."
- The adapter writes PendingActions and ActionFeedback to the World.
- Feedback flows back to the Brain on the next cycle via the perception builder reading ActionFeedback from the World.

## TickLoop

No changes. The Brain's scheduled work runs within the tick's existing `scheduler.run()` call.

- Pre-systems run once at the start.
- `brain.perceive()` is called for each agent, which schedules cognitive work.
- `scheduler.run()` drains all scheduled work. sim_time advances within the tick based on cognitive costs — this provides ordering (faster brains act first) but the tick remains a single logical frame.
- Post-systems run once after all brain work completes.
- Persist runs at the end.

sim_time and tick_number are independent concepts. sim_time is the scheduler's internal clock, tick_number is the runner's count of logical frames.

## Scheduler

No changes.

## Migration

### Framework changes

1. **Brain protocol** — `think(percept) -> list[Decision]` becomes `perceive(percept, scheduler, handle) -> None`.
2. **ActionAdapter protocol** — new protocol with a standard `WorldActionAdapter` implementation.
3. **Existing Brain class** — becomes one concrete implementation (a pipeline brain that schedules its processes in sequence). The protocol is what the framework cares about.
4. **Existing processes** — no changes. The `Process` protocol, `BrainContext`, `Blackboard`, `State`, and `Percept` types all stay as-is. They are internal to the pipeline brain implementation.

### Scenario changes

1. **Runners** — `think_then_act` simplifies to calling `brain.perceive()`. The adapter handles action execution.
2. **Brain construction** — runners pass an ActionAdapter to the brain at construction time.
