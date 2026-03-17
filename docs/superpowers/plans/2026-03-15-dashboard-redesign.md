# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the inline HTML dashboard with a React SPA featuring a social graph, agent deep-dives, and rich HANDLER controls.

**Architecture:** Vite + React + TypeScript frontend in `frontend/`, polling the existing FastAPI API every 1s. Transport-agnostic data layer (DataSource interface) keeps components decoupled from fetch mechanism. Backend gets a `/api/status` endpoint, structured handler actions, and static file serving.

**Tech Stack:** React 19, TypeScript, Vite, react-force-graph-2d, FastAPI, Python 3.14

**Spec:** `docs/superpowers/specs/2026-03-15-dashboard-redesign-design.md`

---

## File Map

### Backend (modify)
- `conwai/dashboard.py` — Add `/api/status`, extend `/api/handler` for structured actions, remove inline HTML, add static file serving
- `main.py` — Write `data/tick` file each cycle, add `!secret` handler command

### Frontend (create)
- `frontend/package.json` — Dependencies and scripts
- `frontend/tsconfig.json` — TypeScript config
- `frontend/vite.config.ts` — Vite config with API proxy
- `frontend/index.html` — SPA entry point
- `frontend/src/main.tsx` — React mount point
- `frontend/src/App.tsx` — Root component with providers
- `frontend/src/api/types.ts` — Agent, SimEvent, BoardPost, AgentStats, HandlerAction, etc.
- `frontend/src/api/transport.ts` — DataSource interface + PollingTransport
- `frontend/src/api/hooks.ts` — useSimulation, useUI, useAgentColor
- `frontend/src/api/colors.ts` — getAgentColor utility (deterministic hash → 16-color palette)
- `frontend/src/components/layout/Shell.tsx` — Top-level CSS grid layout
- `frontend/src/components/layout/Sidebar.tsx` — Agent list + sim status
- `frontend/src/components/layout/MainView.tsx` — View router
- `frontend/src/components/layout/EventTicker.tsx` — Bottom bar event stream
- `frontend/src/components/graph/SocialGraph.tsx` — Force-directed graph
- `frontend/src/components/agents/AgentCard.tsx` — Compact sidebar card
- `frontend/src/components/agents/AgentDetail.tsx` — Full agent deep-dive
- `frontend/src/components/feed/Board.tsx` — Board posts panel
- `frontend/src/components/feed/ConversationView.tsx` — DM thread view
- `frontend/src/components/controls/ControlPanel.tsx` — Slide-out drawer
- `frontend/src/components/controls/ContextMenu.tsx` — Right-click/hover actions
- `frontend/src/index.css` — Global styles (Neon Observatory theme)

---

## Chunk 1: Backend Changes

### Task 1: Write tick file from main loop

**Files:**
- Modify: `main.py:150-187` (main loop)

- [ ] **Step 1: Add tick file write to main loop**

In `main.py`, after `ctx.tick += 1` (line 151), write the tick value to `data/tick`:

```python
Path("data/tick").write_text(str(ctx.tick))
```

Add `Path` import if not already present (it's already imported on line 3).

- [ ] **Step 2: Verify it works**

Run: `python -c "from pathlib import Path; Path('data').mkdir(exist_ok=True); Path('data/tick').write_text('42'); print(Path('data/tick').read_text())"`
Expected: `42`

- [ ] **Step 3: Commit**

```bash
git add main.py
git commit -m "feat: write tick counter to data/tick each cycle"
```

### Task 2: Add /api/status endpoint

**Files:**
- Modify: `conwai/dashboard.py`

- [ ] **Step 1: Write test for status endpoint**

Create `tests/test_dashboard.py`:

```python
import json
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from conwai.dashboard import app

client = TestClient(app)


def test_status_returns_tick_alive_total(tmp_path):
    tick_file = tmp_path / "tick"
    tick_file.write_text("42")
    events_file = tmp_path / "events.jsonl"
    events_file.write_text('{"t":1,"entity":"a","type":"x","data":{}}\n' * 3)
    agents_dir = tmp_path / "agents"
    (agents_dir / "agent1").mkdir(parents=True)
    (agents_dir / "agent1" / "alive").write_text("true")
    (agents_dir / "agent2").mkdir(parents=True)
    (agents_dir / "agent2" / "alive").write_text("false")

    with patch("conwai.dashboard.Path") as mock_path:
        # We need a more targeted approach - patch the module-level constants
        pass

    # Simpler: patch the constants directly
    with (
        patch("conwai.dashboard.EVENTS_PATH", events_file),
        patch("conwai.dashboard.AGENTS_DIR", agents_dir),
    ):
        # Also need to patch a TICK_PATH constant
        with patch("conwai.dashboard.TICK_PATH", tick_file):
            resp = client.get("/api/status")
            assert resp.status_code == 200
            data = resp.json()
            assert data["tick"] == 42
            assert data["alive"] == 1
            assert data["total_events"] == 3
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_dashboard.py::test_status_returns_tick_alive_total -v`
Expected: FAIL (TICK_PATH not defined, no endpoint)

- [ ] **Step 3: Implement /api/status**

In `conwai/dashboard.py`, add `TICK_PATH` constant and the endpoint:

```python
TICK_PATH = Path("data/tick")

@app.get("/api/status")
def api_status():
    tick = int(TICK_PATH.read_text().strip()) if TICK_PATH.exists() else 0
    alive = 0
    if AGENTS_DIR.exists():
        for d in AGENTS_DIR.iterdir():
            if d.is_dir():
                alive_path = d / "alive"
                if not alive_path.exists() or alive_path.read_text().strip() == "true":
                    alive += 1
    total_events = 0
    if EVENTS_PATH.exists():
        total_events = sum(1 for _ in EVENTS_PATH.read_text().strip().splitlines() if _.strip())
    return {"tick": tick, "alive": alive, "total_events": total_events}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_dashboard.py::test_status_returns_tick_alive_total -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/dashboard.py tests/test_dashboard.py
git commit -m "feat: add /api/status endpoint for tick, alive count, total events"
```

### Task 3: Extend /api/handler for structured actions

**Files:**
- Modify: `conwai/dashboard.py:128-136` (api_handler function)

- [ ] **Step 1: Write tests for structured handler actions**

Add to `tests/test_dashboard.py`:

```python
def test_handler_structured_post_board(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "post_board", "content": "hello world"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert handler_file.read_text().strip() == "hello world"


def test_handler_structured_send_dm(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "send_dm", "to": "abc123", "content": "hey"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert handler_file.read_text().strip() == "@abc123 hey"


def test_handler_structured_set_energy(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "set_energy", "handle": "abc123", "value": 500})
        assert resp.status_code == 200
        assert handler_file.read_text().strip() == "!set_energy abc123 500"


def test_handler_structured_drain_energy(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "drain_energy", "handle": "abc123", "amount": 100})
        assert resp.status_code == 200
        assert handler_file.read_text().strip() == "!drain abc123 100"


def test_handler_structured_drop_secret(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "drop_secret", "handle": "abc123", "content": "a secret"})
        assert resp.status_code == 200
        assert handler_file.read_text().strip() == "!secret abc123 a secret"


def test_handler_structured_unknown_action(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"action": "unknown_thing"})
        assert resp.status_code == 400
        assert resp.json()["ok"] is False


def test_handler_legacy_message_still_works(tmp_path):
    handler_file = tmp_path / "handler_input.txt"
    with patch("conwai.dashboard.HANDLER_FILE", handler_file):
        resp = client.post("/api/handler", json={"message": "hello board"})
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
        assert handler_file.read_text().strip() == "hello board"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_dashboard.py -k "handler" -v`
Expected: Most FAIL (structured actions not implemented)

- [ ] **Step 3: Implement structured handler dispatch**

Replace the `api_handler` function in `conwai/dashboard.py`:

```python
@app.post("/api/handler")
async def api_handler(request: Request):
    body = await request.json()

    # Structured action format
    if "action" in body:
        action = body["action"]
        try:
            if action == "post_board":
                line = body["content"]
            elif action == "send_dm":
                line = f"@{body['to']} {body['content']}"
            elif action == "set_energy":
                line = f"!set_energy {body['handle']} {body['value']}"
            elif action == "drain_energy":
                line = f"!drain {body['handle']} {body['amount']}"
            elif action == "drop_secret":
                line = f"!secret {body['handle']} {body['content']}"
            else:
                return JSONResponse({"ok": False, "error": f"unknown action: {action}"}, status_code=400)
        except KeyError as e:
            return JSONResponse({"ok": False, "error": f"missing field: {e}"}, status_code=400)

        with open(HANDLER_FILE, "a") as f:
            f.write(line + "\n")
        return {"ok": True}

    # Legacy text format
    msg = body.get("message", "").strip()
    if not msg:
        return JSONResponse({"ok": False, "error": "empty message"}, status_code=400)
    with open(HANDLER_FILE, "a") as f:
        f.write(msg + "\n")
    return {"ok": True, "message": msg}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_dashboard.py -k "handler" -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add conwai/dashboard.py tests/test_dashboard.py
git commit -m "feat: extend /api/handler to accept structured action JSON"
```

### Task 4: Add !secret handler command to main.py

**Files:**
- Modify: `main.py:26-78` (watch_handler_file function)

- [ ] **Step 1: Add !secret command handling**

In `main.py`, in the `watch_handler_file` function, add a new `elif` branch after the `!set_energy` block (after line 63):

```python
elif line.startswith("!secret "):
    parts = line.split(" ", 2)
    if len(parts) >= 3 and parts[1] in ctx.agent_map:
        handle, content = parts[1], parts[2]
        ctx.bus.send("WORLD", handle, content)
        ctx.log("WORLD", "secret_dropped", {"to": handle, "content": content})
        print(f"[HANDLER] dropped secret to {handle}: {content}", flush=True)
```

- [ ] **Step 2: Commit**

```bash
git add main.py
git commit -m "feat: add !secret handler command for dropping secrets to agents"
```

---

## Chunk 2: Frontend Scaffold + Data Layer

### Task 5: Initialize Vite + React + TypeScript project

**Files:**
- Create: `frontend/package.json`, `frontend/tsconfig.json`, `frontend/vite.config.ts`, `frontend/index.html`, `frontend/src/main.tsx`

- [ ] **Step 1: Scaffold the project**

```bash
cd /Users/pat/Code/conwai
npm create vite@latest frontend -- --template react-ts
```

- [ ] **Step 2: Install dependencies**

```bash
cd /Users/pat/Code/conwai/frontend
npm install
npm install react-force-graph-2d
```

- [ ] **Step 3: Configure Vite proxy**

Replace `frontend/vite.config.ts`:

```typescript
import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8000'
    }
  }
})
```

- [ ] **Step 4: Clean up scaffold**

Remove the default Vite boilerplate files that we won't use:
- Delete `frontend/src/App.css`
- Delete `frontend/src/assets/react.svg`
- Delete `frontend/public/vite.svg`

- [ ] **Step 5: Update .gitignore**

Append to `.gitignore`:

```
frontend/node_modules/
frontend/dist/
```

This ensures neither `node_modules` nor build artifacts are committed.

- [ ] **Step 6: Verify dev server starts**

```bash
cd /Users/pat/Code/conwai/frontend && npm run dev -- --host 127.0.0.1 &
sleep 3
curl -s http://127.0.0.1:5173 | head -5
kill %1
```

Expected: HTML containing `<div id="root">` or similar Vite output.

- [ ] **Step 7: Commit**

```bash
git add frontend/ .gitignore
git commit -m "feat: scaffold Vite + React + TypeScript frontend"
```

### Task 6: Define TypeScript types

**Files:**
- Create: `frontend/src/api/types.ts`

- [ ] **Step 1: Create types file**

```typescript
// Types matching the FastAPI backend responses

export interface Agent {
  handle: string
  personality: string
  soul: string
  memory: string
  energy: number | null
  alive: boolean
}

export interface SimEvent {
  idx: number
  t: number
  entity: string
  type: string
  data: Record<string, any>
}

export interface BoardPost extends SimEvent {
  type: 'board_post'
  data: { content: string }
}

export interface AgentStats {
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

export type HandlerAction =
  | { action: 'post_board'; content: string }
  | { action: 'send_dm'; to: string; content: string }
  | { action: 'set_energy'; handle: string; value: number }
  | { action: 'drain_energy'; handle: string; amount: number }
  | { action: 'drop_secret'; handle: string; content: string }

export interface ActionResult {
  ok: boolean
  error?: string
}

export interface SimulationData {
  agents: Agent[]
  events: SimEvent[]
  board: BoardPost[]
  conversations: Record<string, SimEvent[]>
  stats: AgentStats[]
  tick: number
  aliveCount: number
  totalEvents: number
}

export interface UIState {
  selectedAgent: string | null
  selectedConversation: string | null
  view: 'graph' | 'agent' | 'conversation'
  controlPanelOpen: boolean
  controlPanelPrefill: Partial<HandlerAction> | null
}

export interface DataSource {
  subscribe(callback: (data: SimulationData) => void): void
  unsubscribe(): void
  getData(): SimulationData
  sendAction(action: HandlerAction): Promise<ActionResult>
}
```

- [ ] **Step 2: Verify types compile**

Run: `cd /Users/pat/Code/conwai/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/types.ts
git commit -m "feat: define TypeScript types for simulation data layer"
```

### Task 7: Implement agent color utility

**Files:**
- Create: `frontend/src/api/colors.ts`

- [ ] **Step 1: Create colors module**

```typescript
// 16-color neon palette for dark backgrounds
const PALETTE = [
  '#818cf8', // indigo
  '#f472b6', // pink
  '#34d399', // emerald
  '#fb923c', // orange
  '#a78bfa', // violet
  '#38bdf8', // sky
  '#facc15', // yellow
  '#f87171', // red
  '#2dd4bf', // teal
  '#c084fc', // purple
  '#4ade80', // green
  '#f97316', // deep orange
  '#67e8f9', // cyan
  '#e879f9', // fuchsia
  '#a3e635', // lime
  '#fbbf24', // amber
]

function hashString(str: string): number {
  let hash = 0
  for (let i = 0; i < str.length; i++) {
    hash = ((hash << 5) - hash + str.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

export function getAgentColor(handle: string): string {
  return PALETTE[hashString(handle) % PALETTE.length]
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/api/colors.ts
git commit -m "feat: deterministic agent color utility with 16-color neon palette"
```

### Task 8: Implement PollingTransport

**Files:**
- Create: `frontend/src/api/transport.ts`

- [ ] **Step 1: Create transport module**

```typescript
import type { DataSource, SimulationData, HandlerAction, ActionResult, SimEvent, BoardPost } from './types'

const EMPTY_DATA: SimulationData = {
  agents: [],
  events: [],
  board: [],
  conversations: {},
  stats: [],
  tick: 0,
  aliveCount: 0,
  totalEvents: 0,
}

export class PollingTransport implements DataSource {
  private data: SimulationData = EMPTY_DATA
  private callbacks: Set<(data: SimulationData) => void> = new Set()
  private intervalId: ReturnType<typeof setInterval> | null = null
  private lastEventIdx = 0

  constructor(private pollIntervalMs = 1000) {}

  subscribe(callback: (data: SimulationData) => void): void {
    this.callbacks.add(callback)
    if (this.callbacks.size === 1) {
      this.start()
    }
    // Immediately emit current state
    callback(this.data)
  }

  unsubscribe(): void {
    this.callbacks.clear()
    this.stop()
  }

  getData(): SimulationData {
    return this.data
  }

  async sendAction(action: HandlerAction): Promise<ActionResult> {
    const resp = await fetch('/api/handler', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(action),
    })
    return resp.json()
  }

  private start(): void {
    this.poll()
    this.intervalId = setInterval(() => this.poll(), this.pollIntervalMs)
  }

  private stop(): void {
    if (this.intervalId) {
      clearInterval(this.intervalId)
      this.intervalId = null
    }
  }

  private async poll(): Promise<void> {
    try {
      const [agents, newEvents, board, conversations, stats, status] = await Promise.all([
        fetch('/api/agents').then(r => r.json()),
        fetch(`/api/events?since=${this.lastEventIdx}`).then(r => r.json()),
        fetch('/api/board').then(r => r.json()),
        fetch('/api/conversations').then(r => r.json()),
        fetch('/api/stats').then(r => r.json()),
        fetch('/api/status').then(r => r.json()),
      ])

      // Append new events, cap at 500
      let events = [...this.data.events, ...newEvents]
      if (events.length > 500) {
        events = events.slice(events.length - 500)
      }
      if (newEvents.length > 0) {
        this.lastEventIdx = newEvents[newEvents.length - 1].idx + 1
      }

      this.data = {
        agents,
        events,
        board: board as BoardPost[],
        conversations,
        stats,
        tick: status.tick ?? 0,
        aliveCount: status.alive ?? 0,
        totalEvents: status.total_events ?? 0,
      }

      for (const cb of this.callbacks) {
        cb(this.data)
      }
    } catch (err) {
      // Silently skip failed polls — next cycle will retry
      console.warn('Poll failed:', err)
    }
  }
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /Users/pat/Code/conwai/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/transport.ts
git commit -m "feat: implement PollingTransport with 1s interval and incremental events"
```

### Task 9: Create React context and hooks

**Files:**
- Create: `frontend/src/api/hooks.ts`

- [ ] **Step 1: Create hooks module**

```typescript
import { createContext, useContext, useReducer, useEffect, useState, useCallback, type ReactNode, type Dispatch } from 'react'
import type { SimulationData, UIState, DataSource, HandlerAction, ActionResult } from './types'

// --- Simulation data context (from transport) ---

const SimulationContext = createContext<SimulationData | null>(null)
const SendActionContext = createContext<((action: HandlerAction) => Promise<ActionResult>) | null>(null)

export function SimulationProvider({ dataSource, children }: { dataSource: DataSource; children: ReactNode }) {
  const [data, setData] = useState<SimulationData>(dataSource.getData())

  useEffect(() => {
    dataSource.subscribe(setData)
    return () => dataSource.unsubscribe()
  }, [dataSource])

  const sendAction = useCallback(
    (action: HandlerAction) => dataSource.sendAction(action),
    [dataSource],
  )

  return (
    <SimulationContext.Provider value={data}>
      <SendActionContext.Provider value={sendAction}>
        {children}
      </SendActionContext.Provider>
    </SimulationContext.Provider>
  )
}

export function useSimulation(): SimulationData {
  const ctx = useContext(SimulationContext)
  if (!ctx) throw new Error('useSimulation must be used within SimulationProvider')
  return ctx
}

export function useSendAction(): (action: HandlerAction) => Promise<ActionResult> {
  const ctx = useContext(SendActionContext)
  if (!ctx) throw new Error('useSendAction must be used within SimulationProvider')
  return ctx
}

// --- UI state context ---

type UIAction =
  | { type: 'SELECT_AGENT'; handle: string }
  | { type: 'SELECT_CONVERSATION'; key: string }
  | { type: 'SHOW_GRAPH' }
  | { type: 'TOGGLE_CONTROL_PANEL' }
  | { type: 'OPEN_CONTROL_PANEL'; prefill?: Partial<HandlerAction> }
  | { type: 'CLOSE_CONTROL_PANEL' }

const initialUIState: UIState = {
  selectedAgent: null,
  selectedConversation: null,
  view: 'graph',
  controlPanelOpen: false,
  controlPanelPrefill: null,
}

function uiReducer(state: UIState, action: UIAction): UIState {
  switch (action.type) {
    case 'SELECT_AGENT':
      return { ...state, selectedAgent: action.handle, selectedConversation: null, view: 'agent' }
    case 'SELECT_CONVERSATION':
      return { ...state, selectedConversation: action.key, selectedAgent: null, view: 'conversation' }
    case 'SHOW_GRAPH':
      return { ...state, selectedAgent: null, selectedConversation: null, view: 'graph' }
    case 'TOGGLE_CONTROL_PANEL':
      return { ...state, controlPanelOpen: !state.controlPanelOpen, controlPanelPrefill: null }
    case 'OPEN_CONTROL_PANEL':
      return { ...state, controlPanelOpen: true, controlPanelPrefill: action.prefill ?? null }
    case 'CLOSE_CONTROL_PANEL':
      return { ...state, controlPanelOpen: false, controlPanelPrefill: null }
    default:
      return state
  }
}

const UIStateContext = createContext<UIState | null>(null)
const UIDispatchContext = createContext<Dispatch<UIAction> | null>(null)

export function UIProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(uiReducer, initialUIState)

  return (
    <UIStateContext.Provider value={state}>
      <UIDispatchContext.Provider value={dispatch}>
        {children}
      </UIDispatchContext.Provider>
    </UIStateContext.Provider>
  )
}

export function useUIState(): UIState {
  const ctx = useContext(UIStateContext)
  if (!ctx) throw new Error('useUIState must be used within UIProvider')
  return ctx
}

export function useUIDispatch(): Dispatch<UIAction> {
  const ctx = useContext(UIDispatchContext)
  if (!ctx) throw new Error('useUIDispatch must be used within UIProvider')
  return ctx
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /Users/pat/Code/conwai/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
git add frontend/src/api/hooks.ts
git commit -m "feat: React context providers and hooks for simulation data and UI state"
```

---

## Chunk 3: Layout Shell + Sidebar

### Task 10: Global styles (Neon Observatory theme)

**Files:**
- Create: `frontend/src/index.css`

- [ ] **Step 1: Write global CSS**

```css
:root {
  --bg-primary: #0f1117;
  --bg-surface: rgba(124, 58, 237, 0.08);
  --bg-surface-hover: rgba(124, 58, 237, 0.12);
  --border: rgba(124, 58, 237, 0.15);
  --border-hover: rgba(124, 58, 237, 0.3);
  --text-primary: #e2e8f0;
  --text-secondary: #64748b;
  --accent: #a78bfa;
  --accent-interactive: #818cf8;
  --energy-healthy: #34d399;
  --energy-warning: #facc15;
  --energy-critical: #ef4444;
  --font-ui: -apple-system, system-ui, sans-serif;
  --font-mono: 'SF Mono', 'Fira Code', 'Fira Mono', Menlo, monospace;
}

*, *::before, *::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

html, body, #root {
  height: 100%;
  overflow: hidden;
}

body {
  font-family: var(--font-ui);
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 13px;
  -webkit-font-smoothing: antialiased;
}

::-webkit-scrollbar {
  width: 6px;
}

::-webkit-scrollbar-track {
  background: transparent;
}

::-webkit-scrollbar-thumb {
  background: rgba(124, 58, 237, 0.2);
  border-radius: 3px;
}

::-webkit-scrollbar-thumb:hover {
  background: rgba(124, 58, 237, 0.4);
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
```

- [ ] **Step 2: Import in main.tsx**

Replace `frontend/src/main.tsx`:

```tsx
import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/index.css frontend/src/main.tsx
git commit -m "feat: Neon Observatory global styles and entry point"
```

### Task 11: App root with providers

**Files:**
- Modify: `frontend/src/App.tsx`

- [ ] **Step 1: Write App component**

```tsx
import { useMemo } from 'react'
import { SimulationProvider, UIProvider } from './api/hooks'
import { PollingTransport } from './api/transport'
import { Shell } from './components/layout/Shell'

export default function App() {
  const dataSource = useMemo(() => new PollingTransport(1000), [])

  return (
    <SimulationProvider dataSource={dataSource}>
      <UIProvider>
        <Shell />
      </UIProvider>
    </SimulationProvider>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/App.tsx
git commit -m "feat: App root with simulation and UI providers"
```

### Task 12: Shell layout component

**Files:**
- Create: `frontend/src/components/layout/Shell.tsx`

- [ ] **Step 1: Create Shell**

```tsx
import { useUIState } from '../../api/hooks'
import { Sidebar } from './Sidebar'
import { MainView } from './MainView'
import { EventTicker } from './EventTicker'

export function Shell() {
  const { controlPanelOpen } = useUIState()

  return (
    <div style={{
      display: 'grid',
      gridTemplateColumns: `240px 1fr${controlPanelOpen ? ' 320px' : ''}`,
      gridTemplateRows: '1fr 48px',
      height: '100vh',
      gap: 0,
    }}>
      <div style={{
        gridRow: '1 / 3',
        borderRight: '1px solid var(--border)',
        overflow: 'hidden',
        display: 'flex',
        flexDirection: 'column',
      }}>
        <Sidebar />
      </div>

      <div style={{ overflow: 'hidden', position: 'relative' }}>
        <MainView />
      </div>

      <div style={{
        borderTop: '1px solid var(--border)',
        gridColumn: controlPanelOpen ? '2 / 4' : '2',
      }}>
        <EventTicker />
      </div>

      {controlPanelOpen && (
        <div style={{
          gridRow: '1',
          borderLeft: '1px solid var(--border)',
          overflow: 'auto',
        }}>
          {/* ControlPanel placeholder */}
          <div style={{ padding: 16, color: 'var(--text-secondary)' }}>Control Panel</div>
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/Shell.tsx
git commit -m "feat: Shell layout component with CSS grid zones"
```

### Task 13: AgentCard component

**Files:**
- Create: `frontend/src/components/agents/AgentCard.tsx`

- [ ] **Step 1: Create AgentCard**

```tsx
import type { Agent, SimEvent } from '../../api/types'
import { getAgentColor } from '../../api/colors'

const RECENCY_WINDOW_MS = 10_000

interface AgentCardProps {
  agent: Agent
  events: SimEvent[]
  maxEnergy: number
  selected: boolean
  onClick: () => void
}

export function AgentCard({ agent, events, maxEnergy, selected, onClick }: AgentCardProps) {
  const color = getAgentColor(agent.handle)
  const energyPct = agent.energy != null && maxEnergy > 0
    ? Math.round((agent.energy / maxEnergy) * 100)
    : 0
  const now = Date.now() / 1000
  const recentlyActive = events.some(
    e => e.entity === agent.handle && (now - e.t) < RECENCY_WINDOW_MS / 1000
  )

  const energyColor = energyPct < 20
    ? 'var(--energy-critical)'
    : energyPct < 50
    ? 'var(--energy-warning)'
    : 'var(--energy-healthy)'

  return (
    <div
      onClick={onClick}
      style={{
        padding: '8px 12px',
        borderLeft: `2px solid ${selected ? color : 'transparent'}`,
        background: selected ? 'var(--bg-surface)' : 'transparent',
        cursor: 'pointer',
        transition: 'background 200ms, border-color 200ms',
      }}
      onMouseEnter={e => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.background = 'var(--bg-surface-hover)'
      }}
      onMouseLeave={e => {
        if (!selected) (e.currentTarget as HTMLDivElement).style.background = 'transparent'
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {recentlyActive && (
          <span style={{
            width: 6, height: 6, borderRadius: '50%',
            background: color, boxShadow: `0 0 6px ${color}`,
            animation: 'pulse 2s ease-in-out infinite',
          }} />
        )}
        <span style={{ color, fontFamily: 'var(--font-mono)', fontWeight: 600, fontSize: 12 }}>
          {agent.handle}
        </span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 11, marginLeft: 'auto' }}>
          {agent.energy != null ? agent.energy : '?'}
        </span>
      </div>
      <div style={{
        background: 'rgba(255,255,255,0.05)', height: 3, borderRadius: 2, margin: '4px 0',
      }}>
        <div style={{
          height: '100%', borderRadius: 2, width: `${energyPct}%`,
          background: energyColor,
          boxShadow: `0 0 6px ${energyColor}40`,
          transition: 'width 300ms ease',
        }} />
      </div>
      <div style={{ color: 'var(--text-secondary)', fontSize: 10 }}>
        {agent.personality}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/agents/AgentCard.tsx
git commit -m "feat: AgentCard component with energy bar and activity indicator"
```

### Task 14: Sidebar component

**Files:**
- Create: `frontend/src/components/layout/Sidebar.tsx`

- [ ] **Step 1: Create Sidebar**

```tsx
import { useSimulation, useUIState, useUIDispatch } from '../../api/hooks'
import { AgentCard } from '../agents/AgentCard'

export function Sidebar() {
  const { agents, events, tick, aliveCount, totalEvents } = useSimulation()
  const { selectedAgent } = useUIState()
  const dispatch = useUIDispatch()

  const maxEnergy = agents.reduce((max, a) => Math.max(max, a.energy ?? 0), 0)
  const sorted = [...agents].sort((a, b) => (b.energy ?? 0) - (a.energy ?? 0))

  return (
    <>
      <div style={{
        padding: '12px 16px',
        borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
      }}>
        <span
          onClick={() => dispatch({ type: 'SHOW_GRAPH' })}
          style={{
            color: 'var(--accent)', fontWeight: 600, fontSize: 15,
            letterSpacing: 1, cursor: 'pointer',
          }}
        >
          CONWAI
        </span>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '4px 0' }}>
        {sorted.map(agent => (
          <AgentCard
            key={agent.handle}
            agent={agent}
            events={events}
            maxEnergy={maxEnergy}
            selected={selectedAgent === agent.handle}
            onClick={() => dispatch({ type: 'SELECT_AGENT', handle: agent.handle })}
          />
        ))}
      </div>

      <div style={{
        padding: '8px 16px',
        borderTop: '1px solid var(--border)',
        display: 'flex', gap: 12,
        color: 'var(--text-secondary)', fontSize: 11,
        fontFamily: 'var(--font-mono)',
      }}>
        <span>tick {tick}</span>
        <span>{aliveCount} alive</span>
        <span>{totalEvents} events</span>
      </div>
    </>
  )
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/layout/Sidebar.tsx
git commit -m "feat: Sidebar with sorted agent cards and simulation status"
```

### Task 15: MainView router and EventTicker placeholder

**Files:**
- Create: `frontend/src/components/layout/MainView.tsx`, `frontend/src/components/layout/EventTicker.tsx`

- [ ] **Step 1: Create MainView**

```tsx
import { useUIState } from '../../api/hooks'

export function MainView() {
  const { view, selectedAgent, selectedConversation } = useUIState()

  return (
    <div style={{ height: '100%', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
      {view === 'graph' && (
        <div style={{ color: 'var(--text-secondary)' }}>Social Graph (coming next)</div>
      )}
      {view === 'agent' && (
        <div style={{ color: 'var(--text-secondary)' }}>Agent Detail: {selectedAgent}</div>
      )}
      {view === 'conversation' && (
        <div style={{ color: 'var(--text-secondary)' }}>Conversation: {selectedConversation}</div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Create EventTicker**

```tsx
import { useSimulation } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'

const TYPE_COLORS: Record<string, string> = {
  board_post: '#34d399',
  dm_sent: '#818cf8',
  inspect: '#64748b',
  remember: '#facc15',
  soul_updated: '#67e8f9',
  secret_dropped: '#f87171',
  question_posted: '#a78bfa',
  code_submitted: '#fb923c',
  code_solved: '#4ade80',
  code_wrong_guess: '#f97316',
}

function eventContent(e: { type: string; entity: string; data: Record<string, any> }): string {
  if (e.type === 'dm_sent') return `→ ${e.data.to}: ${e.data.content ?? ''}`
  if (e.type === 'board_post') return e.data.content ?? ''
  if (e.type === 'inspect') return `inspected ${e.data.target ?? '?'}`
  if (e.type === 'code_submitted') return `submitted ${e.data.guess ?? '?'}`
  if (e.type === 'code_solved') return `solved!`
  return e.data.content ?? e.data.secret ?? e.data.question ?? ''
}

export function EventTicker() {
  const { events } = useSimulation()
  const recent = events
    .filter(e => e.type !== 'sleeping' && e.type !== 'no_energy')
    .slice(-30)

  return (
    <div style={{
      height: '100%', overflowX: 'auto', overflowY: 'hidden',
      display: 'flex', alignItems: 'center', gap: 16,
      padding: '0 16px', whiteSpace: 'nowrap',
      fontFamily: 'var(--font-mono)', fontSize: 11,
    }}>
      {recent.map(e => (
        <span key={e.idx} style={{ display: 'inline-flex', gap: 4, flexShrink: 0 }}>
          <span style={{ color: getAgentColor(e.entity) }}>{e.entity}</span>
          <span style={{ color: TYPE_COLORS[e.type] ?? 'var(--text-secondary)' }}>{e.type}</span>
          <span style={{ color: 'var(--text-secondary)', maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {eventContent(e).slice(0, 80)}
          </span>
        </span>
      ))}
    </div>
  )
}
```

- [ ] **Step 3: Verify app renders**

Run the dev server and confirm the layout shows sidebar with agents, a center placeholder, and bottom ticker:

```bash
cd /Users/pat/Code/conwai/frontend && npx tsc --noEmit
```

Expected: No type errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/layout/MainView.tsx frontend/src/components/layout/EventTicker.tsx
git commit -m "feat: MainView router and EventTicker components"
```

---

## Chunk 4: Social Graph

### Task 16: SocialGraph component

**Files:**
- Create: `frontend/src/components/graph/SocialGraph.tsx`

- [ ] **Step 1: Create SocialGraph**

```tsx
import { useMemo, useCallback, useRef, useEffect } from 'react'
import ForceGraph2D, { type ForceGraphMethods } from 'react-force-graph-2d'
import { useSimulation, useUIState, useUIDispatch } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'
import type { Agent } from '../../api/types'

const RECENCY_WINDOW_S = 10
const EDGE_FADE_S = 60
const EDGE_MIN_OPACITY = 0.3

interface GraphNode {
  id: string
  agent: Agent
  color: string
  energy: number
  recentlyActive: boolean
}

interface GraphLink {
  source: string
  target: string
  weight: number
  lastActivity: number
}

export function SocialGraph() {
  const { agents, conversations, events } = useSimulation()
  const { selectedAgent } = useUIState()
  const dispatch = useUIDispatch()
  const graphRef = useRef<ForceGraphMethods<GraphNode, GraphLink>>(undefined)

  const maxEnergy = agents.reduce((max, a) => Math.max(max, a.energy ?? 0), 1)
  const now = Date.now() / 1000

  // Track dead agents for fade-out
  const prevAgentsRef = useRef<Set<string>>(new Set())
  const [fadingAgents, setFadingAgents] = useState<Map<string, { agent: Agent; fadeStart: number }>>(new Map())

  useEffect(() => {
    const currentHandles = new Set(agents.map(a => a.handle))
    const prev = prevAgentsRef.current

    // Detect disappeared agents
    for (const handle of prev) {
      if (!currentHandles.has(handle) && !fadingAgents.has(handle)) {
        // Agent disappeared — start fade
        setFadingAgents(m => {
          const next = new Map(m)
          next.set(handle, { agent: { handle, personality: '', soul: '', memory: '', energy: 0, alive: false }, fadeStart: Date.now() })
          return next
        })
      }
    }

    // Cancel fade if agent reappears
    for (const handle of currentHandles) {
      if (fadingAgents.has(handle)) {
        setFadingAgents(m => { const next = new Map(m); next.delete(handle); return next })
      }
    }

    prevAgentsRef.current = currentHandles
  }, [agents])

  // Clean up faded agents after 3s
  useEffect(() => {
    if (fadingAgents.size === 0) return
    const timer = setInterval(() => {
      setFadingAgents(m => {
        const next = new Map(m)
        for (const [handle, { fadeStart }] of next) {
          if (Date.now() - fadeStart > 3000) next.delete(handle)
        }
        return next.size !== m.size ? next : m
      })
    }, 500)
    return () => clearInterval(timer)
  }, [fadingAgents.size])

  const graphData = useMemo(() => {
    const allAgents = [...agents, ...Array.from(fadingAgents.values()).map(f => f.agent)]
    const nodes: GraphNode[] = allAgents.map(a => ({
      id: a.handle,
      agent: a,
      color: getAgentColor(a.handle),
      energy: a.energy ?? 0,
      recentlyActive: events.some(
        e => e.entity === a.handle && (now - e.t) < RECENCY_WINDOW_S
      ),
    }))

    const links: GraphLink[] = Object.entries(conversations).map(([key, msgs]) => {
      const [source, target] = key.split('-')
      const lastMsg = msgs[msgs.length - 1]
      return {
        source,
        target,
        weight: msgs.length,
        lastActivity: lastMsg?.t ?? 0,
      }
    })

    return { nodes, links }
  }, [agents, conversations, events, now])

  const handleNodeClick = useCallback((node: GraphNode) => {
    dispatch({ type: 'SELECT_AGENT', handle: node.id })
  }, [dispatch])

  const handleLinkClick = useCallback((link: GraphLink) => {
    const src = typeof link.source === 'object' ? (link.source as any).id : link.source
    const tgt = typeof link.target === 'object' ? (link.target as any).id : link.target
    const key = [src, tgt].sort().join('-')
    dispatch({ type: 'SELECT_CONVERSATION', key })
  }, [dispatch])

  // Node tooltip on hover
  const nodeLabel = useCallback((node: GraphNode) => {
    const a = node.agent
    return `${a.handle}\n${a.personality}\nenergy: ${a.energy ?? '?'}\n${a.soul ? a.soul.slice(0, 80) : ''}`
  }, [])

  const paintNode = useCallback((node: GraphNode, ctx: CanvasRenderingContext2D) => {
    const radius = 4 + (node.energy / maxEnergy) * 12
    const isSelected = selectedAgent === node.id

    // Fade out dying agents
    const fadeEntry = fadingAgents.get(node.id)
    if (fadeEntry) {
      const elapsed = Date.now() - fadeEntry.fadeStart
      ctx.globalAlpha = Math.max(0, 1 - elapsed / 3000)
    }

    // Glow effect for active nodes
    if (node.recentlyActive) {
      ctx.beginPath()
      ctx.arc(node.x!, node.y!, radius + 4, 0, Math.PI * 2)
      ctx.fillStyle = node.color + '30'
      ctx.fill()
    }

    // Node circle
    ctx.beginPath()
    ctx.arc(node.x!, node.y!, radius, 0, Math.PI * 2)
    ctx.fillStyle = node.color + '20'
    ctx.fill()
    ctx.strokeStyle = isSelected ? '#e2e8f0' : node.color
    ctx.lineWidth = isSelected ? 2 : 1.5
    ctx.stroke()

    // Label
    ctx.font = '4px sans-serif'
    ctx.textAlign = 'center'
    ctx.textBaseline = 'top'
    ctx.fillStyle = node.color
    ctx.fillText(node.id, node.x!, node.y! + radius + 3)

    // Reset alpha
    ctx.globalAlpha = 1
  }, [maxEnergy, selectedAgent, fadingAgents])

  const paintLink = useCallback((link: GraphLink, ctx: CanvasRenderingContext2D) => {
    const src = link.source as any
    const tgt = link.target as any
    if (!src.x || !tgt.x) return

    const age = now - link.lastActivity
    const opacity = age > EDGE_FADE_S
      ? EDGE_MIN_OPACITY
      : EDGE_MIN_OPACITY + (1 - EDGE_MIN_OPACITY) * (1 - age / EDGE_FADE_S)

    ctx.beginPath()
    ctx.moveTo(src.x, src.y)
    ctx.lineTo(tgt.x, tgt.y)
    ctx.strokeStyle = `rgba(124, 58, 237, ${opacity})`
    ctx.lineWidth = Math.min(0.5 + link.weight * 0.3, 4)
    ctx.stroke()
  }, [now])

  return (
    <div style={{
      width: '100%', height: '100%',
      background: 'radial-gradient(ellipse at center, #131520 0%, #0f1117 70%)',
    }}>
      <ForceGraph2D
        ref={graphRef}
        graphData={graphData}
        nodeCanvasObject={paintNode}
        nodeLabel={nodeLabel}
        linkCanvasObject={paintLink}
        linkDirectionalParticles={(link: GraphLink) => {
          // Show particles on edges with recent activity
          const age = now - link.lastActivity
          return age < RECENCY_WINDOW_S ? 3 : 0
        }}
        linkDirectionalParticleSpeed={0.01}
        linkDirectionalParticleColor={() => 'rgba(167, 139, 250, 0.6)'}
        linkDirectionalParticleWidth={2}
        onNodeClick={handleNodeClick}
        onLinkClick={handleLinkClick}
        nodeId="id"
        enableZoomInteraction={true}
        enablePanInteraction={true}
        enableNodeDrag={true}
        cooldownTicks={100}
        backgroundColor="transparent"
      />
    </div>
  )
}
```

- [ ] **Step 2: Verify it compiles**

Run: `cd /Users/pat/Code/conwai/frontend && npx tsc --noEmit`

Note: `react-force-graph-2d` may need a `@types` package or a declaration file. If type errors occur, create `frontend/src/types/react-force-graph-2d.d.ts`:

```typescript
declare module 'react-force-graph-2d' {
  import { Component } from 'react'
  export interface ForceGraphMethods<N = any, L = any> {
    d3Force: (name: string, force?: any) => any
    centerAt: (x?: number, y?: number, ms?: number) => void
    zoom: (zoom?: number, ms?: number) => void
  }
  const ForceGraph2D: React.ForwardRefExoticComponent<any & React.RefAttributes<ForceGraphMethods>>
  export default ForceGraph2D
  export type { ForceGraphMethods }
}
```

- [ ] **Step 3: Wire into MainView**

Update `frontend/src/components/layout/MainView.tsx`:

```tsx
import { useUIState } from '../../api/hooks'
import { SocialGraph } from '../graph/SocialGraph'

export function MainView() {
  const { view, selectedAgent, selectedConversation } = useUIState()

  return (
    <div style={{ height: '100%', overflow: 'hidden' }}>
      {view === 'graph' && <SocialGraph />}
      {view === 'agent' && (
        <div style={{ padding: 16, color: 'var(--text-secondary)' }}>Agent Detail: {selectedAgent} (coming next)</div>
      )}
      {view === 'conversation' && (
        <div style={{ padding: 16, color: 'var(--text-secondary)' }}>Conversation: {selectedConversation} (coming next)</div>
      )}
    </div>
  )
}
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/graph/ frontend/src/components/layout/MainView.tsx frontend/src/types/
git commit -m "feat: SocialGraph with force-directed layout, glow effects, and edge fading"
```

---

## Chunk 5: Agent Detail + Conversation Views

### Task 17: AgentDetail component

**Files:**
- Create: `frontend/src/components/agents/AgentDetail.tsx`

- [ ] **Step 1: Create AgentDetail**

```tsx
import { useState, useEffect } from 'react'
import { useSimulation, useUIState, useUIDispatch } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'

export function AgentDetail() {
  const { agents, events, stats, conversations } = useSimulation()
  const { selectedAgent } = useUIState()
  const dispatch = useUIDispatch()
  const [context, setContext] = useState<any>(null)
  const [contextLoading, setContextLoading] = useState(false)

  const agent = agents.find(a => a.handle === selectedAgent)
  const agentStats = stats.find(s => s.handle === selectedAgent)
  const color = selectedAgent ? getAgentColor(selectedAgent) : 'var(--text-primary)'

  // Agent's recent events
  const agentEvents = events
    .filter(e => e.entity === selectedAgent || (e.type === 'dm_sent' && e.data.to === selectedAgent))
    .slice(-50)

  const boardPosts = agentEvents.filter(e => e.type === 'board_post').slice(-10)
  const dms = agentEvents.filter(e => e.type === 'dm_sent').slice(-20)

  // Conversations involving this agent
  const agentConvos = Object.entries(conversations)
    .filter(([key]) => key.split('-').includes(selectedAgent ?? ''))

  async function loadContext() {
    if (!selectedAgent) return
    setContextLoading(true)
    try {
      const resp = await fetch(`/api/agent/${selectedAgent}/context`)
      const data = await resp.json()
      if (!data.error) setContext(data)
      else setContext(null)
    } catch { setContext(null) }
    setContextLoading(false)
  }

  // Reset context when agent changes
  useEffect(() => { setContext(null) }, [selectedAgent])

  if (!agent) {
    return <div style={{ padding: 16, color: 'var(--text-secondary)' }}>Agent not found</div>
  }

  return (
    <div style={{ height: '100%', overflowY: 'auto', padding: 20 }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
        <span style={{
          fontSize: 20, fontWeight: 700, color, fontFamily: 'var(--font-mono)',
        }}>
          {agent.handle}
        </span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 12 }}>{agent.personality}</span>
        <span style={{ marginLeft: 'auto', color: 'var(--text-secondary)', fontSize: 12 }}>
          energy: <span style={{ color: 'var(--text-primary)' }}>{agent.energy ?? '?'}</span>
        </span>
        <button
          onClick={() => dispatch({ type: 'OPEN_CONTROL_PANEL', prefill: { action: 'send_dm', to: agent.handle } as any })}
          style={{
            background: 'var(--bg-surface)', border: '1px solid var(--border)',
            borderRadius: 4, padding: '4px 10px', color: 'var(--accent)',
            cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
          }}
        >
          Send DM
        </button>
      </div>

      {/* Stats */}
      {agentStats && (
        <div style={{ display: 'flex', gap: 16, marginBottom: 16, fontSize: 12 }}>
          <span style={{ color: 'var(--text-secondary)' }}>posts: <span style={{ color: 'var(--text-primary)' }}>{agentStats.posts}</span></span>
          <span style={{ color: 'var(--text-secondary)' }}>dms sent: <span style={{ color: 'var(--text-primary)' }}>{agentStats.dms_sent}</span></span>
          <span style={{ color: 'var(--text-secondary)' }}>dms recv: <span style={{ color: 'var(--text-primary)' }}>{agentStats.dms_received}</span></span>
          <span style={{ color: 'var(--text-secondary)' }}>remembers: <span style={{ color: 'var(--text-primary)' }}>{agentStats.remembers}</span></span>
        </div>
      )}

      {/* Soul */}
      <Section title="soul">
        <pre style={{ color: '#67e8f9', fontStyle: 'italic', whiteSpace: 'pre-wrap', fontSize: 12 }}>
          {agent.soul || '(empty)'}
        </pre>
      </Section>

      {/* Memory */}
      <Section title="memory">
        <pre style={{ color: 'var(--text-primary)', whiteSpace: 'pre-wrap', fontSize: 12 }}>
          {agent.memory || '(empty)'}
        </pre>
      </Section>

      {/* Recent Board Posts */}
      <Section title={`recent posts (${boardPosts.length})`}>
        {boardPosts.length === 0 ? <Muted>(none)</Muted> : boardPosts.map(e => (
          <div key={e.idx} style={{ padding: '4px 0', borderBottom: '1px solid var(--border)', fontSize: 12 }}>
            {e.data.content}
          </div>
        ))}
      </Section>

      {/* Recent DMs */}
      <Section title={`recent DMs (${dms.length})`}>
        {dms.length === 0 ? <Muted>(none)</Muted> : dms.map(e => {
          const outgoing = e.entity === selectedAgent
          return (
            <div key={e.idx} style={{ padding: '4px 0', borderBottom: '1px solid var(--border)', fontSize: 12 }}>
              <span style={{ color: outgoing ? 'var(--energy-healthy)' : 'var(--accent-interactive)' }}>
                {outgoing ? `→ ${e.data.to}` : `← ${e.entity}`}
              </span>
              {': '}{e.data.content}
            </div>
          )
        })}
      </Section>

      {/* Conversations */}
      <Section title={`conversations (${agentConvos.length})`}>
        {agentConvos.map(([key, msgs]) => (
          <div
            key={key}
            onClick={() => dispatch({ type: 'SELECT_CONVERSATION', key })}
            style={{
              padding: '6px 0', cursor: 'pointer', borderBottom: '1px solid var(--border)',
              fontSize: 12, color: 'var(--accent-interactive)',
            }}
          >
            {key} ({msgs.length} messages)
          </div>
        ))}
      </Section>

      {/* Context */}
      <Section title="LLM context">
        {context ? (
          <div style={{ fontSize: 11, fontFamily: 'var(--font-mono)' }}>
            <div style={{ color: 'var(--energy-healthy)', marginBottom: 8, fontWeight: 600 }}>SYSTEM PROMPT</div>
            <pre style={{ whiteSpace: 'pre-wrap', color: 'var(--text-primary)', marginBottom: 16, maxHeight: 300, overflow: 'auto' }}>
              {context.system}
            </pre>
            <div style={{ color: 'var(--energy-healthy)', marginBottom: 8, fontWeight: 600 }}>
              MESSAGES ({context.messages?.length ?? 0})
            </div>
            {context.messages?.map((m: any, i: number) => (
              <div key={i} style={{
                background: m.role === 'user' ? 'rgba(129,140,248,0.08)' : m.role === 'assistant' ? 'rgba(167,139,250,0.08)' : 'rgba(250,204,21,0.08)',
                border: '1px solid var(--border)', borderRadius: 4, padding: 8, marginBottom: 4,
              }}>
                <div style={{ color: m.role === 'user' ? '#818cf8' : m.role === 'assistant' ? '#a78bfa' : '#facc15', fontWeight: 600, marginBottom: 4 }}>
                  {m.role}{m.name ? ` (${m.name})` : ''}
                </div>
                <pre style={{ whiteSpace: 'pre-wrap', color: 'var(--text-primary)', maxHeight: 200, overflow: 'auto' }}>
                  {m.content ?? ''}
                  {m.tool_calls?.map((tc: any) => `\n[tool_call] ${tc.function.name}(${tc.function.arguments})`).join('') ?? ''}
                </pre>
              </div>
            ))}
          </div>
        ) : (
          <button
            onClick={loadContext}
            disabled={contextLoading}
            style={{
              background: 'var(--bg-surface)', border: '1px solid var(--border)',
              borderRadius: 4, padding: '4px 12px', color: 'var(--accent)',
              cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 11,
            }}
          >
            {contextLoading ? 'Loading...' : 'Load Context'}
          </button>
        )}
      </Section>
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <div style={{ color: 'var(--energy-healthy)', fontSize: 11, fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.5, marginBottom: 6 }}>
        {title}
      </div>
      <div style={{
        background: 'var(--bg-surface)', border: '1px solid var(--border)',
        borderRadius: 4, padding: 10, maxHeight: 300, overflowY: 'auto',
      }}>
        {children}
      </div>
    </div>
  )
}

function Muted({ children }: { children: React.ReactNode }) {
  return <span style={{ color: 'var(--text-secondary)', fontStyle: 'italic' }}>{children}</span>
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/agents/AgentDetail.tsx
git commit -m "feat: AgentDetail with stats, soul, memory, DMs, posts, and context viewer"
```

### Task 18: ConversationView component

**Files:**
- Create: `frontend/src/components/feed/ConversationView.tsx`

- [ ] **Step 1: Create ConversationView**

```tsx
import { useSimulation, useUIState, useUIDispatch } from '../../api/hooks'
import { getAgentColor } from '../../api/colors'

export function ConversationView() {
  const { conversations } = useSimulation()
  const { selectedConversation } = useUIState()
  const dispatch = useUIDispatch()

  if (!selectedConversation) {
    return <div style={{ padding: 16, color: 'var(--text-secondary)' }}>No conversation selected</div>
  }

  const messages = conversations[selectedConversation] ?? []
  const [handleA, handleB] = selectedConversation.split('-')
  const colorA = getAgentColor(handleA)
  const colorB = getAgentColor(handleB)

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      {/* Header */}
      <div style={{
        padding: '12px 20px', borderBottom: '1px solid var(--border)',
        display: 'flex', alignItems: 'center', gap: 12,
      }}>
        <span
          onClick={() => dispatch({ type: 'SELECT_AGENT', handle: handleA })}
          style={{ color: colorA, fontFamily: 'var(--font-mono)', fontWeight: 600, cursor: 'pointer' }}
        >
          {handleA}
        </span>
        <span style={{ color: 'var(--text-secondary)' }}>↔</span>
        <span
          onClick={() => dispatch({ type: 'SELECT_AGENT', handle: handleB })}
          style={{ color: colorB, fontFamily: 'var(--font-mono)', fontWeight: 600, cursor: 'pointer' }}
        >
          {handleB}
        </span>
        <span style={{ color: 'var(--text-secondary)', fontSize: 11, marginLeft: 'auto' }}>
          {messages.length} messages
        </span>
      </div>

      {/* Messages */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '12px 20px' }}>
        {messages.map(msg => {
          const isA = msg.entity === handleA
          const color = isA ? colorA : colorB
          return (
            <div key={msg.idx} style={{
              display: 'flex', flexDirection: 'column',
              alignItems: isA ? 'flex-start' : 'flex-end',
              marginBottom: 8,
            }}>
              <span style={{ color, fontFamily: 'var(--font-mono)', fontSize: 10, marginBottom: 2 }}>
                {msg.entity}
              </span>
              <div style={{
                background: isA ? 'rgba(129,140,248,0.08)' : 'rgba(167,139,250,0.08)',
                border: '1px solid var(--border)', borderRadius: 6,
                padding: '6px 10px', maxWidth: '70%', fontSize: 12,
              }}>
                {msg.data.content}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
```

- [ ] **Step 2: Wire AgentDetail and ConversationView into MainView**

Update `frontend/src/components/layout/MainView.tsx`:

```tsx
import { useUIState } from '../../api/hooks'
import { SocialGraph } from '../graph/SocialGraph'
import { AgentDetail } from '../agents/AgentDetail'
import { ConversationView } from '../feed/ConversationView'

export function MainView() {
  const { view } = useUIState()

  return (
    <div style={{ height: '100%', overflow: 'hidden' }}>
      {view === 'graph' && <SocialGraph />}
      {view === 'agent' && <AgentDetail />}
      {view === 'conversation' && <ConversationView />}
    </div>
  )
}
```

- [ ] **Step 3: Verify compilation**

Run: `cd /Users/pat/Code/conwai/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add frontend/src/components/feed/ConversationView.tsx frontend/src/components/layout/MainView.tsx
git commit -m "feat: ConversationView chat-style DM thread and wire all views into MainView"
```

---

## Chunk 6: Control Panel + Contextual Actions

### Task 19: ControlPanel slide-out drawer

**Files:**
- Create: `frontend/src/components/controls/ControlPanel.tsx`

- [ ] **Step 1: Create ControlPanel**

```tsx
import { useState, useEffect } from 'react'
import { useSimulation, useUIState, useUIDispatch, useSendAction } from '../../api/hooks'
import type { HandlerAction } from '../../api/types'

type ActionType = HandlerAction['action']

export function ControlPanel() {
  const { agents } = useSimulation()
  const { controlPanelPrefill } = useUIState()
  const dispatch = useUIDispatch()
  const sendAction = useSendAction()

  const [activeAction, setActiveAction] = useState<ActionType>('post_board')
  const [content, setContent] = useState('')
  const [targetHandle, setTargetHandle] = useState('')
  const [energyValue, setEnergyValue] = useState(0)
  const [confirming, setConfirming] = useState(false)
  const [result, setResult] = useState<{ ok: boolean; error?: string } | null>(null)

  // Handle prefill from contextual actions
  useEffect(() => {
    if (controlPanelPrefill) {
      const p = controlPanelPrefill as any
      if (p.action) setActiveAction(p.action)
      if (p.to) setTargetHandle(p.to)
      if (p.handle) setTargetHandle(p.handle)
      if (p.content) setContent(p.content)
    }
  }, [controlPanelPrefill])

  function buildAction(): HandlerAction | null {
    switch (activeAction) {
      case 'post_board': return content ? { action: 'post_board', content } : null
      case 'send_dm': return content && targetHandle ? { action: 'send_dm', to: targetHandle, content } : null
      case 'set_energy': return targetHandle ? { action: 'set_energy', handle: targetHandle, value: energyValue } : null
      case 'drain_energy': return targetHandle ? { action: 'drain_energy', handle: targetHandle, amount: energyValue } : null
      case 'drop_secret': return content && targetHandle ? { action: 'drop_secret', handle: targetHandle, content } : null
      default: return null
    }
  }

  function describeAction(): string {
    switch (activeAction) {
      case 'post_board': return `Post to board: "${content.slice(0, 50)}"`
      case 'send_dm': return `DM ${targetHandle}: "${content.slice(0, 50)}"`
      case 'set_energy': return `Set ${targetHandle} energy to ${energyValue}`
      case 'drain_energy': return `Drain ${energyValue} energy from ${targetHandle}`
      case 'drop_secret': return `Drop secret to ${targetHandle}: "${content.slice(0, 50)}"`
      default: return ''
    }
  }

  async function execute() {
    const action = buildAction()
    if (!action) return
    const res = await sendAction(action)
    setResult(res)
    setConfirming(false)
    if (res.ok) {
      setContent('')
      setTargetHandle('')
      setEnergyValue(0)
      setTimeout(() => setResult(null), 2000)
    }
  }

  const currentAction = buildAction()
  const needsTarget = activeAction !== 'post_board'
  const needsContent = ['post_board', 'send_dm', 'drop_secret'].includes(activeAction)
  const needsEnergy = ['set_energy', 'drain_energy'].includes(activeAction)

  const actions: { value: ActionType; label: string }[] = [
    { value: 'post_board', label: 'Post to Board' },
    { value: 'send_dm', label: 'Send DM' },
    { value: 'set_energy', label: 'Set Energy' },
    { value: 'drain_energy', label: 'Drain Energy' },
    { value: 'drop_secret', label: 'Drop Secret' },
  ]

  const inputStyle: React.CSSProperties = {
    width: '100%', background: 'rgba(255,255,255,0.03)',
    border: '1px solid var(--border)', borderRadius: 4,
    padding: '6px 10px', color: 'var(--text-primary)',
    fontFamily: 'var(--font-mono)', fontSize: 12,
    outline: 'none',
  }

  return (
    <div style={{ padding: 16, display: 'flex', flexDirection: 'column', gap: 12, height: '100%' }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <span style={{ color: 'var(--accent)', fontWeight: 600, fontSize: 13, letterSpacing: 0.5 }}>HANDLER</span>
        <span
          onClick={() => dispatch({ type: 'CLOSE_CONTROL_PANEL' })}
          style={{ color: 'var(--text-secondary)', cursor: 'pointer', fontSize: 18 }}
        >
          ×
        </span>
      </div>

      {/* Action selector */}
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
        {actions.map(a => (
          <button
            key={a.value}
            onClick={() => { setActiveAction(a.value); setConfirming(false); setResult(null) }}
            style={{
              background: activeAction === a.value ? 'var(--bg-surface)' : 'transparent',
              border: `1px solid ${activeAction === a.value ? 'var(--accent)' : 'var(--border)'}`,
              borderRadius: 4, padding: '3px 8px',
              color: activeAction === a.value ? 'var(--accent)' : 'var(--text-secondary)',
              cursor: 'pointer', fontFamily: 'var(--font-mono)', fontSize: 10,
            }}
          >
            {a.label}
          </button>
        ))}
      </div>

      {/* Target selector */}
      {needsTarget && (
        <div>
          <label style={{ color: 'var(--text-secondary)', fontSize: 10, display: 'block', marginBottom: 4 }}>Agent</label>
          <select
            value={targetHandle}
            onChange={e => setTargetHandle(e.target.value)}
            style={{ ...inputStyle, cursor: 'pointer' }}
          >
            <option value="">Select agent...</option>
            {agents.map(a => (
              <option key={a.handle} value={a.handle}>{a.handle} ({a.personality})</option>
            ))}
          </select>
        </div>
      )}

      {/* Content input */}
      {needsContent && (
        <div>
          <label style={{ color: 'var(--text-secondary)', fontSize: 10, display: 'block', marginBottom: 4 }}>
            {activeAction === 'drop_secret' ? 'Secret' : 'Message'}
          </label>
          <textarea
            value={content}
            onChange={e => setContent(e.target.value)}
            placeholder={activeAction === 'drop_secret' ? 'Secret text...' : 'Message...'}
            rows={3}
            style={{ ...inputStyle, resize: 'vertical' }}
          />
        </div>
      )}

      {/* Energy input */}
      {needsEnergy && (
        <div>
          <label style={{ color: 'var(--text-secondary)', fontSize: 10, display: 'block', marginBottom: 4 }}>
            {activeAction === 'set_energy' ? 'New value' : 'Amount to drain'}
          </label>
          <input
            type="number"
            value={energyValue}
            onChange={e => setEnergyValue(parseInt(e.target.value) || 0)}
            style={inputStyle}
          />
        </div>
      )}

      {/* Confirm / Execute */}
      {confirming ? (
        <div style={{
          background: 'rgba(250,204,21,0.08)', border: '1px solid rgba(250,204,21,0.2)',
          borderRadius: 4, padding: 8, fontSize: 11,
        }}>
          <div style={{ color: '#facc15', marginBottom: 6 }}>{describeAction()}</div>
          <div style={{ display: 'flex', gap: 8 }}>
            <button onClick={execute} style={{
              background: 'var(--accent)', border: 'none', borderRadius: 4,
              padding: '4px 12px', color: '#0f1117', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
            }}>
              Confirm
            </button>
            <button onClick={() => setConfirming(false)} style={{
              background: 'transparent', border: '1px solid var(--border)', borderRadius: 4,
              padding: '4px 12px', color: 'var(--text-secondary)', cursor: 'pointer',
              fontFamily: 'var(--font-mono)', fontSize: 11,
            }}>
              Cancel
            </button>
          </div>
        </div>
      ) : (
        <button
          onClick={() => currentAction && setConfirming(true)}
          disabled={!currentAction}
          style={{
            background: currentAction ? 'var(--bg-surface)' : 'transparent',
            border: `1px solid ${currentAction ? 'var(--accent)' : 'var(--border)'}`,
            borderRadius: 4, padding: '6px 12px',
            color: currentAction ? 'var(--accent)' : 'var(--text-secondary)',
            cursor: currentAction ? 'pointer' : 'default',
            fontFamily: 'var(--font-mono)', fontSize: 11,
          }}
        >
          Preview Action
        </button>
      )}

      {/* Result */}
      {result && (
        <div style={{
          fontSize: 11, padding: 6, borderRadius: 4,
          color: result.ok ? 'var(--energy-healthy)' : 'var(--energy-critical)',
          background: result.ok ? 'rgba(52,211,153,0.08)' : 'rgba(239,68,68,0.08)',
        }}>
          {result.ok ? 'Sent!' : `Error: ${result.error}`}
        </div>
      )}
    </div>
  )
}
```

- [ ] **Step 2: Wire ControlPanel into Shell**

Update the Shell component to render ControlPanel in the right drawer column instead of the placeholder:

In `frontend/src/components/layout/Shell.tsx`, add import and replace the placeholder `<div>`:

```tsx
import { ControlPanel } from '../controls/ControlPanel'
```

Replace the control panel placeholder div:
```tsx
{controlPanelOpen && (
  <div style={{
    gridRow: '1',
    borderLeft: '1px solid var(--border)',
    overflow: 'auto',
  }}>
    <ControlPanel />
  </div>
)}
```

- [ ] **Step 3: Add floating toggle button**

In Shell, add a floating button to toggle the control panel. Place it just before the closing `</div>` of the root grid:

```tsx
{!controlPanelOpen && (
  <button
    onClick={() => dispatch({ type: 'TOGGLE_CONTROL_PANEL' })}
    style={{
      position: 'fixed', right: 16, top: 16, zIndex: 50,
      background: 'var(--bg-surface)', border: '1px solid var(--accent)',
      borderRadius: 6, padding: '6px 12px',
      color: 'var(--accent)', cursor: 'pointer',
      fontFamily: 'var(--font-mono)', fontSize: 11, fontWeight: 600,
    }}
  >
    HANDLER
  </button>
)}
```

Add the dispatch import in Shell if not present:
```tsx
import { useUIState, useUIDispatch } from '../../api/hooks'
```
And in the component: `const dispatch = useUIDispatch()`

- [ ] **Step 4: Verify compilation**

Run: `cd /Users/pat/Code/conwai/frontend && npx tsc --noEmit`
Expected: No errors

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/controls/ControlPanel.tsx frontend/src/components/layout/Shell.tsx
git commit -m "feat: ControlPanel drawer with all handler actions and inline confirmation"
```

### Task 20: ContextMenu for agents

**Files:**
- Create: `frontend/src/components/controls/ContextMenu.tsx`

- [ ] **Step 1: Create ContextMenu**

```tsx
import { useUIDispatch } from '../../api/hooks'

interface ContextMenuProps {
  handle: string
  x: number
  y: number
  onClose: () => void
}

export function ContextMenu({ handle, x, y, onClose }: ContextMenuProps) {
  const dispatch = useUIDispatch()

  const items = [
    { label: 'View Detail', action: () => dispatch({ type: 'SELECT_AGENT', handle }) },
    { label: 'Send DM', action: () => dispatch({ type: 'OPEN_CONTROL_PANEL', prefill: { action: 'send_dm', to: handle } as any }) },
    { label: 'Adjust Energy', action: () => dispatch({ type: 'OPEN_CONTROL_PANEL', prefill: { action: 'set_energy', handle } as any }) },
  ]

  return (
    <>
      <div
        onClick={onClose}
        style={{ position: 'fixed', inset: 0, zIndex: 99 }}
      />
      <div style={{
        position: 'fixed', left: x, top: y, zIndex: 100,
        background: '#1a1b26', border: '1px solid var(--border)',
        borderRadius: 6, padding: 4, minWidth: 140,
        boxShadow: '0 4px 16px rgba(0,0,0,0.5)',
      }}>
        {items.map(item => (
          <div
            key={item.label}
            onClick={() => { item.action(); onClose() }}
            style={{
              padding: '6px 10px', cursor: 'pointer', borderRadius: 4,
              fontSize: 11, fontFamily: 'var(--font-mono)',
              color: 'var(--text-primary)',
            }}
            onMouseEnter={e => (e.currentTarget.style.background = 'var(--bg-surface)')}
            onMouseLeave={e => (e.currentTarget.style.background = 'transparent')}
          >
            {item.label}
          </div>
        ))}
      </div>
    </>
  )
}
```

- [ ] **Step 2: Add context menu to AgentCard**

Update `AgentCard` to support right-click. Add state and handler:

Add to `AgentCard.tsx` imports: `import { useState } from 'react'` and `import { ContextMenu } from '../controls/ContextMenu'`

Add state inside the component:
```tsx
const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
```

Add `onContextMenu` to the root div:
```tsx
onContextMenu={e => { e.preventDefault(); setMenu({ x: e.clientX, y: e.clientY }) }}
```

Add before closing `</div>`:
```tsx
{menu && <ContextMenu handle={agent.handle} x={menu.x} y={menu.y} onClose={() => setMenu(null)} />}
```

- [ ] **Step 3: Commit**

```bash
git add frontend/src/components/controls/ContextMenu.tsx frontend/src/components/agents/AgentCard.tsx
git commit -m "feat: ContextMenu with right-click actions on agent cards"
```

---

## Chunk 7: Backend Static Serving + Production Build

### Task 21: Remove inline HTML, add static file serving

**Files:**
- Modify: `conwai/dashboard.py:171-428`

- [ ] **Step 1: Replace the index() endpoint**

Remove the entire inline HTML string from the `index()` function. Replace with static file serving:

Add import at top of `conwai/dashboard.py`:
```python
from fastapi.staticfiles import StaticFiles
```

Replace the `index()` function (and add static mount after app creation):

```python
FRONTEND_DIR = Path("frontend/dist")

# Mount static files if built frontend exists
if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def serve_frontend(full_path: str):
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return index_path.read_text()
        return HTMLResponse("Frontend not built. Run: cd frontend && npm run build", status_code=404)
```

Remove the old `index()` function entirely.

Note: The catch-all route must be registered last (after all `/api/` routes) to avoid conflicts. Move the mount and route registration to the end of the file.

- [ ] **Step 2: Verify API routes still work**

Run all dashboard tests to confirm API endpoints aren't shadowed by the catch-all route:

```bash
cd /Users/pat/Code/conwai && python -m pytest tests/test_dashboard.py -v
```

Expected: All tests pass (status, handler tests from Tasks 2-3 still work).

- [ ] **Step 3: Commit**

```bash
git add conwai/dashboard.py
git commit -m "feat: serve built React frontend from FastAPI, remove inline HTML"
```

### Task 22: Build frontend and verify end-to-end

- [ ] **Step 1: Build the frontend**

```bash
cd /Users/pat/Code/conwai/frontend && npm run build
```

Expected: Build succeeds, `frontend/dist/` directory created with `index.html` and `assets/`.

- [ ] **Step 2: Verify TypeScript compiles clean**

```bash
cd /Users/pat/Code/conwai/frontend && npx tsc --noEmit
```

Expected: No errors.

- [ ] **Step 3: Run all backend tests**

```bash
cd /Users/pat/Code/conwai && python -m pytest tests/ -v
```

Expected: All tests pass.

- [ ] **Step 4: Commit source files only (dist/ is gitignored)**

```bash
git add frontend/src/ frontend/package.json frontend/tsconfig.json frontend/vite.config.ts frontend/index.html
git commit -m "feat: complete dashboard frontend source"
```

---

## Chunk 8: Final Integration

### Task 23: Manual verification checklist

This is not automated — run through these manually with the simulation running:

- [ ] **Step 1: Start FastAPI server**

```bash
cd /Users/pat/Code/conwai && uvicorn conwai.dashboard:app --port 8000
```

- [ ] **Step 2: Start Vite dev server (for hot reload)**

```bash
cd /Users/pat/Code/conwai/frontend && npm run dev
```

- [ ] **Step 3: Verify each feature**

Open http://localhost:5173 and check:
- Sidebar shows agent cards with energy bars
- Clicking an agent shows their detail view
- Graph view renders with nodes and edges
- Event ticker scrolls at the bottom
- HANDLER button opens control panel
- Post to board works
- Send DM works
- Right-click agent card shows context menu
- Click graph edge opens conversation view
- Click CONWAI title returns to graph view
- Tick count, alive count visible in sidebar footer

- [ ] **Step 4: Final commit (only changed files)**

```bash
git add frontend/src/ conwai/dashboard.py main.py tests/
git commit -m "feat: dashboard redesign complete — React SPA with social graph, agent detail, and handler controls"
```
