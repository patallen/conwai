import json
import sqlite3
from pathlib import Path
from time import time


class EventLog:
    def __init__(self, path: Path = Path("data/events.db")):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                t REAL NOT NULL,
                entity TEXT NOT NULL,
                type TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}'
            )
        """)
        self._conn.execute("""
            CREATE TABLE IF NOT EXISTS stats (
                handle TEXT PRIMARY KEY,
                events INTEGER NOT NULL DEFAULT 0,
                posts INTEGER NOT NULL DEFAULT 0,
                dms_sent INTEGER NOT NULL DEFAULT 0,
                dms_received INTEGER NOT NULL DEFAULT 0
            )
        """)
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_entity ON events(entity)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON events(type)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_entity_type ON events(entity, type)")
        self._conn.execute("CREATE INDEX IF NOT EXISTS idx_t ON events(t)")
        self._conn.commit()

    def log(self, entity_id: str, event_type: str, data: dict | None = None):
        self._conn.execute(
            "INSERT INTO events (t, entity, type, data) VALUES (?, ?, ?, ?)",
            (time(), entity_id, event_type, json.dumps(data or {})),
        )
        # Update pre-computed stats
        if entity_id not in ("HANDLER", "WORLD"):
            self._conn.execute(
                "INSERT INTO stats (handle, events) VALUES (?, 1) "
                "ON CONFLICT(handle) DO UPDATE SET events = events + 1",
                (entity_id,),
            )
            if event_type == "board_post":
                self._conn.execute(
                    "UPDATE stats SET posts = posts + 1 WHERE handle = ?",
                    (entity_id,),
                )
            elif event_type == "dm_sent":
                self._conn.execute(
                    "UPDATE stats SET dms_sent = dms_sent + 1 WHERE handle = ?",
                    (entity_id,),
                )
                to = (data or {}).get("to", "")
                if to:
                    self._conn.execute(
                        "INSERT INTO stats (handle, dms_received) VALUES (?, 1) "
                        "ON CONFLICT(handle) DO UPDATE SET dms_received = dms_received + 1",
                        (to,),
                    )
        self._conn.commit()

    def _row_to_dict(self, r: tuple) -> dict:
        return {"idx": r[0], "t": r[1], "entity": r[2], "type": r[3], "data": json.loads(r[4])}

    def read_since(self, since_id: int = 0) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, t, entity, type, data FROM events WHERE id > ? ORDER BY id",
            (since_id,),
        ).fetchall()
        return [self._row_to_dict(r) for r in rows]

    def count(self) -> int:
        return self._conn.execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def count_by_entity_type(self, entity: str, event_type: str) -> int:
        return self._conn.execute(
            "SELECT COUNT(*) FROM events WHERE entity = ? AND type = ?",
            (entity, event_type),
        ).fetchone()[0]

    def board_posts(self, limit: int = 30) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, t, entity, type, data FROM events WHERE type = 'board_post' ORDER BY id DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [self._row_to_dict(r) for r in reversed(rows)]

    def recent_conversations(self, since_t: float | None = None) -> dict[str, list[dict]]:
        """Return conversations with activity since since_t (default: last hour)."""
        if since_t is None:
            since_t = time() - 3600
        rows = self._conn.execute(
            "SELECT id, t, entity, type, data FROM events WHERE type = 'dm_sent' AND t > ? ORDER BY id",
            (since_t,),
        ).fetchall()
        pairs: dict[str, list[dict]] = {}
        for r in rows:
            event = self._row_to_dict(r)
            key = "-".join(sorted([r[2], event["data"].get("to", "")]))
            pairs.setdefault(key, []).append(event)
        return dict(sorted(pairs.items(), key=lambda x: len(x[1]), reverse=True))

    def agent_stats(self) -> list[dict]:
        """Read pre-computed stats — O(agents), not O(events)."""
        rows = self._conn.execute(
            "SELECT handle, events, posts, dms_sent, dms_received FROM stats"
        ).fetchall()
        return [
            {"handle": r[0], "events": r[1], "posts": r[2], "dms_sent": r[3], "dms_received": r[4]}
            for r in rows
        ]

    def agent_events(self, handle: str, event_type: str | None = None, limit: int = 50) -> list[dict]:
        if event_type:
            rows = self._conn.execute(
                "SELECT id, t, entity, type, data FROM events WHERE entity = ? AND type = ? ORDER BY id DESC LIMIT ?",
                (handle, event_type, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT id, t, entity, type, data FROM events WHERE entity = ? ORDER BY id DESC LIMIT ?",
                (handle, limit),
            ).fetchall()
        return [self._row_to_dict(r) for r in reversed(rows)]

    def agent_dms(self, handle: str, limit: int = 30) -> list[dict]:
        rows = self._conn.execute(
            "SELECT id, t, entity, type, data FROM events WHERE type = 'dm_sent' AND (entity = ? OR json_extract(data, '$.to') = ?) ORDER BY id DESC LIMIT ?",
            (handle, handle, limit),
        ).fetchall()
        return [self._row_to_dict(r) for r in reversed(rows)]
