from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from conwai.events import EventLog
from conwai.storage import SQLiteStorage
from scenarios.bread_economy import queries

app = FastAPI()

FRONTEND_DIR = Path("frontend/dist")

_events = EventLog()
_storage = SQLiteStorage()


def read_agents() -> list[dict]:
    agents = []
    for entity in _storage.list_entities():
        identity = _storage.load_component(entity, "_identity")
        if identity is None:
            continue  # Not an agent (e.g. WORLD)
        if not identity.get("alive", True):
            continue

        agent = {
            "handle": identity["handle"],
            "soul": "",
            "born_tick": identity.get("born_tick", 0),
            "alive": True,
        }

        # Read agent_info component for role/personality
        info = _storage.load_component(entity, "agent_info")
        if info:
            agent["role"] = info.get("role", "")
            agent["personality"] = info.get("personality", "")
        else:
            agent["role"] = ""
            agent["personality"] = ""

        for comp_name, fields in [
            ("economy", ["coins"]),
            ("inventory", ["flour", "water", "bread"]),
            ("hunger", ["hunger", "thirst"]),
            ("memory", ["memory", "soul"]),
        ]:
            data = _storage.load_component(entity, comp_name)
            if data:
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
    tick_data = _storage.load_component("WORLD", "tick")
    tick = tick_data["value"] if tick_data else 0
    alive = sum(1 for a in read_agents() if a.get("alive", True))
    return {"tick": tick, "alive": alive, "total_events": _events.count()}


@app.get("/api/cipher")
def api_cipher():
    state = _storage.load_component("WORLD", "world_events")
    if not state:
        return None
    # Extract cipher status fields
    if not state.get("plaintext"):
        return None
    return {
        "ciphertext": state.get("ciphertext"),
        "started_tick": state.get("cipher_started_tick", 0),
        "expires_tick": state.get("cipher_started_tick", 0) + 80,
        "clue_holders": list(state.get("clue_holders", {}).keys()),
        "clues": state.get("clue_holders", {}),
        "attempts": state.get("attempts", []),
        "reward": state.get("reward", 300),
        "penalty": state.get("penalty", 10),
    }


@app.get("/api/election")
def api_election():
    state = _storage.load_component("WORLD", "world_events")
    if not state:
        return None
    if not state.get("election_active"):
        return None
    tick_data = _storage.load_component("WORLD", "tick")
    tick = tick_data["value"] if tick_data else 0
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
        valid_actions = {"post_board", "send_dm", "set_energy", "drain_energy", "drop_secret"}
        if action not in valid_actions:
            return JSONResponse({"ok": False, "error": f"unknown action: {action}"}, status_code=400)
        try:
            _storage.push_command(body)
        except KeyError as e:
            return JSONResponse({"ok": False, "error": f"missing field: {e}"}, status_code=400)
        return {"ok": True}

    msg = body.get("message", "").strip()
    if not msg:
        return JSONResponse({"ok": False, "error": "empty message"}, status_code=400)
    _storage.push_command({"action": "post_board", "content": msg})
    return {"ok": True, "message": msg}


@app.get("/api/handler/inbox")
def api_handler_inbox():
    """All DM threads involving HANDLER (both directions)."""
    rows = _events._conn().execute(
        "SELECT id, t, entity, type, data FROM events "
        "WHERE type = 'dm_sent' AND "
        "(json_extract(data, '$.to') = 'HANDLER' OR entity = 'HANDLER') "
        "ORDER BY id"
    ).fetchall()
    threads: dict[str, list[dict]] = {}
    for r in rows:
        event = _events._row_to_dict(r)
        # Key by the other party (not HANDLER)
        if event["entity"] == "HANDLER":
            other = event["data"].get("to", "")
        else:
            other = event["entity"]
        if not other or other == "HANDLER":
            continue
        threads.setdefault(other, []).append({
            "t": event["t"],
            "content": event["data"].get("content", ""),
            "from": event["entity"],
        })
    return threads


@app.get("/api/handler/inbox/{handle}")
def api_handler_thread(handle: str):
    """DM thread between a specific agent and HANDLER (both directions)."""
    rows = _events._conn().execute(
        "SELECT id, t, entity, type, data FROM events "
        "WHERE type = 'dm_sent' AND "
        "(entity = ? AND json_extract(data, '$.to') = 'HANDLER' OR "
        " entity = 'HANDLER' AND json_extract(data, '$.to') = ?) "
        "ORDER BY id",
        (handle, handle),
    ).fetchall()
    messages = []
    for r in rows:
        event = _events._row_to_dict(r)
        messages.append({
            "from": event["entity"],
            "to": event["data"].get("to", ""),
            "content": event["data"].get("content", ""),
            "t": event["t"],
        })
    return messages


@app.get("/api/agent/{handle}/context")
def api_agent_context(handle: str):
    data = _storage.load_component(handle, "brain")
    if not data:
        return {"error": "no context available"}
    return data


@app.get("/api/agent/{handle}/memory")
def api_agent_memory(handle: str):
    brain = _storage.load_component(handle, "brain")
    if not brain:
        return {"memory": ""}
    parts = []
    for m in brain.get("messages", []):
        if m.get("_tick_summary"):
            parts.append(m["content"])
    for entry in brain.get("diary", []):
        parts.append(entry.get("content", ""))
    return {"memory": "\n".join(parts) if parts else ""}


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
