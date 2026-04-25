"""Graph checkpoint stores.

These checkpoints are graph-layer recovery snapshots, not the #39 sessions/messages
database. A future adapter can bridge this protocol to the #39 store.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Protocol

from legacy.graph.state import ClassroomState, state_from_jsonable, state_to_jsonable


class CheckpointStore(Protocol):
    async def save_checkpoint(
        self, session_id: str, state: ClassroomState, *, node: str, event_seq: int
    ) -> None: ...
    async def load_latest(self, session_id: str) -> ClassroomState | None: ...


class InMemoryCheckpointStore:
    def __init__(self) -> None:
        self._items: dict[str, list[dict[str, object]]] = {}

    async def save_checkpoint(
        self, session_id: str, state: ClassroomState, *, node: str, event_seq: int
    ) -> None:
        self._items.setdefault(session_id, []).append(
            {"node": node, "event_seq": event_seq, "state": state_to_jsonable(state)}
        )

    async def load_latest(self, session_id: str) -> ClassroomState | None:
        rows = self._items.get(session_id) or []
        if not rows:
            return None
        return state_from_jsonable(rows[-1]["state"])  # type: ignore[arg-type]


class SQLiteCheckpointStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self._ensure_table()

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.db_path)

    def _ensure_table(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS classroom_checkpoints (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL,
                    turn_index INTEGER NOT NULL,
                    node TEXT NOT NULL,
                    event_seq INTEGER NOT NULL,
                    state_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )

    async def save_checkpoint(
        self, session_id: str, state: ClassroomState, *, node: str, event_seq: int
    ) -> None:
        payload = json.dumps(state_to_jsonable(state), ensure_ascii=False)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO classroom_checkpoints (session_id, turn_index, node, event_seq, state_json, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (
                    session_id,
                    state["turn_index"],
                    node,
                    event_seq,
                    payload,
                    datetime.now(timezone.utc).isoformat(),
                ),
            )

    async def load_latest(self, session_id: str) -> ClassroomState | None:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT state_json FROM classroom_checkpoints WHERE session_id = ? ORDER BY id DESC LIMIT 1",
                (session_id,),
            ).fetchone()
        if row is None:
            return None
        return state_from_jsonable(json.loads(row[0]))
