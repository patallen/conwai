# conwai

An engine for building agent simulations. Agents perceive, think, and act in a shared world. You define the world rules, what agents see, and how they decide.

## Goals

- Make it easy to build agent simulations without rebuilding plumbing (memory, perception, communication, persistence, world rules)
- Support rapid experimentation with different cognitive architectures and scenario designs
- Stay LLM-agnostic: the framework shouldn't assume how agents think
- Built-in observability: everything should be inspectable, measurable, and reproducible
- Observe emergent behavior, not script it

## Architecture

Three layers:

**Framework**: The engine, World, and cognitive pipeline primitives. LLM-agnostic. You could build a rule-based agent with the same framework.

- `World`: unified container for entities, typed components (ECS-style), and singleton resources
- `System`: operates on the World each tick via typed queries
- `Percept`: read-only typed container for what an agent perceives
- `Blackboard`: mutable typed container for inter-process state
- `BlackboardBrain`: runs a pipeline of processes, takes a Percept, returns Decisions

**Processes**: Reusable building blocks for common cognitive patterns. Opt-in, not required.

- `MemoryCompression`: collapse working memory into episodes
- `MemoryRecall`: surface relevant episodes via embedding similarity
- `ContextAssembly`: convert cognitive state to LLM message format
- `InferenceProcess`: call an LLM and produce decisions

**Scenarios**: These are "working" simulation implementations that are built atop the core engine.

- `scenarios/bread_economy/`: multi-agent economy with foraging, baking, trading, and social dynamics
- `scenarios/workbench/`: minimal testbed for cognitive pipeline experiments

## How it (currently) works

Each tick:

1. **Systems** run on the World (hunger decay, taxes, spoilage, etc.)
2. **Perception builders** read World state and produce a typed `Percept` for each agent
3. **Brains think**: processes run sequentially on the `Percept` and `Blackboard`, producing `Decisions`
4. **Actions execute**: decisions are applied to the World, results feed back next tick
5. **Flush**: all component state is persisted to storage

The brain owns its state across ticks. Working memory and episodes persist on the blackboard. The engine handles persistence via batched flush at tick end.

## Running

```bash
make start        # full stack (engine + dashboard)
make run          # engine only
uv run python harness.py  # single-agent test harness
```

## Testing

```bash
uv run pytest tests/
```
