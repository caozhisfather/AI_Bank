from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from carbon_finance.config import DATA_DIR


class PersistentStore:
    """Small SQLite audit store for local competition demos."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or DATA_DIR / "runtime" / "platform.db"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = RLock()
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS datasets (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS workflows (
                    id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def save_dataset(self, dataset_id: str, payload: dict, keep: int = 100) -> None:
        self._save("datasets", dataset_id, payload, keep)

    def get_dataset(self, dataset_id: str) -> dict | None:
        return self._get("datasets", dataset_id)

    def save_workflow(self, workflow_id: str, payload: dict, keep: int = 100) -> None:
        self._save("workflows", workflow_id, payload, keep)

    def get_workflow(self, workflow_id: str) -> dict | None:
        return self._get("workflows", workflow_id)

    def list_workflows(self, limit: int) -> list[dict]:
        with self._lock, self._connect() as connection:
            rows = connection.execute(
                "SELECT payload FROM workflows ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [json.loads(row[0]) for row in rows]

    def _save(self, table: str, item_id: str, payload: dict, keep: int) -> None:
        created_at = datetime.now(timezone.utc).isoformat()
        encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
        with self._lock, self._connect() as connection:
            connection.execute(
                f"INSERT OR REPLACE INTO {table} (id, created_at, payload) VALUES (?, ?, ?)",
                (item_id, created_at, encoded),
            )
            connection.execute(
                f"DELETE FROM {table} WHERE id NOT IN (SELECT id FROM {table} ORDER BY created_at DESC LIMIT ?)",
                (keep,),
            )

    def _get(self, table: str, item_id: str) -> dict | None:
        with self._lock, self._connect() as connection:
            row = connection.execute(f"SELECT payload FROM {table} WHERE id = ?", (item_id,)).fetchone()
        return json.loads(row[0]) if row else None


persistent_store = PersistentStore()
