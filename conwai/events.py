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
