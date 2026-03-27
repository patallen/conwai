# DES Scheduler + Generator Brain

## What we built

### Scheduler (`conwai/scheduler.py`)

Discrete event scheduler. Heap queue sorted by simulated time. Time jumps from event to event — no empty steps.

- `schedule(key, task_fn, cost)` — put work on the heap at `sim_time + cost`
- `run(until=N)` — pop events in order, run tasks, drain EventBus between steps
- Tasks at the same sim_time run concurrently via `asyncio.gather`
- Duplicate keys are ignored (agent can't be scheduled twice)
- Work past `until` stays on the heap for the next `run()` call

### Mind (`conwai/cognitive.py`)

Generator-based brain. Yields `Work` items, receives results via `.send()`.

- `Work(type, tick_cost)` — what to do and how long it takes
- `Mind.handle(percept)` — returns a generator the runner drives
- Mind owns persistent `State` across activations
- The framework doesn't prescribe what Work types exist or what results look like — that's between the Mind implementation and its runner

### POC (`poc_scheduler.py`)

Three agents with heartbeats. Each agent wakes every N sim-time units, perceives the world (inbox, board, pond), triages, and decides whether to ignore, react, or deliberate. DMs and board posts are just world state agents see on their heartbeat — no event-triggered activation.

Produces: multi-party negotiation, social deduction, false confessions, emergent governance. All from the architecture, not from scripted behavior.

## How it works

```
Agent heartbeat fires
  → Mind.handle(percept) produces a generator
  → Runner drives it:
      yield Work("triage", cost=1)     → runner calls LLM, sends result back
      yield Work("deliberate", cost=5) → runner calls LLM, sends result back
      yield Work("command", cost=0)    → runner executes action
  → After generator completes, schedule next heartbeat
```

Each yield goes through the scheduler. Triage resolves 1 sim-time unit later. Deliberation resolves 5 units later. Other agents' heartbeats can fire in between.

## Integration path

The existing conwai framework doesn't change. The runner changes:

1. **Scheduler** replaces the Engine's tick loop for agent orchestration
2. **Mind** wraps the existing Brain — triage decides whether to call `Brain.think()` (the existing process pipeline with memory, recall, context assembly, inference)
3. **Heartbeats** replace the "all agents think every tick" pattern
4. **World, ECS, ActionRegistry, perception builders, memory, storage** — all unchanged

## Key findings from the POC

- Agents independently notice environmental changes (pond level) without being told
- Social pressure creates false confessions (Bob admitted to something he didn't do)
- Agents invent physical world elements (docks, crowds) when there's no grounded environment — integration with the real World/perception system would fix this
- Charlie (the guilty agent) consistently plays it cool early, only confessing under sustained pressure
- The heartbeat model produces much more dynamic interaction than tick-by-tick
