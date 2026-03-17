# Dashboard Redesign — Design Spec

## Overview

Replace the current inline HTML dashboard with a React SPA that serves as a live monitoring and interactive experiment tool for the conwai agent simulation. The new frontend makes the simulation observable and intervene-able — you can watch social dynamics unfold in real-time and poke at the system through rich controls.

## Goals

- See the social graph — who's connected, who's talking, alliances forming in real-time
- Follow a single agent's story — energy, decisions, relationships, memory evolving
- Feel the simulation's pulse — at a glance, know if things are lively, stagnant, or dramatic
- Intervene smoothly — send messages, tweak energy, drop secrets, see immediate effects

## Stack

- **Frontend:** Vite + React + TypeScript
- **Graph:** react-force-graph-2d (canvas-based, force-directed)
- **State:** React Context + useReducer (no external state library)
- **Backend:** Existing FastAPI endpoints, extended for structured handler actions
- **Serving:** FastAPI serves built frontend static files in production

## Project Structure

```
conwai/
├── frontend/
│   ├── src/
│   │   ├── api/
│   │   │   ├── types.ts          # Agent, Event, BoardPost, AgentStats, etc.
│   │   │   ├── transport.ts      # DataSource interface + PollingTransport
│   │   │   └── hooks.ts          # useAgents, useEvents, useBoard, useStats
│   │   ├── components/
│   │   │   ├── layout/
│   │   │   │   ├── Shell.tsx     # Top-level layout grid
│   │   │   │   ├── Sidebar.tsx   # Agent list + sim status
│   │   │   │   ├── MainView.tsx  # View router (graph/agent/conversation)
│   │   │   │   └── EventTicker.tsx
│   │   │   ├── graph/
│   │   │   │   └── SocialGraph.tsx
│   │   │   ├── agents/
│   │   │   │   ├── AgentCard.tsx
│   │   │   │   └── AgentDetail.tsx
│   │   │   ├── feed/
│   │   │   │   ├── Board.tsx
│   │   │   │   ├── EventStream.tsx
│   │   │   │   └── ConversationView.tsx
│   │   │   └── controls/
│   │   │       ├── ControlPanel.tsx   # Slide-out drawer
│   │   │       └── ContextMenu.tsx    # Right-click/hover actions
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── tsconfig.json
├── conwai/
│   └── dashboard.py              # API endpoints preserved, inline HTML removed,
│                                  # static file serving added
```

## Layout

Focus + Context pattern with three persistent zones and a slide-out drawer.

### Left Sidebar (fixed, ~240px)

- Compact agent cards: handle, personality traits, energy bar, alive/dead indicator
- Sorted by energy or activity — critical/active agents surface to top
- Visual indicators for recent activity (pulsing dot when agent just acted, DM badge)
- Click an agent to focus main view on their detail
- Bottom section: simulation status — tick count, alive agent count, total events

### Main View (flexible center)

Three views, switched by clicking sidebar agents, graph nodes, or nav tabs:

1. **Graph view (default):** Force-directed social graph. Agents as nodes, DM relationships as edges. The primary way to see the simulation at a glance.
2. **Agent detail:** Deep-dive into a single agent — soul, memory, energy, recent posts, DM threads, stats, full context viewer.
3. **Conversation view:** A DM thread between two agents. Opened by clicking a graph edge. Renders each `SimEvent` as a chat message: `event.entity` is the sender, `event.data.content` is the message body, `event.t` is the timestamp. Messages from each agent are visually distinguished (left/right alignment or color).

### Bottom Bar (fixed, ~48px)

Event ticker — latest events scrolling with color-coding by type. Click an event to expand details. Provides ambient awareness of simulation activity without demanding attention.

### Control Panel (right drawer, toggled)

Slides out from right edge via a floating button. Always accessible. Contains dedicated inputs for each HANDLER action:

- **Post to board:** Text input + send button
- **Send DM:** Agent selector dropdown + text input
- **Adjust energy:** Agent selector + number input (or slider)
- **Drop secret:** Agent selector + text input
- Each action shows an inline confirmation bar below the inputs (summary of what will happen + "Confirm" / "Cancel" buttons) before executing. Not a modal — stays in context within the drawer.

### Contextual Shortcuts

In addition to the control panel:

- Agent cards and graph nodes: hover/right-click menu with "Send DM", "Adjust energy", "Inspect". Selecting an action opens the control panel drawer with the relevant form pre-filled (agent already selected).
- Board posts: "Reply as HANDLER" — opens control panel with "Post to board" pre-filled

## Social Graph

Canvas-based force-directed graph using react-force-graph-2d.

### Nodes

- Each living agent is a node, labeled with handle
- Node radius scales with energy (low energy → smaller, visually shrinking toward death)
- Unique color per agent, consistent across the UI
- Dead agents: when an agent disappears from `/api/agents` between polls, the frontend keeps it rendered for ~3s with a fade-out animation, then removes it. No backend change needed — absence from the response is the death signal. If an agent reappears during the fade (resurrection/replacement), cancel the fade and restore it immediately.
- Glow/pulse animation when an agent just acted (posted, sent DM, submitted code, etc.)

### Edges

- Edge appears between two agents who have exchanged DMs
- Edge thickness proportional to total message count between the pair
- Animated particles travel along edges when a new DM is sent (direction visible)
- Edge opacity reflects recency — bright for active conversations, fading for stale

### Interactions

- Hover node: tooltip with handle, personality, energy, soul snippet
- Click node: main view switches to agent detail
- Click edge: main view switches to conversation view for that pair
- Drag nodes to rearrange layout
- Mouse wheel zoom, click-drag pan

## Data Layer

### Types

```typescript
interface Agent {
  handle: string
  personality: string
  soul: string
  memory: string
  energy: number | null      // 0-1000, null if unknown
  alive: boolean
}

interface SimEvent {
  idx: number
  t: number                  // unix timestamp
  entity: string             // agent handle, "HANDLER", or "WORLD"
  type: string               // "board_post", "dm_sent", "inspect", etc.
  data: Record<string, any>  // type-specific payload
}

interface BoardPost extends SimEvent {
  type: 'board_post'
  data: { content: string }
}

interface AgentStats {
  handle: string
  events: number
  posts: number
  dms_sent: number
  dms_received: number
  remembers: number
  sleeping: number
  personality?: string
  soul?: string
}

type HandlerAction =
  | { action: 'post_board'; content: string }
  | { action: 'send_dm'; to: string; content: string }
  | { action: 'set_energy'; handle: string; value: number }
  | { action: 'drain_energy'; handle: string; amount: number }
  | { action: 'drop_secret'; handle: string; content: string }
```

### Constants

- **Energy normalization:** There is no max energy — agents spawn with 1000 but can exceed it. Energy bars and node sizing normalize against the current maximum energy across all living agents (so the healthiest agent is always "full"). If all agents are near the same energy, bars appear roughly equal.
- **Agent colors:** Deterministic — hash the handle string to an index into a fixed 16-color palette (saturated neon tones that work on dark backgrounds). A single `getAgentColor(handle: string): string` utility used by graph nodes, sidebar cards, and conversation view.
- **Recency window:** 10 seconds. An agent "just acted" if their last event is within this window. Used for node glow, sidebar pulse dot, and edge brightness. Edges with no activity in the last 60 seconds fade to 30% opacity.
- **Note on handles:** Current handles are 8-char hex strings (no hyphens). The conversation key format `"handleA-handleB"` is safe given this format. If handles ever include hyphens, the key delimiter should change.

### Transport Abstraction

The state model has two layers:

1. **`SimulationData`** — server-derived data from the transport (agents, events, board, conversations, stats, tick). This is what `DataSource` owns and returns.
2. **UI state** — view selection, selected agent/conversation. Managed by a separate `useReducer` in the app, not part of the transport.

```typescript
interface SimulationData {
  agents: Agent[]
  events: SimEvent[]
  board: BoardPost[]
  conversations: Record<string, SimEvent[]>
  stats: AgentStats[]
  tick: number
  aliveCount: number
  totalEvents: number
}

interface DataSource {
  subscribe(callback: (data: SimulationData) => void): void
  unsubscribe(): void
  getData(): SimulationData
  sendAction(action: HandlerAction): Promise<ActionResult>
}

interface ActionResult {
  ok: boolean
  error?: string
}
```

`PollingTransport` implements this interface, fetching all endpoints every 1 second. Components never know or care about the transport — they consume React hooks that read from a context provider.

Swapping to WebSockets or SSE later means writing a new `DataSource` implementation and changing one line in the provider. Zero component changes.

### UI State (separate from transport)

```typescript
interface UIState {
  selectedAgent: string | null
  selectedConversation: string | null
  view: 'graph' | 'agent' | 'conversation'
  controlPanelOpen: boolean
  controlPanelPrefill: Partial<HandlerAction> | null
}
```

Managed by its own `useReducer` in the app shell. Navigation actions (clicking a node, opening the drawer, context menu pre-fill) dispatch to this reducer. Completely independent of the polling cycle.

### Polling Cycle (1s)

Each tick fetches in parallel:
- `GET /api/agents`
- `GET /api/events?since=N` (incremental append)
- `GET /api/board`
- `GET /api/conversations`
- `GET /api/stats`
- `GET /api/status` (tick count, alive count, total events)

Events append incrementally using the existing `since` parameter. Other endpoints return full state and replace previous values.

Conversation keys use the format `"handleA-handleB"` where handles are sorted alphabetically and joined with a hyphen (matching the existing backend format). This key format is the canonical edge identity for the social graph.

### Derived Data (computed, not stored)

- Graph edges: computed from conversations (each key = one edge, array length = weight)
- Agent activity indicators: computed from recent events
- Energy trends: computed from event history within the events buffer

## Backend Changes

Minimal changes to `conwai/dashboard.py`:

1. **Remove** the inline HTML string from the `index()` endpoint
2. **Add** static file serving for the built frontend (`frontend/dist/`)
3. **Add** `GET /api/status` — returns `{"tick": N, "alive": M, "total_events": E}`. Tick value is read from a `data/tick` file that the main simulation loop already writes each cycle. Alive count = number of agent dirs with `alive` == "true". Total events = line count of `events.jsonl`.
4. **Extend** `POST /api/handler` to accept structured JSON actions alongside existing text commands:

```python
# Existing text format still works:
{"message": "@agent_handle hello"}
{"message": "!set_energy agent_handle 500"}

# New structured format:
{"action": "post_board", "content": "hello world"}
{"action": "send_dm", "to": "agent_handle", "content": "hello"}
{"action": "set_energy", "handle": "agent_handle", "value": 500}
{"action": "drain_energy", "handle": "agent_handle", "amount": 100}
{"action": "drop_secret", "handle": "agent_handle", "content": "a secret"}
```

The handler endpoint detects format by checking for the `action` key and dispatches accordingly. Existing text-based commands continue to work.

**Structured action dispatch:** Each structured action translates to the equivalent text command and writes to `handler_input.txt` (same mechanism as existing text commands). The translation happens in `api_handler`:
- `post_board` → writes content as plain text line
- `send_dm` → writes `@{to} {content}`
- `set_energy` → writes `!set_energy {handle} {value}`
- `drain_energy` → writes `!drain {handle} {amount}`
- `drop_secret` → writes `!secret {handle} {content}` (new handler command)

This keeps the structured API as a thin facade over the existing handler file mechanism. New handler commands added to `main.py`'s handler processing loop:
- `!drain {handle} {amount}` — reads current energy, subtracts amount, writes new value to agent's `energy` file. Logs a `handler_drain` event.
- `!secret {handle} {content}` — sends a DM from "WORLD" to the target agent containing the secret text (same mechanism as the existing `WorldEvents.drop_secret`). Logs a `secret_dropped` event.

**Response contract:**
- Success: `{"ok": true}` with HTTP 200
- Validation error (missing field, unknown action, invalid handle): `{"ok": false, "error": "description"}` with HTTP 400
- The existing `api_agent_detail` and `api_agent_context` endpoints return `{"error": "..."}` with HTTP 200 — the frontend should check for the `error` key in all API responses, not rely solely on HTTP status.

## Visual Style — Neon Observatory

### Color Palette

- **Background:** #0f1117 (deep dark), radial gradients from #131520 at center
- **Surface:** rgba(124, 58, 237, 0.08) with rgba(124, 58, 237, 0.15) borders
- **Text primary:** #e2e8f0
- **Text secondary:** #64748b
- **Accent (primary):** #a78bfa (purple/violet)
- **Accent (interactive):** #818cf8 (indigo)
- **Energy healthy:** linear-gradient #34d399 → #6ee7b7, box-shadow rgba(52, 211, 153, 0.3)
- **Energy warning:** linear-gradient #facc15 → #fde68a, box-shadow rgba(234, 179, 8, 0.3)
- **Energy critical:** linear-gradient #ef4444 → #f87171, box-shadow rgba(239, 68, 68, 0.3)
- **Border default:** rgba(124, 58, 237, 0.15)

### Typography

- UI: system sans-serif (-apple-system, system-ui, sans-serif)
- Data/code: monospace for handles, event types, stats

### Effects

- Node borders glow with soft box-shadow matching their assigned color
- Energy bars have subtle halo glow
- Active edges pulse with animated opacity
- Recent activity on agent cards: gentle pulse animation on indicator dot
- Transitions: 200ms ease for state changes, 300ms for drawer open/close

## Not In Scope

- Historical replay or time-travel through simulation state
- Graph clustering or community detection algorithms
- Board-post connections in the graph (DM relationships only)
- Authentication or multi-user support
- Mobile responsiveness (desktop monitoring tool)
- Persistent user preferences or layout customization

## Development Setup

### Vite Dev Proxy

During development, the React dev server (typically port 5173) proxies API requests to the running FastAPI server (typically port 8000):

```typescript
// vite.config.ts
export default defineConfig({
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

### Production Serving

FastAPI mounts the built frontend from `frontend/dist/` as static files and serves `index.html` as a catch-all for client-side routing.
