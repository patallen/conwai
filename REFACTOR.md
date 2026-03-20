# Conwai Engine Refactor

Concrete issues found during architectural review. Engine-only — no scenario complaints, no wish-list features.

---

## 1. Race Condition in BrainPhase

`BrainPhase.run()` spawns all agents as concurrent async tasks via `asyncio.gather`. Each task builds perception (safe — read-only), calls the LLM (safe — independent), then **executes actions immediately** (`actions.execute()` in `engine.py:72`).

Actions that write to **other agents' components** race:

- `_pay` (actions.py:184-186) — read-modify-write on recipient's economy
- `_give` (actions.py:282-284) — read-modify-write on recipient's inventory
- `_post_to_board` (actions.py:46-48) — grants coins to mentioned agents
- `_send_message` (actions.py:77-79) — grants coins to DM recipient

If agents A and B both pay agent C in the same tick:
```
A reads C.economy → {coins: 100}
B reads C.economy → {coins: 100}
A writes C.economy → {coins: 150}
B writes C.economy → {coins: 150}  ← overwrites A's write
```

C should have 200, gets 150.

**Options:**
- Queue actions during brain phase, resolve in a post-brain action-resolution phase
- Lock per-agent component writes (adds complexity, kills some parallelism)
- Accept it and document the contract: actions should only modify the acting agent's own state; cross-agent mutations need a different pattern (e.g., a pending-transfer queue resolved by a later phase)

---

## 2. No Per-Agent Error Isolation in BrainPhase

`engine.py:63`: `await asyncio.gather(*tasks)` — if any agent's LLM call throws (timeout, malformed response, action handler exception), the entire gather fails and the tick is lost for all agents.

```python
# Current
await asyncio.gather(*tasks)

# Should be
results = await asyncio.gather(*tasks, return_exceptions=True)
for r in results:
    if isinstance(r, Exception):
        log.error(f"Agent tick failed: {r}")
```

Same issue in `actions.py:51-61` — if `action.handler()` raises, the exception propagates up through the brain phase unhandled.

---

## 3. BulletinBoard Cursor Bug on Overflow

`bulletin_board.py:22-26`: When posts exceed `max_posts`, old posts are trimmed and all cursors shift back by the overflow amount. An agent who already read posts before the trim will re-read them as duplicates on the next `read_new()` call.

```python
# Current
for h in self._cursors:
    self._cursors[h] = max(0, self._cursors[h] - overflow)

# Fix: clamp cursors that were past the overflow point
for h in self._cursors:
    self._cursors[h] = max(0, self._cursors[h] - overflow)
    # But this still produces duplicates for cursors in the kept range
```

Need to ensure cursors pointing into the kept range stay correct relative to the new list indices.

---

## 4. tick_state Mutation on Frozen TickContext

`actions.py:47-49`: `begin_tick()` assigns `ctx.tick_state = {...}`, mutating a field on TickContext. TickContext is a dataclass but not actually frozen (despite the DESIGN.md saying it should be). The mutation works, but it's implicit state threading — if two phases both use tick_state, they'd interfere.

**Options:**
- ActionRegistry owns tick_state internally, exposes it via methods
- tick_state becomes a return value from begin_tick(), not a mutation

---

## 5. ComponentStore get-mutate-set Pattern

Every action does:
```python
eco = store.get(handle, "economy")
eco["coins"] -= amount
store.set(handle, "economy", eco)
```

If you forget the `set()`, the mutation is silently lost. This pattern is repeated ~20 times in the scenario actions.

**Options:**
- `store.update(handle, component, fn)` where fn receives the dict and returns it
- `store.get()` returns a proxy that auto-commits on context exit
- Accept it — it's simple and explicit, just easy to get wrong

---

## 6. EventLog Timestamps Are Wall-Clock, Not Tick-Based

`events.py:31`: Events are timestamped with `time()` (wall clock). Two events in the same tick can have different timestamps. For replay, analysis, or determinism, events should carry the tick number.

```python
# Current
def log(self, entity_id, event_type, data=None):
    self._conn.execute("INSERT INTO events (t, ...) VALUES (?, ...)", (time(), ...))

# Should include tick
def log(self, entity_id, event_type, data=None, tick=None):
    self._conn.execute("INSERT INTO events (t, tick, ...) VALUES (?, ?, ...)", (time(), tick, ...))
```

---

## 7. EventLog Commits Per Event

`events.py:34`: Every `log()` call does `self._conn.commit()`. At 20 agents x 3 actions/tick, that's 60 fsync calls per tick. Fine on local NVMe, bad on networked storage or at scale.

**Option:** Batch commits — commit once per tick, or every N events.

---

## 8. LLMClient Interface Mismatch

`LLMClient` (OpenAI-compatible) and `AnthropicLLMClient` both implement `call(system, messages, tools)` but:
- Different `max_tokens` defaults (8192 vs 600)
- `extra_body` / `chat_template_kwargs` is OpenAI-specific, silently ignored by Anthropic
- No shared Protocol defining the contract
- Temperature hardcoded to 0.7 in both, not injectable

Swapping clients changes behavior in non-obvious ways.

**Option:** Define an `LLMClient` Protocol with explicit contract. Make temperature and max_tokens constructor params (they already are — but defaults should match or be required).

---

## 9. ~~Compaction Retention Is Unprincipled~~ DONE

Replaced LLM-based compaction with mechanical diary entries. Each tick's messages are collapsed into: agent's reasoning (truncated) + action→result pairs. No LLM calls. Retention window is configurable (`recent_ticks`, default 16). Agents are told to use their journal for long-term memory.

**Future:** structured relationship store (computed from EventLog), keyword-based diary retrieval for episodic recall.

---

## 10. Perception.build() Signature Diverges from DESIGN.md

DESIGN.md specified `build(agent, ctx)` — passing TickContext. Actual code (`perception.py:37-46`) passes individual args `(agent, store, board, bus, tick)`. The engine call site (`engine.py:69`) matches the current code, not the design.

This matters because adding new context (reputation, spatial info) requires changing the Perception signature and all builders. With TickContext, new context just goes in ctx.

**Decision needed:** Was the individual-args approach intentional (explicit dependencies) or an incomplete refactor?

---

## 11. save_all() Persists Everything Every Tick

`engine.py:118`: `self.pool.save_all()` writes every agent's identity + all components to disk every tick. At 20 agents x 5 components, that's 120 JSON writes per tick.

No dirty tracking — unchanged components are rewritten identically.

**Option:** Mark components dirty on `store.set()`, only persist dirty components in `save_all()`.

---

## 12. Brain State Save/Load Has No Versioning

`repository.py:58-67`: Brain state is saved/loaded as raw JSON. If `LLMBrain` adds or removes fields, old state files break or load incorrectly. The field-stripping in `load_agent()` (lines 37-50) handles Agent schema changes but nothing equivalent exists for brain state.
