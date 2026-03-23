from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from time import time
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from conwai.event_bus import EventBus


class EventLog:
    def __init__(self, path: Path = Path("data/events.db")):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        conn = self._conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                t REAL NOT NULL,
                entity TEXT NOT NULL,
                type TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}'
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_entity ON events(entity)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_type ON events(type)")
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_entity_type ON events(entity, type)"
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_t ON events(t)")
        conn.commit()

    def _conn(self) -> sqlite3.Connection:
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self.path))
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA synchronous=NORMAL")
            self._local.conn = conn
        return conn

    def log(self, entity_id: str, event_type: str, data: dict | None = None):
        conn = self._conn()
        conn.execute(
            "INSERT INTO events (t, entity, type, data) VALUES (?, ?, ?, ?)",
            (time(), entity_id, event_type, json.dumps(data or {})),
        )
        conn.commit()

    def _row_to_dict(self, r: tuple) -> dict:
        return {
            "idx": r[0],
            "t": r[1],
            "entity": r[2],
            "type": r[3],
            "data": json.loads(r[4]),
        }

    def read_since(self, since_id: int = 0) -> list[dict]:
        rows = (
            self._conn()
            .execute(
                "SELECT id, t, entity, type, data FROM events WHERE id > ? ORDER BY id",
                (since_id,),
            )
            .fetchall()
        )
        return [self._row_to_dict(r) for r in rows]

    def count(self) -> int:
        return self._conn().execute("SELECT COUNT(*) FROM events").fetchone()[0]

    def count_by_entity_type(self, entity: str, event_type: str) -> int:
        return (
            self._conn()
            .execute(
                "SELECT COUNT(*) FROM events WHERE entity = ? AND type = ?",
                (entity, event_type),
            )
            .fetchone()[0]
        )

    def subscribe_to(self, bus: EventBus) -> None:
        """Subscribe to an EventBus to auto-persist lifecycle and action events."""
        from conwai.event_types import ActionExecuted, EntityDestroyed, EntitySpawned

        def on_action(event: ActionExecuted):
            log_data = dict(event.args)
            log_data.update(event.data)
            self.log(event.entity, event.action, log_data)

        def on_spawned(event: EntitySpawned):
            self.log(event.entity, "entity_spawned", {})

        def on_destroyed(event: EntityDestroyed):
            self.log(event.entity, "entity_destroyed", {})

        bus.subscribe(ActionExecuted, on_action)
        bus.subscribe(EntitySpawned, on_spawned)
        bus.subscribe(EntityDestroyed, on_destroyed)

    def agent_events(
        self, handle: str, event_type: str | None = None, limit: int = 50
    ) -> list[dict]:
        if event_type:
            rows = (
                self._conn()
                .execute(
                    "SELECT id, t, entity, type, data FROM events WHERE entity = ? AND type = ? ORDER BY id DESC LIMIT ?",
                    (handle, event_type, limit),
                )
                .fetchall()
            )
        else:
            rows = (
                self._conn()
                .execute(
                    "SELECT id, t, entity, type, data FROM events WHERE entity = ? ORDER BY id DESC LIMIT ?",
                    (handle, limit),
                )
                .fetchall()
            )
        return [self._row_to_dict(r) for r in reversed(rows)]
