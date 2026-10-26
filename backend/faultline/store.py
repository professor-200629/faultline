"""SQLite persistence.

Two access classes share one database file but different tables:
  * `Store`       - public run records: status, events, model calls, spend.
  * `SealedStore` - judge-only: hidden case configuration, seeds, grades.
Agent-facing code is only ever handed a `Store`-backed recorder.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Optional

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  kind TEXT NOT NULL,
  mode TEXT NOT NULL,
  status TEXT NOT NULL,
  status_reason TEXT NOT NULL DEFAULT '',
  public_json TEXT NOT NULL,
  budgets_json TEXT NOT NULL DEFAULT '{}',
  provider_json TEXT NOT NULL DEFAULT '{}',
  counters_json TEXT NOT NULL DEFAULT '{}',
  diagnosis_json TEXT,
  board_json TEXT,
  evidence_json TEXT NOT NULL DEFAULT '[]',
  predictions_json TEXT NOT NULL DEFAULT '[]',
  remedy_json TEXT,
  versions_json TEXT NOT NULL DEFAULT '{}',
  revealed INTEGER NOT NULL DEFAULT 0,
  replay_of TEXT,
  terminal_at REAL
);
CREATE TABLE IF NOT EXISTS events (
  run_id TEXT NOT NULL,
  seq INTEGER NOT NULL,
  at REAL NOT NULL,
  type TEXT NOT NULL,
  payload_json TEXT NOT NULL,
  PRIMARY KEY (run_id, seq)
);
CREATE TABLE IF NOT EXISTS model_calls (
  run_id TEXT NOT NULL,
  n INTEGER NOT NULL,
  at REAL NOT NULL,
  record_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS spend (
  at REAL NOT NULL,
  run_id TEXT NOT NULL,
  usd REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS replay_bundles (
  run_id TEXT PRIMARY KEY,
  source_name TEXT NOT NULL,
  bundle_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS sealed_cases (
  run_id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  truth_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS remedy_checks (
  run_id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  check_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS grades (
  run_id TEXT PRIMARY KEY,
  created_at REAL NOT NULL,
  grade_json TEXT NOT NULL
);
"""

TERMINAL = ("diagnosed", "inconclusive", "failed", "cancelled")
STATES = ("ready", "investigating", "awaiting_approval") + TERMINAL


class _DB:
    def __init__(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(path), check_same_thread=False, isolation_level=None)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        self.lock = threading.RLock()

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        with self.lock:
            return self.conn.execute(sql, params)


_J = json.dumps


def _load(v: Optional[str]) -> Any:
    return json.loads(v) if v else None


class Store:
    def __init__(self, db: _DB) -> None:
        self._db = db

    # ---- runs ----
    def create_run(self, run_id: str, kind: str, mode: str, public: dict, budgets: dict, provider: dict,
                   replay_of: Optional[str] = None) -> None:
        self._db.execute(
            "INSERT INTO runs (id, created_at, kind, mode, status, public_json, budgets_json, provider_json, replay_of)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (run_id, time.time(), kind, mode, "ready", _J(public), _J(budgets), _J(provider), replay_of),
        )

    def update_run(self, run_id: str, **fields: Any) -> None:
        cols, vals = [], []
        for k, v in fields.items():
            if k.endswith("_json"):
                v = _J(v)
            cols.append(f"{k}=?")
            vals.append(v)
        if fields.get("status") in TERMINAL:
            cols.append("terminal_at=?")
            vals.append(time.time())
        vals.append(run_id)
        self._db.execute(f"UPDATE runs SET {', '.join(cols)} WHERE id=?", tuple(vals))

    def get_run(self, run_id: str) -> Optional[dict]:
        r = self._db.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
        return self._row(r) if r else None

    def list_runs(self, limit: int = 100) -> list[dict]:
        rows = self._db.execute("SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [self._row(r) for r in rows]

    @staticmethod
    def _row(r: sqlite3.Row) -> dict:
        d = dict(r)
        for k in list(d):
            if k.endswith("_json"):
                d[k[:-5]] = _load(d.pop(k))
        d["revealed"] = bool(d["revealed"])
        return d

    # ---- replays (recorded bundles imported for playback) ----
    def put_replay(self, run_id: str, source_name: str, bundle: dict) -> None:
        self._db.execute("INSERT INTO replay_bundles (run_id, source_name, bundle_json) VALUES (?,?,?)",
                         (run_id, source_name, _J(bundle)))

    def get_replay(self, run_id: str) -> Optional[dict]:
        r = self._db.execute("SELECT bundle_json FROM replay_bundles WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(r[0]) if r else None

    def replay_sources(self) -> set[str]:
        return {r[0] for r in self._db.execute("SELECT source_name FROM replay_bundles").fetchall()}

    # ---- events ----
    def add_event(self, run_id: str, type_: str, payload: dict) -> int:
        with self._db.lock:
            row = self._db.execute("SELECT COALESCE(MAX(seq), 0) FROM events WHERE run_id=?", (run_id,)).fetchone()
            seq = int(row[0]) + 1
            self._db.execute("INSERT INTO events (run_id, seq, at, type, payload_json) VALUES (?,?,?,?,?)",
                             (run_id, seq, time.time(), type_, _J(payload)))
            return seq

    def events(self, run_id: str, after: int = 0) -> list[dict]:
        rows = self._db.execute("SELECT seq, at, type, payload_json FROM events WHERE run_id=? AND seq>? ORDER BY seq",
                                (run_id, after)).fetchall()
        return [{"seq": r["seq"], "at": r["at"], "type": r["type"], "payload": json.loads(r["payload_json"])} for r in rows]

    # ---- model calls & spend ----
    def add_model_call(self, run_id: str, record: dict) -> None:
        self._db.execute("INSERT INTO model_calls (run_id, n, at, record_json) VALUES (?,?,?,?)",
                         (run_id, int(record.get("n", 0)), time.time(), _J(record)))

    def model_calls(self, run_id: str) -> list[dict]:
        rows = self._db.execute("SELECT record_json FROM model_calls WHERE run_id=? ORDER BY rowid", (run_id,)).fetchall()
        return [json.loads(r[0]) for r in rows]

    def add_spend(self, run_id: str, usd: float) -> None:
        self._db.execute("INSERT INTO spend (at, run_id, usd) VALUES (?,?,?)", (time.time(), run_id, usd))

    def total_spend(self) -> float:
        return float(self._db.execute("SELECT COALESCE(SUM(usd), 0) FROM spend").fetchone()[0])


class SealedStore:
    """Judge-only tables. Never handed to agent-facing code."""

    def __init__(self, db: _DB) -> None:
        self._db = db

    def __repr__(self) -> str:
        return "SealedStore(<redacted>)"

    def put_truth(self, run_id: str, truth: dict) -> None:
        self._db.execute("INSERT INTO sealed_cases (run_id, created_at, truth_json) VALUES (?,?,?)",
                         (run_id, time.time(), _J(truth)))

    def get_truth(self, run_id: str) -> Optional[dict]:
        r = self._db.execute("SELECT truth_json FROM sealed_cases WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(r[0]) if r else None

    def put_remedy_check(self, run_id: str, check: dict) -> None:
        self._db.execute("INSERT OR REPLACE INTO remedy_checks (run_id, created_at, check_json) VALUES (?,?,?)",
                         (run_id, time.time(), _J(check)))

    def get_remedy_check(self, run_id: str) -> Optional[dict]:
        r = self._db.execute("SELECT check_json FROM remedy_checks WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(r[0]) if r else None

    def put_grade(self, run_id: str, grade: dict) -> None:
        self._db.execute("INSERT OR REPLACE INTO grades (run_id, created_at, grade_json) VALUES (?,?,?)",
                         (run_id, time.time(), _J(grade)))

    def get_grade(self, run_id: str) -> Optional[dict]:
        r = self._db.execute("SELECT grade_json FROM grades WHERE run_id=?", (run_id,)).fetchone()
        return json.loads(r[0]) if r else None


def open_stores(path: Path) -> tuple[Store, SealedStore]:
    db = _DB(path)
    return Store(db), SealedStore(db)
