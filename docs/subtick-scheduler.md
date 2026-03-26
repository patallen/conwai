# Sub-tick Scheduler

## The Problem

Everything is lockstep. All agents think once per tick, simultaneously. No agent can react to what another did. No conversations, no cascading, no emergence.

## The Design

A tick is divided into N sub-ticks (configurable, default 1 = backward compat). A Scheduler class manages the sub-tick timeline as a System in the engine.

### How it works

1. Events drive agent activation. When something happens (DM arrives, board post, env change), the EventBus fires. The scheduler subscribes and queues affected agents.
2. Each activation has a cost in sub-ticks. Quick reply = 1. Full deliberation = 3. Deep reflection = 5.
3. The scheduler processes sub-ticks in order. At each sub-tick, it gathers results from completed work, executes actions, and checks for new events that trigger more work.
4. At resolution=1, all agents activate at sub-tick 0 with cost 1. Everything resolves immediately. Same as today.

### Example: resolution=10, think_cost=3, retrigger_cost=2

```
subtick 0: All agents start thinking (LLM calls fire concurrently)
subtick 2: All agents resolve. Actions execute. EventBus fires.
           Agent A sent DM to B → ActionExecuted event → scheduler queues B
subtick 3: (nothing, B's retrigger hasn't resolved yet)
subtick 4: B resolves retrigger. B's action executes. B DMs C → queues C
subtick 5: (waiting)
subtick 6: C resolves retrigger.
subtick 9: Tick ends.
```

### Key principles

- **Scheduler is a System** — holds state, persists across ticks, has config set once at startup
- **Scheduler is generic** — doesn't know about brains, perception, actions, or any domain concept. Takes opaque async callables.
- **Events are the routing layer** — the EventBus (already exists) connects actions to re-triggers. Scenario code subscribes to events and tells the scheduler to queue work. The scheduler never inspects action results.
- **BrainSystem/ActionSystem untouched** — the scheduler orchestrates WHEN agents run, not HOW they think. The existing brain and action logic stays where it is.

### Architecture

```
Engine
  └── tick()
        ├── PondSystem (env update)
        └── Scheduler.run()
              ├── processes sub-ticks 0..resolution-1
              ├── at each sub-tick: gather due tasks, execute
              ├── actions fire events on EventBus
              ├── event handlers call scheduler.schedule(key, task_fn)
              └── new tasks land at current_subtick + cost
```

### Config (scenarios/commons/config.json)

```json
{
    "tick_resolution": 10,
    "think_cost": 3,
    "retrigger_cost": 2
}
```

### What exists now

`conwai/scheduler.py` has a `run_subticks()` function that handles the sub-tick loop and re-triggering. It's generic (no domain imports) but it's just a function, not a System. Needs to become a class with state that integrates with EventBus.

`scenarios/commons/runner.py` has a `ScheduledAgents` class that wraps the function with domain logic (activate, on_complete). The on_complete callback does string matching on action names — should use EventBus instead.

### What's left to do

1. Make scheduler a proper class/System with state
2. Wire re-triggering through EventBus instead of string-matching callbacks
3. The runner defines what events trigger which agents (scenario-specific), subscribes to EventBus, calls scheduler.schedule()
