"""Scenario-specific query helpers that run against the generic EventLog."""

from __future__ import annotations

from time import time

from conwai.events import EventLog


def board_posts(events: EventLog, limit: int = 30) -> list[dict]:
    rows = events._conn.execute(
        "SELECT id, t, entity, type, data FROM events WHERE type = 'board_post' ORDER BY id DESC LIMIT ?",
        (limit,),
    ).fetchall()
    return [events._row_to_dict(r) for r in reversed(rows)]


def recent_conversations(events: EventLog, since_t: float | None = None) -> dict[str, list[dict]]:
    if since_t is None:
        since_t = time() - 3600
    rows = events._conn.execute(
        "SELECT id, t, entity, type, data FROM events WHERE type = 'dm_sent' AND t > ? ORDER BY id",
        (since_t,),
    ).fetchall()
    pairs: dict[str, list[dict]] = {}
    for r in rows:
        event = events._row_to_dict(r)
        key = "-".join(sorted([r[2], event["data"].get("to", "")]))
        pairs.setdefault(key, []).append(event)
    return dict(sorted(pairs.items(), key=lambda x: len(x[1]), reverse=True))


def agent_stats(events: EventLog) -> list[dict]:
    """Compute per-agent stats by scanning events."""
    rows = events._conn.execute(
        "SELECT entity, type, COUNT(*) FROM events "
        "WHERE entity NOT IN ('HANDLER', 'WORLD') "
        "GROUP BY entity, type"
    ).fetchall()
    stats: dict[str, dict] = {}
    for entity, etype, cnt in rows:
        if entity not in stats:
            stats[entity] = {"handle": entity, "events": 0, "posts": 0, "dms_sent": 0, "dms_received": 0}
        stats[entity]["events"] += cnt
        if etype == "board_post":
            stats[entity]["posts"] += cnt
        elif etype == "dm_sent":
            stats[entity]["dms_sent"] += cnt
    # Count DMs received
    dm_rows = events._conn.execute(
        "SELECT json_extract(data, '$.to'), COUNT(*) FROM events WHERE type = 'dm_sent' GROUP BY json_extract(data, '$.to')"
    ).fetchall()
    for to_handle, cnt in dm_rows:
        if to_handle and to_handle in stats:
            stats[to_handle]["dms_received"] += cnt
    return list(stats.values())


def economy_counts(events: EventLog) -> dict:
    rows = events._conn.execute(
        "SELECT type, COUNT(*) FROM events WHERE type IN ('bake', 'give', 'payment', 'forage') GROUP BY type"
    ).fetchall()
    counts = {r[0]: r[1] for r in rows}
    bread_baked = events._conn.execute(
        "SELECT COALESCE(SUM(json_extract(data, '$.bread')), 0) FROM events WHERE type = 'bake'"
    ).fetchone()[0]
    counts["bread_baked"] = bread_baked
    return counts


def trade_volume(events: EventLog) -> list[dict]:
    rows = events._conn.execute(
        "SELECT id, t, entity, type, data FROM events WHERE type = 'give' ORDER BY id"
    ).fetchall()
    return [events._row_to_dict(r) for r in rows]


def agent_dms(events: EventLog, handle: str, limit: int = 30) -> list[dict]:
    rows = events._conn.execute(
        "SELECT id, t, entity, type, data FROM events WHERE type = 'dm_sent' AND (entity = ? OR json_extract(data, '$.to') = ?) ORDER BY id DESC LIMIT ?",
        (handle, handle, limit),
    ).fetchall()
    return [events._row_to_dict(r) for r in reversed(rows)]
