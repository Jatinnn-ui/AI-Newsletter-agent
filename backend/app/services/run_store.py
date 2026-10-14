"""SQLite-backed store for run metadata, live view state and the event log.

The LangGraph checkpointer persists the workflow itself (needed to resume a
paused Human-in-the-Loop run); this store holds what the API serves: status,
stage progress, intermediate artifacts and an ordered event stream for SSE.
"""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.models.domain import utc_now_iso

_SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    run_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    mode TEXT NOT NULL,
    deterministic INTEGER NOT NULL DEFAULT 0,
    goal TEXT NOT NULL,
    request_json TEXT NOT NULL,
    current_stage TEXT,
    stages_json TEXT NOT NULL DEFAULT '{}',
    view_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT,
    error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    awaiting_since TEXT
);
CREATE INDEX IF NOT EXISTS idx_runs_created ON runs(created_at);
CREATE TABLE IF NOT EXISTS events (
    run_id TEXT NOT NULL,
    seq INTEGER NOT NULL,
    type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (run_id, seq)
);
"""

_JSON_COLS = {"stages_json": "stages", "view_json": "view", "result_json": "result", "request_json": "request"}


class RunStore:
    def __init__(self, path: Path | str) -> None:
        if str(path) != ":memory:":
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()
        with self._lock:
            if str(path) != ":memory:":
                self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    @staticmethod
    def _row(row: sqlite3.Row) -> dict[str, Any]:
        out = dict(row)
        for col, key in _JSON_COLS.items():
            raw = out.pop(col, None)
            out[key] = json.loads(raw) if raw else None
        out["deterministic"] = bool(out.get("deterministic"))
        out["stages"] = out.get("stages") or {}
        out["view"] = out.get("view") or {}
        return out

    # -- runs ---------------------------------------------------------------
    def create(self, run_id: str, *, mode: str, deterministic: bool, goal: str, request: dict[str, Any]) -> None:
        now = utc_now_iso()
        with self._lock:
            self._conn.execute(
                "INSERT INTO runs (run_id, status, mode, deterministic, goal, request_json, created_at, updated_at)"
                " VALUES (?, 'queued', ?, ?, ?, ?, ?, ?)",
                (run_id, mode, int(deterministic), goal, json.dumps(request), now, now),
            )

    def get(self, run_id: str) -> dict[str, Any] | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM runs WHERE run_id = ?", (run_id,)).fetchone()
        return self._row(row) if row else None

    def list(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT run_id, status, mode, deterministic, goal, current_stage, created_at, updated_at, error"
                " FROM runs ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        return [dict(r) | {"deterministic": bool(r["deterministic"])} for r in rows]

    def update(self, run_id: str, **fields: Any) -> None:
        if not fields:
            return
        cols, vals = [], []
        for key, value in fields.items():
            if key in ("stages", "view", "result"):
                key, value = f"{key}_json", (json.dumps(value, default=str) if value is not None else None)
            cols.append(f"{key} = ?")
            vals.append(value)
        cols.append("updated_at = ?")
        vals.append(utc_now_iso())
        with self._lock:
            self._conn.execute(f"UPDATE runs SET {', '.join(cols)} WHERE run_id = ?", (*vals, run_id))

    def transition_status(self, run_id: str, expected: str, new_status: str) -> bool:
        """Atomically change a status only when it still has the expected value."""
        with self._lock:
            cursor = self._conn.execute(
                "UPDATE runs SET status = ?, updated_at = ? WHERE run_id = ? AND status = ?",
                (new_status, utc_now_iso(), run_id, expected),
            )
        return cursor.rowcount == 1

    def count_active(self) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COUNT(*) FROM runs WHERE status IN ('queued', 'running')").fetchone()
        return int(row[0])

    def find(self, statuses: list[str]) -> list[dict[str, Any]]:
        marks = ",".join("?" for _ in statuses)
        with self._lock:
            rows = self._conn.execute(f"SELECT * FROM runs WHERE status IN ({marks})", statuses).fetchall()
        return [self._row(r) for r in rows]

    def older_than(self, days: float) -> list[str]:
        cutoff = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat(timespec="milliseconds")
        with self._lock:
            rows = self._conn.execute("SELECT run_id FROM runs WHERE updated_at < ?", (cutoff,)).fetchall()
        return [r[0] for r in rows]

    def delete(self, run_id: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM events WHERE run_id = ?", (run_id,))
            self._conn.execute("DELETE FROM runs WHERE run_id = ?", (run_id,))

    # -- events -------------------------------------------------------------
    def add_event(self, run_id: str, event_type: str, payload: dict[str, Any]) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events WHERE run_id = ?", (run_id,)).fetchone()
            seq = int(row[0]) + 1
            self._conn.execute(
                "INSERT INTO events (run_id, seq, type, payload_json, created_at) VALUES (?, ?, ?, ?, ?)",
                (run_id, seq, event_type, json.dumps(payload, default=str), utc_now_iso()),
            )
        return seq

    def last_seq(self, run_id: str) -> int:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(MAX(seq), 0) FROM events WHERE run_id = ?", (run_id,)).fetchone()
        return int(row[0])

    def events(
        self, run_id: str, after: int = 0, types: tuple[str, ...] | None = None, limit: int = 2000
    ) -> list[dict[str, Any]]:
        sql = "SELECT seq, type, payload_json, created_at FROM events WHERE run_id = ? AND seq > ?"
        args: list[Any] = [run_id, after]
        if types:
            sql += f" AND type IN ({','.join('?' for _ in types)})"
            args.extend(types)
        sql += " ORDER BY seq LIMIT ?"
        args.append(limit)
        with self._lock:
            rows = self._conn.execute(sql, args).fetchall()
        return [
            {"seq": r["seq"], "type": r["type"], "data": json.loads(r["payload_json"]), "created_at": r["created_at"]}
            for r in rows
        ]
