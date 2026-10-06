"""Persistence helpers: JSON store for session state, SQLite for long-term."""
from __future__ import annotations

import json
import os
import sqlite3
import tempfile
from pathlib import Path
from typing import Any


class JsonStore:
    """Atomic JSON file store used for session memory and caches."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def read(self, default: Any = None) -> Any:
        if not self.path.exists():
            return default if default is not None else {}
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return default if default is not None else {}

    def write(self, data: Any) -> None:
        # write to temp then replace to avoid torn files
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2, ensure_ascii=False, default=str)
            os.replace(tmp, self.path)
        finally:
            if os.path.exists(tmp):
                try:
                    os.remove(tmp)
                except OSError:
                    pass


class SqliteStore:
    """Simple key/value + record store backed by SQLite for long-term memory."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path))
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS preferences (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at REAL NOT NULL
            );
            CREATE TABLE IF NOT EXISTS entities (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                kind TEXT NOT NULL,
                value TEXT NOT NULL,
                created_at REAL NOT NULL,
                UNIQUE(kind, value)
            );
            """
        )
        self._conn.commit()

    def get(self, key: str, default: Any = None) -> Any:
        row = self._conn.execute("SELECT value FROM preferences WHERE key=?", (key,)).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except json.JSONDecodeError:
            return row["value"]

    def set(self, key: str, value: Any) -> None:
        import time

        self._conn.execute(
            "INSERT INTO preferences(key, value, updated_at) VALUES(?,?,?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
            (key, json.dumps(value, default=str), time.time()),
        )
        self._conn.commit()

    def delete(self, key: str) -> None:
        self._conn.execute("DELETE FROM preferences WHERE key=?", (key,))
        self._conn.commit()

    def all_keys(self) -> list[str]:
        return [r["key"] for r in self._conn.execute("SELECT key FROM preferences")]

    def remember_entity(self, kind: str, value: str) -> None:
        import time

        self._conn.execute(
            "INSERT OR IGNORE INTO entities(kind, value, created_at) VALUES(?,?,?)",
            (kind, value, time.time()),
        )
        self._conn.commit()

    def recent_entities(self, kind: str, limit: int = 10) -> list[str]:
        rows = self._conn.execute(
            "SELECT value FROM entities WHERE kind=? ORDER BY created_at DESC LIMIT ?",
            (kind, limit),
        ).fetchall()
        return [r["value"] for r in rows]

    def close(self) -> None:
        self._conn.close()
