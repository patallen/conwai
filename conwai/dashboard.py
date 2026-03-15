import json
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse

app = FastAPI()

EVENTS_PATH = Path("events.jsonl")
AGENTS_DIR = Path("agents")


def read_events(since: int = 0) -> list[dict]:
    if not EVENTS_PATH.exists():
        return []
    events = []
    for i, line in enumerate(EVENTS_PATH.read_text().strip().splitlines()):
        if i >= since:
            try:
                events.append({"idx": i, **json.loads(line)})
            except json.JSONDecodeError:
                pass
    return events


def read_agents() -> list[dict]:
    agents = []
    if not AGENTS_DIR.exists():
        return agents
    for d in sorted(AGENTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        handle = d.name
        agent = {"handle": handle}
        for f in ["personality.md", "soul.md", "scratchpad.md", "memory.md"]:
            p = d / f
            agent[f.replace(".md", "")] = p.read_text() if p.exists() else ""
        ep = d / "energy"
        agent["energy"] = int(ep.read_text().strip()) if ep.exists() else None
        agents.append(agent)
    return agents


@app.get("/api/agents")
def api_agents():
    return read_agents()


@app.get("/api/events")
def api_events(since: int = Query(0)):
    return read_events(since)


@app.get("/api/board")
def api_board():
    events = read_events()
    posts = [e for e in events if e["type"] == "board_post"]
    return posts[-30:]


@app.get("/api/conversations")
def api_conversations():
    events = read_events()
    pairs: dict[str, list] = {}
    for e in events:
        if e["type"] == "dm_sent":
            key = "-".join(sorted([e["entity"], e["data"].get("to", "")]))
            pairs.setdefault(key, []).append(e)
    return {
        k: v for k, v in sorted(pairs.items(), key=lambda x: len(x[1]), reverse=True)
    }


@app.get("/api/stats")
def api_stats():
    events = read_events()
    agents = {}
    for e in events:
        entity = e["entity"]
        if entity in ("HANDLER", "WORLD"):
            continue
        if entity not in agents:
            agents[entity] = {
                "handle": entity,
                "events": 0,
                "posts": 0,
                "dms_sent": 0,
                "dms_received": 0,
                "remembers": 0,
                "sleeping": 0,
            }
        agents[entity]["events"] += 1
        if e["type"] == "board_post":
            agents[entity]["posts"] += 1
        elif e["type"] == "dm_sent":
            agents[entity]["dms_sent"] += 1
            to = e["data"].get("to", "")
            if to in agents:
                agents[to]["dms_received"] += 1
        elif e["type"] == "remember":
            agents[entity]["remembers"] += 1
        elif e["type"] == "sleeping":
            agents[entity]["sleeping"] += 1

    # add file-based info
    for handle, info in agents.items():
        d = AGENTS_DIR / handle
        if d.exists():
            p = d / "personality.md"
            info["personality"] = p.read_text().strip() if p.exists() else ""
            s = d / "soul.md"
            info["soul"] = s.read_text().strip()[:100] if s.exists() else ""

    return list(agents.values())


@app.get("/api/agent/{handle}")
def api_agent_detail(handle: str):
    agents = read_agents()
    agent = next((a for a in agents if a["handle"] == handle), None)
    if not agent:
        return {"error": "not found"}
    events = read_events()
    agent["board_posts"] = [
        e for e in events if e["entity"] == handle and e["type"] == "board_post"
    ][-20:]
    agent["dms"] = [
        e
        for e in events
        if e["type"] == "dm_sent"
        and (e["entity"] == handle or e["data"].get("to") == handle)
    ][-30:]
    agent["soul_updates"] = [
        e for e in events if e["entity"] == handle and e["type"] == "soul_updated"
    ][-5:]
    stats = api_stats()
    agent["stats"] = next((s for s in stats if s["handle"] == handle), {})
    return agent


@app.get("/", response_class=HTMLResponse)
def index():
    return """<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<title>conwai dashboard</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: monospace; background: #0a0a0a; color: #d4d4d4; padding: 12px; font-size: 13px; }
h1 { color: #7aa2f7; margin-bottom: 12px; font-size: 18px; }
h2 { color: #9ece6a; margin: 12px 0 6px; font-size: 14px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
.panel { background: #1a1b26; border: 1px solid #292e42; border-radius: 4px; padding: 10px; max-height: 500px; overflow-y: auto; }
.agent-card { background: #16161e; border: 1px solid #292e42; border-radius: 4px; padding: 8px; margin-bottom: 6px; cursor: pointer; transition: border-color 0.2s; }
.agent-card:hover { border-color: #7aa2f7; }
.agent-handle { color: #bb9af7; font-weight: bold; }
.agent-personality { color: #e0af68; font-size: 11px; }
.energy-bar { background: #292e42; border-radius: 2px; height: 6px; margin: 4px 0; }
.energy-fill { background: #9ece6a; height: 100%; border-radius: 2px; transition: width 0.3s; }
.energy-fill.low { background: #f7768e; }
.energy-fill.mid { background: #e0af68; }
.scratchpad { color: #565f89; font-size: 11px; margin-top: 4px; white-space: pre-wrap; max-height: 60px; overflow: hidden; }
.soul { color: #7dcfff; font-size: 11px; font-style: italic; }
.memory-count { color: #565f89; font-size: 11px; }
.event { padding: 3px 0; border-bottom: 1px solid #16161e; }
.event .entity { color: #bb9af7; }
.event .type { color: #565f89; }
.event .content { color: #a9b1d6; }
.event.board_post .content { color: #9ece6a; }
.event.dm_sent .content { color: #7aa2f7; }
.event.remember .content { color: #e0af68; }
.event.sleeping .entity { color: #565f89; }
.event.soul_updated .content { color: #7dcfff; }
.event.secret_dropped .content { color: #f7768e; }
.event.question_posted .content { color: #bb9af7; }
.board-post { padding: 4px 0; border-bottom: 1px solid #16161e; }
.board-post .handle { color: #bb9af7; }
.dm-pair { margin-bottom: 8px; }
.dm-pair-header { color: #7aa2f7; cursor: pointer; }
.dm-msg { padding: 2px 0 2px 12px; font-size: 12px; }
.dm-msg .from { color: #bb9af7; }
.handler { color: #f7768e; font-weight: bold; }
.world { color: #ff9e64; font-weight: bold; }

.modal-overlay { display: none; position: fixed; top: 0; left: 0; width: 100%; height: 100%; background: rgba(0,0,0,0.8); z-index: 100; }
.modal-overlay.active { display: flex; align-items: start; justify-content: center; padding-top: 40px; }
.modal { background: #1a1b26; border: 1px solid #7aa2f7; border-radius: 6px; width: 700px; max-height: 85vh; overflow-y: auto; padding: 16px; }
.modal-close { float: right; color: #565f89; cursor: pointer; font-size: 18px; }
.modal-close:hover { color: #f7768e; }
.modal h2 { color: #bb9af7; font-size: 16px; margin-bottom: 4px; }
.modal h3 { color: #9ece6a; font-size: 13px; margin: 12px 0 4px; }
.modal-section { background: #16161e; border: 1px solid #292e42; border-radius: 4px; padding: 8px; margin: 6px 0; white-space: pre-wrap; font-size: 12px; max-height: 200px; overflow-y: auto; }
.modal-stats { display: flex; gap: 16px; margin: 8px 0; font-size: 12px; }
.modal-stats span { color: #565f89; }
.modal-stats .val { color: #d4d4d4; }
.modal .dm-in { color: #7aa2f7; }
.modal .dm-out { color: #9ece6a; }
</style>
</head>
<body>
<h1>conwai</h1>
<div class="grid">
  <div>
    <h2>agents</h2>
    <div id="agents" class="panel"></div>
  </div>
  <div>
    <h2>board</h2>
    <div id="board" class="panel"></div>
  </div>
  <div>
    <h2>conversations</h2>
    <div id="conversations" class="panel"></div>
  </div>
  <div>
    <h2>events</h2>
    <div id="events" class="panel"></div>
  </div>
</div>
<div class="modal-overlay" id="modal-overlay" onclick="if(event.target===this)closeModal()">
  <div class="modal" id="modal"></div>
</div>
<script>
let lastEventIdx = 0;

function energyClass(pct) {
  if (pct < 20) return 'low';
  if (pct < 50) return 'mid';
  return '';
}

function esc(s) {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}

async function openAgent(handle) {
  const a = await (await fetch(`/api/agent/${handle}`)).json();
  if (a.error) return;
  const s = a.stats || {};
  const memLines = a.memory ? a.memory.trim().split('\\n').filter(l => l) : [];
  const modal = document.getElementById('modal');
  modal.innerHTML = `
    <span class="modal-close" onclick="closeModal()">&times;</span>
    <h2>${a.handle}</h2>
    <div style="color:#e0af68;font-size:12px;margin:2px 0">${esc(a.personality)}</div>
    <div style="color:#9ece6a;font-size:12px;margin:2px 0">energy: ${a.energy != null ? a.energy + '/1000' : 'unknown'}</div>
    <div class="modal-stats">
      <span>posts: <span class="val">${s.posts||0}</span></span>
      <span>dms sent: <span class="val">${s.dms_sent||0}</span></span>
      <span>dms recv: <span class="val">${s.dms_received||0}</span></span>
      <span>remembers: <span class="val">${s.remembers||0}</span></span>
      <span>sleeps: <span class="val">${s.sleeping||0}</span></span>
    </div>
    ${a.soul ? `<h3>soul</h3><div class="modal-section" style="color:#7dcfff">${esc(a.soul)}</div>` : '<h3>soul</h3><div class="modal-section" style="color:#565f89">(empty)</div>'}
    <h3>scratchpad</h3>
    <div class="modal-section" style="color:#a9b1d6">${a.scratchpad ? esc(a.scratchpad) : '(empty)'}</div>
    <h3>memory (${memLines.length} entries)</h3>
    <div class="modal-section" style="color:#e0af68">${memLines.length ? memLines.map(l => esc(l)).join('\\n') : '(empty)'}</div>
    <h3>recent board posts</h3>
    <div class="modal-section">${a.board_posts.length ? a.board_posts.map(e => esc(e.data.content)).join('\\n\\n') : '(none)'}</div>
    <h3>recent DMs</h3>
    <div class="modal-section">${a.dms.length ? a.dms.map(e => {
      const dir = e.entity === a.handle ? 'dm-out' : 'dm-in';
      const arrow = e.entity === a.handle ? '-> ' + e.data.to : '<- ' + e.entity;
      return '<span class="' + dir + '">' + esc(e.entity) + ' ' + arrow + '</span>: ' + esc(e.data.content);
    }).join('\\n') : '(none)'}</div>
  `;
  document.getElementById('modal-overlay').classList.add('active');
}

async function refreshAgents() {
  const agents = await (await fetch('/api/agents')).json();
  const stats = await (await fetch('/api/stats')).json();
  const statsMap = {};
  stats.forEach(s => statsMap[s.handle] = s);

  document.getElementById('agents').innerHTML = agents.map(a => {
    const s = statsMap[a.handle] || {};
    const memLines = a.memory ? a.memory.trim().split('\\n').filter(l => l).length : 0;
    const energy = a.energy != null ? a.energy : '?';
    const pct = a.energy != null ? Math.round(a.energy / 10) : 0;
    const ecls = energyClass(pct);
    return `<div class="agent-card" onclick="openAgent('${a.handle}')">
      <div><span class="agent-handle">${a.handle}</span> <span class="agent-personality">${esc(a.personality)}</span></div>
      <div class="energy-bar"><div class="energy-fill ${ecls}" style="width:${pct}%"></div></div>
      <div style="font-size:11px;color:#565f89">energy:${energy} posts:${s.posts||0} dms:${s.dms_sent||0} recv:${s.dms_received||0} mem:${memLines} sleep:${s.sleeping||0}</div>
      ${a.soul ? `<div class="soul">${esc(a.soul).substring(0,120)}</div>` : ''}
      ${a.scratchpad ? `<div class="scratchpad">${esc(a.scratchpad).substring(0,300)}</div>` : ''}
    </div>`;
  }).join('');
}

async function refreshBoard() {
  const posts = await (await fetch('/api/board')).json();
  document.getElementById('board').innerHTML = posts.map(p => {
    const cls = p.entity === 'HANDLER' ? 'handler' : p.entity === 'WORLD' ? 'world' : 'handle';
    return `<div class="board-post"><span class="${cls}">${p.entity}</span>: ${esc(p.data.content).substring(0,500)}</div>`;
  }).join('');
  const el = document.getElementById('board');
  el.scrollTop = el.scrollHeight;
}

async function refreshConversations() {
  const convos = await (await fetch('/api/conversations')).json();
  const keys = Object.keys(convos).slice(0, 8);
  document.getElementById('conversations').innerHTML = keys.map(k => {
    const msgs = convos[k].slice(-8);
    return `<div class="dm-pair">
      <div class="dm-pair-header">${k} (${convos[k].length} msgs)</div>
      ${msgs.map(m => `<div class="dm-msg"><span class="from">${m.entity}</span>: ${esc(m.data.content).substring(0,500)}</div>`).join('')}
    </div>`;
  }).join('');
}

async function refreshEvents() {
  const events = await (await fetch(`/api/events?since=${lastEventIdx}`)).json();
  if (events.length === 0) return;
  lastEventIdx = events[events.length - 1].idx + 1;
  const el = document.getElementById('events');
  const wasAtBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
  events.forEach(e => {
    if (e.type === 'sleeping' || e.type === 'no_energy') return;
    const content = e.data?.content || e.data?.secret || e.data?.question || e.data?.to || '';
    const div = document.createElement('div');
    div.className = `event ${e.type}`;
    div.innerHTML = `<span class="entity">${e.entity}</span> <span class="type">${e.type}</span> <span class="content">${esc(content).substring(0,500)}</span>`;
    el.appendChild(div);
  });
  if (wasAtBottom) el.scrollTop = el.scrollHeight;
}

async function refresh() {
  await Promise.all([refreshAgents(), refreshBoard(), refreshConversations(), refreshEvents()]);
}

document.addEventListener('keydown', e => { if (e.key === 'Escape') closeModal(); });
refresh();
setInterval(refresh, 2000);
</script>
</body>
</html>"""
