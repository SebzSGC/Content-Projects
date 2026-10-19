"""SQLite WAL index for projects, assets, transcripts, jobs and settings."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from vidforge.infra.paths import USERDATA_DIR, ensure_directories


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class Database:
    def __init__(self, db_path: Path | None = None) -> None:
        ensure_directories()
        self.db_path = db_path or (USERDATA_DIR / "vidforge.db")
        self._lock = threading.RLock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        with self._lock, self._connect() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    folder_path TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    data_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    name TEXT NOT NULL,
                    file_path TEXT NOT NULL,
                    thumb_path TEXT,
                    duration_us INTEGER DEFAULT 0,
                    width INTEGER DEFAULT 0,
                    height INTEGER DEFAULT 0,
                    meta_json TEXT DEFAULT '{}',
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS transcripts (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    audio_asset_id TEXT NOT NULL,
                    data_json TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    project_id TEXT,
                    type TEXT NOT NULL,
                    state TEXT NOT NULL,
                    progress REAL DEFAULT 0.0,
                    stage TEXT DEFAULT '',
                    params_json TEXT DEFAULT '{}',
                    result_json TEXT,
                    error_json TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT
                );
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value_json TEXT NOT NULL
                );
                """
            )

    def upsert_project(self, proj: dict[str, Any], folder_path: Path) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT INTO projects (id, name, folder_path, created_at, updated_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    name=excluded.name,
                    folder_path=excluded.folder_path,
                    updated_at=excluded.updated_at,
                    data_json=excluded.data_json
                """,
                (
                    proj["id"],
                    proj["name"],
                    str(folder_path),
                    proj["created_at"],
                    proj["updated_at"],
                    json.dumps(proj),
                ),
            )

    def get_project(self, project_id: str) -> tuple[dict[str, Any], Path] | None:
        with self._lock, self._connect() as conn:
            row = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if not row:
                return None
            return json.loads(row["data_json"]), Path(row["folder_path"])

    def list_projects(self) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT data_json FROM projects ORDER BY updated_at DESC").fetchall()
            return [json.loads(r["data_json"]) for r in rows]

    def delete_project(self, project_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM projects WHERE id = ?", (project_id,))
            conn.execute("DELETE FROM assets WHERE project_id = ?", (project_id,))
            conn.execute("DELETE FROM transcripts WHERE project_id = ?", (project_id,))

    def insert_asset(self, asset: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO assets
                (id, project_id, kind, name, file_path, thumb_path, duration_us, width, height, meta_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset["id"],
                    asset["project_id"],
                    asset["kind"],
                    asset["name"],
                    asset["file_path"],
                    asset.get("thumb_path"),
                    asset.get("duration_us", 0),
                    asset.get("width", 0),
                    asset.get("height", 0),
                    json.dumps(asset.get("meta", {})),
                    asset.get("created_at", utc_now_iso()),
                ),
            )

    def get_asset(self, asset_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            r = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if not r:
                return None
            return {
                "id": r["id"],
                "project_id": r["project_id"],
                "kind": r["kind"],
                "name": r["name"],
                "file_path": r["file_path"],
                "thumb_path": r["thumb_path"],
                "duration_us": r["duration_us"],
                "width": r["width"],
                "height": r["height"],
                "meta": json.loads(r["meta_json"] or "{}"),
                "created_at": r["created_at"],
            }

    def delete_asset(self, asset_id: str) -> bool:
        with self._lock, self._connect() as conn:
            cur = conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            return cur.rowcount > 0

    def list_assets(self, project_id: str, kind: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            if kind:
                rows = conn.execute(
                    "SELECT * FROM assets WHERE project_id = ? AND kind = ? ORDER BY created_at ASC",
                    (project_id, kind),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM assets WHERE project_id = ? ORDER BY created_at ASC",
                    (project_id,),
                ).fetchall()
            return [
                {
                    "id": r["id"],
                    "project_id": r["project_id"],
                    "kind": r["kind"],
                    "name": r["name"],
                    "file_path": r["file_path"],
                    "thumb_path": r["thumb_path"],
                    "duration_us": r["duration_us"],
                    "width": r["width"],
                    "height": r["height"],
                    "meta": json.loads(r["meta_json"] or "{}"),
                    "created_at": r["created_at"],
                }
                for r in rows
            ]

    def save_transcript(self, transcript: dict[str, Any], project_id: str) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO transcripts (id, project_id, audio_asset_id, data_json, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    transcript["id"],
                    project_id,
                    transcript["audio_asset_id"],
                    json.dumps(transcript),
                    utc_now_iso(),
                ),
            )

    def get_transcript(self, transcript_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            r = conn.execute("SELECT data_json FROM transcripts WHERE id = ?", (transcript_id,)).fetchone()
            return json.loads(r["data_json"]) if r else None

    def upsert_job(self, job: dict[str, Any]) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO jobs
                (id, project_id, type, state, progress, stage, params_json, result_json, error_json, created_at, started_at, finished_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job["id"],
                    job.get("project_id"),
                    job["type"],
                    job["state"],
                    job.get("progress", 0.0),
                    job.get("stage", ""),
                    json.dumps(job.get("params", {})),
                    json.dumps(job["result"]) if job.get("result") is not None else None,
                    json.dumps(job["error"]) if job.get("error") is not None else None,
                    job["created_at"],
                    job.get("started_at"),
                    job.get("finished_at"),
                ),
            )

    def get_job(self, job_id: str) -> dict[str, Any] | None:
        with self._lock, self._connect() as conn:
            r = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            if not r:
                return None
            return self._row_to_job(r)

    def list_jobs(self, project_id: str | None = None) -> list[dict[str, Any]]:
        with self._lock, self._connect() as conn:
            if project_id:
                rows = conn.execute(
                    "SELECT * FROM jobs WHERE project_id = ? ORDER BY created_at DESC LIMIT 100",
                    (project_id,),
                ).fetchall()
            else:
                rows = conn.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 100").fetchall()
            return [self._row_to_job(r) for r in rows]

    @staticmethod
    def _row_to_job(r: sqlite3.Row) -> dict[str, Any]:
        return {
            "id": r["id"],
            "project_id": r["project_id"],
            "type": r["type"],
            "state": r["state"],
            "progress": r["progress"],
            "stage": r["stage"],
            "params": json.loads(r["params_json"] or "{}"),
            "result": json.loads(r["result_json"]) if r["result_json"] else None,
            "error": json.loads(r["error_json"]) if r["error_json"] else None,
            "created_at": r["created_at"],
            "started_at": r["started_at"],
            "finished_at": r["finished_at"],
        }

    def get_settings(self) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT key, value_json FROM settings").fetchall()
            out = {
                "whisper_model": "base",
                "default_fps": 60,
                "default_transition": "fade",
                "transition_duration_us": 500000,
                "ken_burns_enabled": True,
                "ollama_url": "http://127.0.0.1:11434",
                "ollama_model": "qwen2.5:3b",
                "capcut_drafts_dir": "",
            }
            for r in rows:
                out[r["key"]] = json.loads(r["value_json"])
            return out

    def update_settings(self, patch: dict[str, Any]) -> dict[str, Any]:
        with self._lock, self._connect() as conn:
            for k, v in patch.items():
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value_json) VALUES (?, ?)",
                    (k, json.dumps(v)),
                )
        return self.get_settings()


db = Database()
