import json
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from conwai.events import EventLog
from scenarios.bread_economy import queries

app = FastAPI()

FRONTEND_DIR = Path("frontend/dist")
AGENTS_DIR = Path("data/agents")
HANDLER_FILE = Path("handler_input.txt")
TICK_PATH = Path("data/tick")
CIPHER_PATH = Path("data/cipher.json")
WORLD_STATE_PATH = Path("data/world_state.json")

_events = EventLog()


def read_agents() -> list[dict]:
    agents = []
    if not AGENTS_DIR.exists():
        return agents
    for d in sorted(AGENTS_DIR.iterdir()):
        if not d.is_dir():
            continue
        identity_path = d / "identity.json"
        if not identity_path.exists():
            continue
        identity = json.loads(identity_path.read_text())
        if not identity.get("alive", True):
            continue

        agent = {
            "handle": identity["handle"],
            "soul": "",
            "born_tick": identity.get("born_tick", 0),
            "alive": True,
        }

        # Read agent_info component for role/personality
        info_path = d / "agent_info.json"
        if info_path.exists():
            info = json.loads(info_path.read_text())
            agent["role"] = info.get("role", "")
            agent["personality"] = info.get("personality", "")
        else:
            agent["role"] = identity.get("role", "")
            agent["personality"] = identity.get("personality", "")

        for comp_name, fields in [
            ("economy", ["coins"]),
            ("inventory", ["flour", "water", "bread"]),
            ("hunger", ["hunger", "thirst"]),
            ("memory", ["memory", "soul"]),
        ]:
            comp_path = d / f"{comp_name}.json"
            if comp_path.exists():
                data = json.loads(comp_path.read_text())
                for f in fields:
                    if f == "coins":
                        agent["energy"] = int(data.get(f, 0))
                    else:
                        agent[f] = data.get(f, 0)

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
                identity_path = d / "identity.json"
                if identity_path.exists():
                    identity = json.loads(identity_path.read_text())
                    if identity.get("alive", True):
                        alive += 1
    return {"tick": tick, "alive": alive, "total_events": _events.count()}


@app.get("/api/cipher")
def api_cipher():
    if not CIPHER_PATH.exists():
        return None
    return json.loads(CIPHER_PATH.read_text())


@app.get("/api/election")
def api_election():
    if not WORLD_STATE_PATH.exists():
        return None
    state = json.loads(WORLD_STATE_PATH.read_text())
    if not state.get("election_active"):
        return None
    tick = int(TICK_PATH.read_text().strip()) if TICK_PATH.exists() else 0
    votes = state.get("votes", {})
    # Tally
    tally: dict[str, list[str]] = {}
    for voter, candidate in votes.items():
        tally.setdefault(candidate, []).append(voter)
    return {
        "active": True,
        "started_tick": state.get("election_started_tick", 0),
        "ticks_left": max(0, state.get("election_started_tick", 0) + 15 - tick),
        "total_votes": len(votes),
        "tally": {c: {"count": len(v), "voters": v} for c, v in sorted(tally.items(), key=lambda x: -len(x[1]))},
    }


@app.get("/api/board")
def api_board():
    return queries.board_posts(_events, 30)


@app.get("/api/conversations")
def api_conversations(since: float = Query(0)):
    return queries.recent_conversations(_events, since if since > 0 else None)


@app.get("/api/stats")
def api_stats():
    return queries.agent_stats(_events)


@app.get("/api/economy")
def api_economy():
    counts = queries.economy_counts(_events)
    trades = queries.trade_volume(_events)
    volume: dict[str, int] = {}
    for e in trades:
        d = e["data"]
        if e["type"] == "give":
            resource = d.get("resource", "")
            amount = d.get("amount", 0)
            if resource and amount:
                volume[resource] = volume.get(resource, 0) + amount
        elif e["type"] == "trade":
            for key in ("received_type", "gave_type"):
                resource = d.get(key, "")
                amount = d.get(key.replace("_type", "_amount"), 0)
                if resource and amount:
                    volume[resource] = volume.get(resource, 0) + amount
    return {"counts": counts, "trade_volume": volume}


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


@app.get("/api/agent/{handle}/memory")
def api_agent_memory(handle: str):
    ctx_path = AGENTS_DIR / handle / "context.json"
    if not ctx_path.exists():
        return {"memory": ""}
    context = json.loads(ctx_path.read_text())
    diary = []
    for m in context.get("messages", []):
        if m.get("_tick_summary"):
            diary.append(m["content"])
    return {"memory": "\n".join(diary) if diary else ""}


@app.get("/api/agent/{handle}")
def api_agent_detail(handle: str):
    agents = read_agents()
    agent = next((a for a in agents if a["handle"] == handle), None)
    if not agent:
        return {"error": "not found"}
    agent["board_posts"] = _events.agent_events(handle, "board_post", 20)
    agent["dms"] = queries.agent_dms(_events, handle, 30)
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
