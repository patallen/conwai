import json
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

app = FastAPI()

FRONTEND_DIR = Path("frontend/dist")
EVENTS_PATH = Path("data/events.jsonl")
AGENTS_DIR = Path("data/agents")
HANDLER_FILE = Path("handler_input.txt")
TICK_PATH = Path("data/tick")


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
        for f in [
            "personality.md",
            "soul.md",
            "memory.md",
            "memory.md",
        ]:
            p = d / f
            agent[f.replace(".md", "")] = p.read_text() if p.exists() else ""
        ep = d / "energy"
        agent["energy"] = int(float(ep.read_text().strip())) if ep.exists() else None
        fp = d / "food"
        agent["food"] = int(fp.read_text().strip()) if fp.exists() else None
        hp = d / "hunger"
        agent["hunger"] = int(hp.read_text().strip()) if hp.exists() else None
        fsp = d / "forage_skill"
        agent["forage_skill"] = int(fsp.read_text().strip()) if fsp.exists() else None
        alive_path = d / "alive"
        agent["alive"] = (
            alive_path.read_text().strip() == "true" if alive_path.exists() else True
        )
        if not agent["alive"]:
            continue
        agents.append(agent)
    return agents


@app.get("/api/agents")
def api_agents():
    return read_agents()


@app.get("/api/events")
def api_events(since: int = Query(0)):
    return read_events(since)


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

    for handle, info in agents.items():
        d = AGENTS_DIR / handle
        if d.exists():
            p = d / "personality.md"
            info["personality"] = p.read_text().strip() if p.exists() else ""
            s = d / "soul.md"
            info["soul"] = s.read_text().strip()[:100] if s.exists() else ""

    return list(agents.values())


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


@app.get("/api/agent/{handle}/context")
def api_agent_context(handle: str):
    ctx_path = AGENTS_DIR / handle / "context.json"
    if not ctx_path.exists():
        return {"error": "no context available"}
    return json.loads(ctx_path.read_text())


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


if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def serve_frontend(full_path: str):
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return index_path.read_text()
        return HTMLResponse("Frontend not built. Run: cd frontend && npm run build", status_code=404)
