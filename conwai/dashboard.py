import json
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from conwai.events import EventLog

app = FastAPI()

FRONTEND_DIR = Path("frontend/dist")
AGENTS_DIR = Path("data/agents")
HANDLER_FILE = Path("handler_input.txt")
TICK_PATH = Path("data/tick")

_events = EventLog()


def read_agents() -> list[dict]:
    agents = []
    if not AGENTS_DIR.exists():
        return agents
    for d in sorted(AGENTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        handle = d.name
        agent = {"handle": handle}
        for f in ["personality.md", "soul.md", "memory.md"]:
            p = d / f
            agent[f.replace(".md", "")] = p.read_text() if p.exists() else ""
        ep = d / "energy"
        agent["energy"] = int(float(ep.read_text().strip())) if ep.exists() else None
        rp = d / "role"
        agent["role"] = rp.read_text().strip() if rp.exists() else None
        for resource in ["flour", "water", "bread"]:
            rp = d / resource
            agent[resource] = int(rp.read_text().strip()) if rp.exists() else 0
        hp = d / "hunger"
        agent["hunger"] = int(hp.read_text().strip()) if hp.exists() else None
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
    return _events.read_since(since)


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
    return {"tick": tick, "alive": alive, "total_events": _events.count()}


@app.get("/api/board")
def api_board():
    return _events.board_posts(30)


@app.get("/api/conversations")
def api_conversations(since: float = Query(0)):
    return _events.recent_conversations(since if since > 0 else None)


@app.get("/api/stats")
def api_stats():
    return _events.agent_stats()


@app.post("/api/handler")
async def api_handler(request: Request):
    body = await request.json()

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
    agent["board_posts"] = _events.agent_events(handle, "board_post", 20)
    agent["dms"] = _events.agent_dms(handle, 30)
    agent["soul_updates"] = _events.agent_events(handle, "soul_updated", 5)
    return agent


if FRONTEND_DIR.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIR / "assets"), name="static-assets")

    @app.get("/{full_path:path}", response_class=HTMLResponse)
    def serve_frontend(full_path: str):
        index_path = FRONTEND_DIR / "index.html"
        if index_path.exists():
            return index_path.read_text()
        return HTMLResponse("Frontend not built. Run: cd frontend && npm run build", status_code=404)
