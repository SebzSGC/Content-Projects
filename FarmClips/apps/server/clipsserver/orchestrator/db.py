"""SQLite persistent state store: sessions, tasks (with lease_until), artifacts (by hash), api_calls, and clips."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from clipscore.domain import SessionState, new_id


def stable_hash(payload: Any) -> str:
    serialized = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]


SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL DEFAULT '',
    recording_name TEXT NOT NULL DEFAULT '',
    state TEXT NOT NULL DEFAULT 'NEW',
    gameplay_path TEXT,
    camera_path TEXT,
    drive_folder_id TEXT,
    language TEXT NOT NULL DEFAULT 'es',
    style_preset TEXT NOT NULL DEFAULT 'hormozi-gaming',
    sync_json TEXT,
    prepared_json TEXT,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS tasks (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    clip_id TEXT,
    kind TEXT NOT NULL,
    hash_key TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'PENDING',
    attempts INTEGER NOT NULL DEFAULT 0,
    not_before REAL NOT NULL DEFAULT 0,
    lease_until REAL NOT NULL DEFAULT 0,
    priority REAL NOT NULL DEFAULT 0,
    error TEXT,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tasks_session ON tasks(session_id);
CREATE INDEX IF NOT EXISTS idx_tasks_hash ON tasks(hash_key);

CREATE TABLE IF NOT EXISTS artifacts (
    hash_key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    path TEXT NOT NULL,
    size_bytes INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS api_calls (
    id TEXT PRIMARY KEY,
    session_id TEXT,
    task_hash TEXT NOT NULL,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    kind TEXT NOT NULL,
    raw_response_path TEXT NOT NULL,
    units_billed REAL NOT NULL DEFAULT 0,
    input_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens INTEGER NOT NULL DEFAULT 0,
    cost_usd REAL NOT NULL DEFAULT 0,
    latency_ms INTEGER NOT NULL DEFAULT 0,
    created_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_api_calls_hash ON api_calls(task_hash);

CREATE TABLE IF NOT EXISTS clips (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    rank_order INTEGER NOT NULL DEFAULT 0,
    start_sec REAL NOT NULL,
    end_sec REAL NOT NULL,
    overlay_title TEXT NOT NULL,
    post_title TEXT NOT NULL,
    hashtags_json TEXT NOT NULL DEFAULT '[]',
    reason TEXT NOT NULL DEFAULT '',
    llm_score REAL NOT NULL DEFAULT 0,
    signal_score REAL NOT NULL DEFAULT 0,
    final_score REAL NOT NULL DEFAULT 0,
    curated_json TEXT NOT NULL,
    editplan_json TEXT,
    draft_mp4_path TEXT,
    final_mp4_path TEXT,
    drive_salidas_json TEXT,
    state TEXT NOT NULL DEFAULT 'CURATED',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_clips_session ON clips(session_id);
"""


class BudgetExceededError(RuntimeError):
    pass


class OrchestratorDB:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.db_path), check_same_thread=False, timeout=30.0)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- Crash recovery via lease_until ------------------------------------

    def recover_expired_leases(self) -> int:
        now = time.time()
        with self._lock:
            cur = self._conn.execute(
                "UPDATE tasks SET state = 'PENDING', lease_until = 0, updated_at = ? "
                "WHERE state = 'RUNNING' AND lease_until < ?",
                (now, now),
            )
            self._conn.commit()
            return cur.rowcount

    def sessions_to_resume(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE state NOT IN ('DELIVERED', 'FAILED', 'CANCELLED') ORDER BY created_at ASC"
            ).fetchall()
            return [dict(r) for r in rows]

    # --- Sessions ----------------------------------------------------------

    def create_session(
        self,
        title: str,
        gameplay_path: Optional[str] = None,
        camera_path: Optional[str] = None,
        recording_name: str = "",
        drive_folder_id: Optional[str] = None,
        language: str = "es",
        style_preset: str = "hormozi-gaming",
        initial_state: SessionState = SessionState.NEW,
        session_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        sid = session_id or new_id("ses")
        now = time.time()
        rec = recording_name or title or sid
        with self._lock:
            self._conn.execute(
                """INSERT INTO sessions (
                    id, title, recording_name, state, gameplay_path, camera_path,
                    drive_folder_id, language, style_preset, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sid,
                    title,
                    rec,
                    initial_state.value,
                    gameplay_path,
                    camera_path,
                    drive_folder_id,
                    language,
                    style_preset,
                    now,
                    now,
                ),
            )
            self._conn.commit()
        return self.get_session(sid)  # type: ignore[return-value]

    def find_session_by_drive_folder(self, folder_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE drive_folder_id = ? ORDER BY created_at DESC LIMIT 1",
                (folder_id,),
            ).fetchone()
            return dict(row) if row else None

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            return dict(row) if row else None

    def list_sessions(self) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
            return [dict(r) for r in rows]

    def update_session(self, session_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [session_id]
        with self._lock:
            self._conn.execute(f"UPDATE sessions SET {cols} WHERE id = ?", vals)
            self._conn.commit()

    # --- Tasks & Artifacts (Idempotent Cache) ------------------------------

    def get_artifact_path(self, hash_key: str) -> Optional[Path]:
        with self._lock:
            row = self._conn.execute("SELECT path FROM artifacts WHERE hash_key = ?", (hash_key,)).fetchone()
            if not row:
                return None
            p = Path(row["path"])
            return p if p.exists() else None

    def put_artifact(self, hash_key: str, kind: str, path: Path) -> None:
        size = path.stat().st_size if path.is_file() else 0
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO artifacts (hash_key, kind, path, size_bytes, created_at) VALUES (?, ?, ?, ?, ?)",
                (hash_key, kind, str(path.resolve()), size, time.time()),
            )
            self._conn.commit()

    def start_task(
        self,
        session_id: str,
        kind: str,
        hash_key: str,
        clip_id: Optional[str] = None,
        priority: float = 0.0,
        lease_sec: float = 300.0,
    ) -> str:
        now = time.time()
        tid = new_id("tsk")
        with self._lock:
            self._conn.execute(
                """INSERT INTO tasks (
                    id, session_id, clip_id, kind, hash_key, state, attempts,
                    not_before, lease_until, priority, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, 'RUNNING', 1, ?, ?, ?, ?, ?)""",
                (tid, session_id, clip_id, kind, hash_key, now, now + lease_sec, priority, now, now),
            )
            self._conn.commit()
        return tid

    def renew_task_lease(self, task_id: str, lease_sec: float = 300.0) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET lease_until = ?, updated_at = ? WHERE id = ? AND state = 'RUNNING'",
                (now + lease_sec, now, task_id),
            )
            self._conn.commit()

    def finish_task(self, task_id: str, state: str = "DONE", error: Optional[str] = None) -> None:
        now = time.time()
        with self._lock:
            self._conn.execute(
                "UPDATE tasks SET state = ?, lease_until = 0, error = ?, updated_at = ? WHERE id = ?",
                (state, error, now, task_id),
            )
            self._conn.commit()

    def list_session_tasks(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tasks WHERE session_id = ? ORDER BY created_at DESC LIMIT 50",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    # --- API Calls & Budget Guard ------------------------------------------

    def total_spend_usd(self) -> float:
        with self._lock:
            row = self._conn.execute("SELECT COALESCE(SUM(cost_usd), 0.0) AS total FROM api_calls").fetchone()
            return round(float(row["total"]) if row else 0.0, 6)

    def assert_within_budget(self, max_budget_usd: float) -> float:
        spent = self.total_spend_usd()
        if spent >= max_budget_usd:
            raise BudgetExceededError(
                f"Presupuesto de API alcanzado (${spent:.4f} >= tope ${max_budget_usd:.2f} USD). "
                "Aumenta CLIPS_MAX_BUDGET_USD para autorizar nuevas llamadas."
            )
        return spent

    def record_api_call(
        self,
        session_id: Optional[str],
        task_hash: str,
        provider: str,
        model: str,
        kind: str,
        raw_response_path: Path,
        units_billed: float = 0.0,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd: float = 0.0,
        latency_ms: int = 0,
    ) -> str:
        cid = new_id("call")
        with self._lock:
            self._conn.execute(
                """INSERT INTO api_calls (
                    id, session_id, task_hash, provider, model, kind, raw_response_path,
                    units_billed, input_tokens, output_tokens, cost_usd, latency_ms, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    cid,
                    session_id,
                    task_hash,
                    provider,
                    model,
                    kind,
                    str(raw_response_path.resolve()),
                    units_billed,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    latency_ms,
                    time.time(),
                ),
            )
            self._conn.commit()
        return cid

    def budget_summary(self, max_budget_usd: float) -> Dict[str, Any]:
        with self._lock:
            spent = self.total_spend_usd()
            by_prov = self._conn.execute(
                """SELECT provider, model, kind, COUNT(*) AS calls,
                          ROUND(SUM(units_billed), 2) AS units,
                          SUM(input_tokens) AS input_tokens,
                          SUM(output_tokens) AS output_tokens,
                          ROUND(SUM(cost_usd), 6) AS cost_usd
                   FROM api_calls GROUP BY provider, model, kind"""
            ).fetchall()
            return {
                "spent_usd": spent,
                "max_budget_usd": max_budget_usd,
                "remaining_usd": round(max(0.0, max_budget_usd - spent), 6),
                "calls_count": sum(int(r["calls"]) for r in by_prov),
                "breakdown": [dict(r) for r in by_prov],
            }

    # --- Clips -------------------------------------------------------------

    def upsert_clip(
        self,
        clip_id: str,
        session_id: str,
        rank_order: int,
        start_sec: float,
        end_sec: float,
        overlay_title: str,
        post_title: str,
        hashtags: List[str],
        reason: str,
        llm_score: float,
        signal_score: float,
        final_score: float,
        curated_json: str,
        editplan_json: Optional[str] = None,
        state: str = "CURATED",
    ) -> None:
        now = time.time()
        with self._lock:
            existing = self._conn.execute("SELECT id FROM clips WHERE id = ?", (clip_id,)).fetchone()
            if existing:
                self._conn.execute(
                    """UPDATE clips SET rank_order=?, start_sec=?, end_sec=?, overlay_title=?,
                       post_title=?, hashtags_json=?, reason=?, llm_score=?, signal_score=?,
                       final_score=?, curated_json=?, editplan_json=COALESCE(?, editplan_json),
                       state=?, updated_at=? WHERE id=?""",
                    (
                        rank_order,
                        start_sec,
                        end_sec,
                        overlay_title,
                        post_title,
                        json.dumps(hashtags, ensure_ascii=False),
                        reason,
                        llm_score,
                        signal_score,
                        final_score,
                        curated_json,
                        editplan_json,
                        state,
                        now,
                        clip_id,
                    ),
                )
            else:
                self._conn.execute(
                    """INSERT INTO clips (
                        id, session_id, rank_order, start_sec, end_sec, overlay_title, post_title,
                        hashtags_json, reason, llm_score, signal_score, final_score, curated_json,
                        editplan_json, state, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        clip_id,
                        session_id,
                        rank_order,
                        start_sec,
                        end_sec,
                        overlay_title,
                        post_title,
                        json.dumps(hashtags, ensure_ascii=False),
                        reason,
                        llm_score,
                        signal_score,
                        final_score,
                        curated_json,
                        editplan_json,
                        state,
                        now,
                        now,
                    ),
                )
            self._conn.commit()

    def update_clip(self, clip_id: str, **fields: Any) -> None:
        if not fields:
            return
        fields["updated_at"] = time.time()
        cols = ", ".join(f"{k} = ?" for k in fields)
        vals = list(fields.values()) + [clip_id]
        with self._lock:
            self._conn.execute(f"UPDATE clips SET {cols} WHERE id = ?", vals)
            self._conn.commit()

    def get_clip(self, clip_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute("SELECT * FROM clips WHERE id = ?", (clip_id,)).fetchone()
            return dict(row) if row else None

    def list_clips(self, session_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM clips WHERE session_id = ? ORDER BY rank_order ASC, final_score DESC",
                (session_id,),
            ).fetchall()
            return [dict(r) for r in rows]

    def delete_stale_session_clips(self, session_id: str, keep_clip_ids: List[str]) -> int:
        """Remove clips from a previous run of `session_id` that are no longer in `keep_clip_ids`."""
        with self._lock:
            if not keep_clip_ids:
                cur = self._conn.execute("DELETE FROM clips WHERE session_id = ?", (session_id,))
            else:
                placeholders = ",".join("?" for _ in keep_clip_ids)
                cur = self._conn.execute(
                    f"DELETE FROM clips WHERE session_id = ? AND id NOT IN ({placeholders})",
                    [session_id, *keep_clip_ids],
                )
            self._conn.commit()
            return cur.rowcount

    def purge_fixture_cache(self) -> int:
        """Delete cached `fixture_stt` / `fixture_llm` artifacts and api_calls so real APIs can run cleanly."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT task_hash FROM api_calls WHERE provider IN ('fixture_stt', 'fixture_llm')"
            ).fetchall()
            hashes = [str(r["task_hash"]) for r in rows if r["task_hash"]]
            removed = 0
            if hashes:
                placeholders = ",".join("?" for _ in hashes)
                art_rows = self._conn.execute(
                    f"SELECT path FROM artifacts WHERE hash_key IN ({placeholders})",
                    hashes,
                ).fetchall()
                for ar in art_rows:
                    try:
                        Path(str(ar["path"])).unlink(missing_ok=True)
                    except OSError:
                        pass
                cur = self._conn.execute(
                    f"DELETE FROM artifacts WHERE hash_key IN ({placeholders})",
                    hashes,
                )
                removed = cur.rowcount
            self._conn.execute("DELETE FROM api_calls WHERE provider IN ('fixture_stt', 'fixture_llm')")
            self._conn.commit()
            return removed
