from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path
from typing import Protocol, runtime_checkable


@runtime_checkable
class Storage(Protocol):
    def save_component(self, entity: str, component: str, data: dict) -> None: ...
    def load_component(self, entity: str, component: str) -> dict | None: ...
    def list_entities(self) -> list[str]: ...
    def list_components(self, entity: str) -> list[str]: ...
    def delete_entity(self, entity: str) -> None: ...


class SQLiteStorage:
    def __init__(self, path: Path = Path("data/state.db")):
        self._path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        self._local = threading.local()
        # Initialize schema on the creating thread
        conn = self._conn()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS components (
                entity TEXT NOT NULL,
                component TEXT NOT NULL,
                data TEXT NOT NULL DEFAULT '{}',
                PRIMARY KEY (entity, component)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS commands (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                data TEXT NOT NULL
            )
        """)
        conn.commit()

    def _conn(self) -> sqlite3.Connection:
        """Return a thread-local connection."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._path))
            try:
                conn.execute("PRAGMA journal_mode=WAL")
                conn.execute("PRAGMA synchronous=NORMAL")
            except sqlite3.DatabaseError:
                conn.close()
                raise
            self._local.conn = conn
        return conn

    def save_component(self, entity: str, component: str, data: dict) -> None:
        conn = self._conn()
        conn.execute(
            "INSERT OR REPLACE INTO components (entity, component, data) VALUES (?, ?, ?)",
            (entity, component, json.dumps(data)),
        )
        conn.commit()

    def load_component(self, entity: str, component: str) -> dict | None:
        row = (
            self._conn()
            .execute(
                "SELECT data FROM components WHERE entity = ? AND component = ?",
                (entity, component),
            )
            .fetchone()
        )
        if row is None:
            return None
        try:
            return json.loads(row[0])
        except (json.JSONDecodeError, TypeError):
            return None

    def list_entities(self) -> list[str]:
        rows = (
            self._conn()
            .execute("SELECT DISTINCT entity FROM components ORDER BY entity")
            .fetchall()
        )
        return [r[0] for r in rows]

    def list_components(self, entity: str) -> list[str]:
        rows = (
            self._conn()
            .execute(
                "SELECT component FROM components WHERE entity = ? ORDER BY component",
                (entity,),
            )
            .fetchall()
        )
        return [r[0] for r in rows]

    def delete_entity(self, entity: str) -> None:
        conn = self._conn()
        conn.execute("DELETE FROM components WHERE entity = ?", (entity,))
        conn.commit()

    def push_command(self, data: dict) -> None:
        conn = self._conn()
        conn.execute("INSERT INTO commands (data) VALUES (?)", (json.dumps(data),))
        conn.commit()

    def pop_commands(self) -> list[dict]:
        conn = self._conn()
        rows = conn.execute("SELECT id, data FROM commands ORDER BY id").fetchall()
        if not rows:
            return []
        conn.execute("DELETE FROM commands WHERE id <= ?", (rows[-1][0],))
        conn.commit()
        return [json.loads(r[1]) for r in rows]
