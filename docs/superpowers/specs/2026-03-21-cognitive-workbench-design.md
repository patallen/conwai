# Cognitive Workbench

A minimal scenario for testing cognitive pipeline changes in isolation, without bread economy noise.

## Problem

All cognitive testing (memory, consolidation, retrieval, A/B variants) currently runs through the bread economy scenario. The economy adds noise that obscures cognitive signal, nothing is reproducible, manual interaction is painful, there's no way to script standardized inputs, and ticks are irrelevant to cognition testing.

## Design

A second scenario (`scenarios/workbench/`) that exercises the same cognitive pipeline (BlackboardBrain + processes) but strips away everything that isn't cognition or communication.

### Structure

```
scenarios/workbench/
├── runner.py          # Live mode: engine + BrainPhase, interactive CLI
├── perception.py      # WorkbenchPercept + WorkbenchPerceptionBuilder
├── actions.py         # Two actions: broadcast, message
└── prompts/
    └── system.md      # Generic agent system prompt
```

### What the workbench has

- **BlackboardBrain** with the standard cognitive processes: MemoryCompression, MemoryRecall, ContextAssembly, InferenceProcess. ConsolidationProcess added when testing consolidation.
- **Two actions**: `broadcast` (post to broadcast channel) and `message` (DM to another agent).
- **Communication primitives**: BulletinBoard (broadcast) and MessageBus (direct messages) from the framework.
- **Stimuli injection**: The runner accepts input that becomes part of agents' percepts. Board posts, DMs from fake handles, or raw injected text.
- **Interactive CLI**: Similar to the existing harness but without bread economy commands. Inspect memory, diary, brain state. Inject stimuli. Tick manually or auto-tick on input.

### What the workbench does not have

- No economy, inventory, hunger, thirst, coins
- No world systems (DecaySystem, TaxSystem, SpoilageSystem, DeathSystem, ConsumptionSystem)
- No world events (elections, ciphers, questions)
- No config dataclass or YAML configuration
- No dashboard

### Components

Only two components registered:

- `brain`: `{"messages": [], "diary": []}` — required by the cognitive processes
- `agent_info`: `{"role": str, "personality": str}` — used by the perception builder for identity

### Perception

`WorkbenchPercept` is a simple dataclass:

```python
@dataclass
class WorkbenchPercept:
    agent_id: str
    tick: int
    identity: str
    prompt_text: str
    action_feedback: list[ActionFeedback] = field(default_factory=list)

    def to_prompt(self) -> str:
        return self.prompt_text
```

`WorkbenchPerceptionBuilder` assembles `prompt_text` from:
- New broadcast messages (via BulletinBoard)
- New direct messages (via MessageBus)
- Injected stimuli (text pushed in by the runner or a script)

No economy state, no hunger warnings, no resource counts. Identity is built from `agent_info` fields only.

### Actions

Two actions:

- `broadcast`: Posts to the broadcast channel. Parameters: `{"content": str}`.
- `message`: Sends a DM. Parameters: `{"to": str, "content": str}`.

### Runner (live mode)

Interactive CLI that drives the engine with just BrainPhase. No world phases.

```
uv run python -m scenarios.workbench.runner [--model MODEL] [--base-url URL] [--agents N]
```

Commands:
- `(any text)` — inject as broadcast from WORLD, then tick
- `@HANDLE message` — inject as DM from HANDLE, then tick
- `!tick [N]` — advance N ticks silently
- `!inspect [HANDLE]` — show agent state
- `!memory [HANDLE]` — show diary + recent summaries
- `!brain [HANDLE]` — dump raw brain state
- `!agents` — list all agents
- `!quit` — exit

Agent count configurable via CLI flag. Defaults to 1 for simple cognitive testing, but supports N agents for social dynamics / emergence testing. Agent names generated via Faker.

### Brain wiring

```python
def make_brain(client, embedder, system_prompt) -> BlackboardBrain:
    return BlackboardBrain(
        processes=[
            MemoryCompression(
                recent_ticks=16,
                embedder=embedder,
            ),
            MemoryRecall(recall_limit=5, embedder=embedder),
            ContextAssembly(
                context_window=10_000,
                system_prompt=system_prompt,
            ),
            InferenceProcess(client=client, tools=registry.tool_definitions()),
        ],
        store=store,
    )
```

No StrategicReview (bread-specific). ConsolidationProcess omitted by default but trivially addable. A/B testing done by creating two `make_brain` variants and assigning agents to groups, same pattern as bread economy.

## Framework issues surfaced

Building this will expose and motivate fixes for:

1. **`PerceptionBuilder` protocol** mandates `board: BulletinBoard` and `bus: MessageBus` parameters. Should accept these optionally or not mandate them at all.
2. **`Percept` protocol** only declares `agent_id`. Should declare `tick`, `to_prompt()`, `action_feedback` since every process depends on them.
3. **`_NOISE_ACTIONS`** in MemoryCompression is hardcoded to bread economy actions. Should be a constructor parameter.
4. **`TickContext`** has `board` and `bus` as optional fields, which is fine, but the `PerceptionBuilder` protocol contradicts this by requiring them.

These fixes are not in scope for the initial workbench build. The workbench will work around them and they become follow-up cleanup tasks.

## Out of scope

- Scripted mode (non-interactive, feed percepts from a Python script). This is a natural follow-up once the live mode works, but the runner's interactive CLI comes first.
- YAML/JSON test definitions. Tests are Python.
- Dashboard or web UI.
- Framework refactoring (renaming BulletinBoard/MessageBus, moving processes to framework, fixing protocols). These are separate tasks motivated by building the workbench.
