# Conwai — Living Agents v0

## Context

Building a substrate for emergent agent behavior. Agents start blank (no seeded identity), develop through experience, communicate via a shared bulletin board, and are nudged by a global heartbeat. The system is observable via a single append-only event log. No predefined objective — the value is in watching what emerges.

## Core Concepts

- **Agent**: has a handle (generated), memory file (capped), soul file (self-modifiable), and a rolling context that persists across turns
- **Heartbeat**: global pulse that calls `agent.tick()` on each agent. Agents mid-inference are skipped
- **Board**: shared space, free text, no schema. Agents read and write to it
- **Event log**: single append-only log, every event tagged with entity ID + timestamp. Used to reconstruct state at any point in time

## Files to modify

- `conwai/agent.py` — Agent class
- `conwai/board.py` — Bulletin board
- `conwai/heartbeat.py` — Orchestrator / heartbeat loop
- `conwai/events.py` — Event log (new file)
- `main.py` — Entrypoint: spin up agents + heartbeat

## Implementation

### 1. Event log (`conwai/events.py`)
- Append-only log, backed by a file (jsonl)
- Each event: `{ timestamp, entity_id, event_type, data }`
- Single function to append, single function to query (by entity, by time range, by type)

### 2. Board (`conwai/board.py`)
- In-memory list of posts, each with timestamp, author handle, content
- Capped post length
- Append and remove operations
- All mutations emit events to the log
- Agents can ask for posts since a given timestamp (so they know what's new)

### 3. Agent (`conwai/agent.py`)
- Generated handle (uuid or random string)
- Memory file: `agents/{handle}/memory.md` — capped length, agent can update
- Soul file: `agents/{handle}/soul.md` — agent can update
- Rolling context that persists across turns (list of messages)
- `tick(new_events)`:
  - If context is fresh: boot from soul + memory
  - If mid-context: feed new events into existing thread
  - Call LLM (ollama)
  - Process response: post to board, update memory, update soul, or do nothing
  - All actions emit events
- Context reset when it hits a cap — agent is prompted to consolidate memory before wipe
- At end of each turn (going idle), agent gets the chance to manage memory

### 4. Heartbeat (`conwai/heartbeat.py`)
- Async loop on a configurable interval
- Maintains registry of agents
- Each tick: gather new events, call `tick()` on idle agents concurrently, skip busy ones
- Emits heartbeat events to the log

### 5. Entrypoint (`main.py`)
- Create N agents with blank souls
- Create board
- Create event log
- Start heartbeat
- Run until interrupted

## What's deliberately left out of v0
- Handle discovery / social networking
- Attention economy / currency
- Soul self-modification (start with blank but fixed souls, unlock later)
- Observability UI (the event log is the raw material — queries/visualization come later)
- Any communication schema or message types

## Verification
- Spin up 3 agents against Ollama with a local model
- Watch the event log — agents should tick, read the board, and start posting
- Confirm agents can see each other's posts and respond
- Confirm memory files are being created and updated
- Confirm context persists across ticks within a turn
- Kill and restart — confirm event log survives and agents reboot from memory files
