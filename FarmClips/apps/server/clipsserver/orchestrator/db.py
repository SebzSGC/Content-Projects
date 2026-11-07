"""SQLite persistent state store: sessions, tasks (with lease_until), artifacts (by hash), api_calls, and clips."""

from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from datetime import datetime
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

CREATE TABLE IF NOT EXISTS provider_balances (
    provider TEXT PRIMARY KEY,
    balance_usd REAL NOT NULL,
    credit_usd REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'manual',
    recorded_at REAL NOT NULL
);
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

    # --- Provider balance calibration (real balance reported by provider console/API) ---

    def set_provider_balance(
        self, provider: str, balance_usd: float, credit_usd: float, source: str = "manual"
    ) -> Dict[str, Any]:
        now = time.time()
        with self._lock:
            self._conn.execute(
                """INSERT INTO provider_balances (provider, balance_usd, credit_usd, source, recorded_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(provider) DO UPDATE SET
                       balance_usd = excluded.balance_usd,
                       credit_usd = excluded.credit_usd,
                       source = excluded.source,
                       recorded_at = excluded.recorded_at""",
                (provider.lower(), float(balance_usd), float(credit_usd), source, now),
            )
            self._conn.commit()
        return self.get_provider_balance(provider) or {}

    def get_provider_balance(self, provider: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM provider_balances WHERE provider = ?", (provider.lower(),)
            ).fetchone()
            return dict(row) if row else None

    def clear_provider_balance(self, provider: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM provider_balances WHERE provider = ?", (provider.lower(),))
            self._conn.commit()

    def reprice_provider_calls(self, provider: str, usd_per_min: float) -> int:
        """Recompute `cost_usd` for STT calls of `provider` from billed seconds at a corrected per-minute rate."""
        with self._lock:
            cur = self._conn.execute(
                "UPDATE api_calls SET cost_usd = ROUND((units_billed / 60.0) * ?, 6) "
                "WHERE LOWER(provider) = ? AND kind = 'stt'",
                (float(usd_per_min), provider.lower()),
            )
            self._conn.commit()
            return cur.rowcount

    @staticmethod
    def _parse_date_bound(raw: Optional[str], end_of_day: bool = False) -> Optional[float]:
        if not raw:
            return None
        s = raw.strip()
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            pass
        try:
            if len(s) == 10 and s[4] == "-" and s[7] == "-":
                dt = datetime.strptime(s, "%Y-%m-%d")
                if end_of_day:
                    dt = dt.replace(hour=23, minute=59, second=59, microsecond=999999)
                return dt.timestamp()
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.timestamp()
        except Exception:
            return None

    def analytics_summary(self, max_budget_usd: float) -> Dict[str, Any]:
        """Compute aggregate KPIs, budget status, and capacity projections from `api_calls` and `clips`."""
        with self._lock:
            cap = max(0.01, float(max_budget_usd))
            agg = self._conn.execute(
                """SELECT
                       COUNT(*) AS total_calls,
                       COALESCE(SUM(CASE WHEN kind = 'stt' THEN 1 ELSE 0 END), 0) AS stt_calls,
                       COALESCE(SUM(CASE WHEN kind = 'llm' THEN 1 ELSE 0 END), 0) AS llm_calls,
                       COALESCE(SUM(cost_usd), 0.0) AS spent_usd,
                       COALESCE(SUM(CASE WHEN kind = 'stt' THEN cost_usd ELSE 0.0 END), 0.0) AS stt_cost_usd,
                       COALESCE(SUM(CASE WHEN kind = 'llm' THEN cost_usd ELSE 0.0 END), 0.0) AS llm_cost_usd,
                       COALESCE(SUM(CASE WHEN kind = 'stt' THEN units_billed ELSE 0.0 END), 0.0) AS audio_seconds_billed,
                       COALESCE(SUM(input_tokens), 0) AS input_tokens,
                       COALESCE(SUM(output_tokens), 0) AS output_tokens,
                       COALESCE(AVG(latency_ms), 0.0) AS avg_latency_ms,
                       COUNT(DISTINCT session_id) AS sessions_with_calls
                   FROM api_calls"""
            ).fetchone()

            total_calls = int(agg["total_calls"] or 0)
            stt_calls = int(agg["stt_calls"] or 0)
            llm_calls = int(agg["llm_calls"] or 0)
            spent_usd = round(float(agg["spent_usd"] or 0.0), 6)
            stt_cost_usd = round(float(agg["stt_cost_usd"] or 0.0), 6)
            llm_cost_usd = round(float(agg["llm_cost_usd"] or 0.0), 6)
            audio_seconds = round(float(agg["audio_seconds_billed"] or 0.0), 3)
            audio_minutes = round(audio_seconds / 60.0, 2)
            audio_hours = round(audio_seconds / 3600.0, 4)
            input_tokens = int(agg["input_tokens"] or 0)
            output_tokens = int(agg["output_tokens"] or 0)
            total_tokens = input_tokens + output_tokens
            avg_latency_ms = int(round(float(agg["avg_latency_ms"] or 0.0)))
            sessions_with_calls = int(agg["sessions_with_calls"] or 0)

            remaining_usd = round(max(0.0, cap - spent_usd), 6)
            usage_pct = round((spent_usd / cap) * 100.0, 2)

            if spent_usd >= cap or usage_pct >= 100.0:
                alert_status = "BLOCKED"
            elif usage_pct > 90.0:
                alert_status = "CRITICAL"
            elif usage_pct >= 70.0:
                alert_status = "WARNING"
            else:
                alert_status = "NORMAL"

            # Count clips generated in sessions that have API calls (fallback to all clips if needed)
            clips_row = self._conn.execute(
                """SELECT
                       COUNT(*) AS total_clips,
                       COALESCE(SUM(CASE WHEN state IN ('RENDERED_DRAFT', 'RENDERED_FINAL', 'DELIVERED')
                                              OR final_mp4_path IS NOT NULL
                                              OR draft_mp4_path IS NOT NULL
                                         THEN 1 ELSE 0 END), 0) AS rendered_clips
                   FROM clips
                   WHERE session_id IN (SELECT DISTINCT session_id FROM api_calls WHERE session_id IS NOT NULL)"""
            ).fetchone()
            billed_clips_total = int(clips_row["total_clips"] or 0)
            billed_clips_rendered = int(clips_row["rendered_clips"] or 0)

            if billed_clips_total == 0:
                all_clips_row = self._conn.execute(
                    """SELECT COUNT(*) AS total_clips,
                              COALESCE(SUM(CASE WHEN state IN ('RENDERED_DRAFT', 'RENDERED_FINAL', 'DELIVERED')
                                                     OR final_mp4_path IS NOT NULL
                                                THEN 1 ELSE 0 END), 0) AS rendered_clips
                       FROM clips"""
                ).fetchone()
                billed_clips_total = int(all_clips_row["total_clips"] or 0)
                billed_clips_rendered = int(all_clips_row["rendered_clips"] or 0)

            effective_clips = max(billed_clips_rendered, billed_clips_total)

            # Empirical vs reference rates (Deepgram Nova-3 $0.0043/min + keyterm add-on $0.0013/min = $0.336/h; Gemini Flash-Lite ~$0.0094/h)
            if audio_hours > 0.01 and spent_usd > 0:
                avg_cost_per_hour = round(spent_usd / audio_hours, 6)
                stt_cost_per_hour = round(stt_cost_usd / audio_hours, 6)
                llm_cost_per_hour = round(llm_cost_usd / audio_hours, 6)
                avg_tokens_per_hour = int(round(total_tokens / audio_hours))
            else:
                stt_cost_per_hour = 0.336
                llm_cost_per_hour = 0.0094
                avg_cost_per_hour = round(stt_cost_per_hour + llm_cost_per_hour, 6)
                avg_tokens_per_hour = 25200

            if effective_clips > 0 and spent_usd > 0:
                avg_cost_per_clip = round(spent_usd / effective_clips, 6)
            else:
                avg_cost_per_clip = round(avg_cost_per_hour / 3.0, 6)

            if audio_hours > 0.01 and effective_clips > 0:
                avg_clips_per_hour = round(effective_clips / audio_hours, 2)
            else:
                avg_clips_per_hour = 3.0

            est_remaining_hours = round(remaining_usd / max(0.0001, avg_cost_per_hour), 2)
            est_remaining_clips = int(remaining_usd / max(0.0001, avg_cost_per_clip))
            free_tier = self._compute_free_tier_comparison()

            return {
                "spent_usd": spent_usd,
                "stt_cost_usd": stt_cost_usd,
                "llm_cost_usd": llm_cost_usd,
                "max_budget_usd": cap,
                "remaining_usd": remaining_usd,
                "usage_pct": usage_pct,
                "alert_status": alert_status,
                "total_calls": total_calls,
                "stt_calls": stt_calls,
                "llm_calls": llm_calls,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "total_tokens": total_tokens,
                "audio_seconds_billed": audio_seconds,
                "audio_minutes_billed": audio_minutes,
                "audio_hours_billed": audio_hours,
                "avg_latency_ms": avg_latency_ms,
                "sessions_with_calls": sessions_with_calls,
                "total_clips_curated": billed_clips_total,
                "total_clips_rendered": effective_clips,
                "projections": {
                    "avg_cost_per_stream_hour_usd": avg_cost_per_hour,
                    "stt_cost_per_stream_hour_usd": stt_cost_per_hour,
                    "llm_cost_per_stream_hour_usd": llm_cost_per_hour,
                    "avg_cost_per_clip_usd": avg_cost_per_clip,
                    "avg_clips_per_stream_hour": avg_clips_per_hour,
                    "avg_tokens_per_stream_hour": avg_tokens_per_hour,
                    "estimated_remaining_stream_hours": est_remaining_hours,
                    "estimated_remaining_clips": est_remaining_clips,
                },
                "free_tier": free_tier,
            }

    def _compute_free_tier_comparison(self) -> Dict[str, Any]:
        """Compute Google AI Studio style rate-limit & free-tier quota comparison (RPM, TPM, RPD, and 24h trend)."""
        rows = self._conn.execute(
            """SELECT provider, model, kind, units_billed, input_tokens, output_tokens, cost_usd, created_at
               FROM api_calls
               ORDER BY created_at ASC"""
        ).fetchall()

        now_ts = time.time()
        max_call_ts = max((float(r["created_at"] or 0.0) for r in rows), default=now_ts)
        ref_ts = max(now_ts, max_call_ts)
        window_start = ref_ts - 86400.0  # Last 24h window

        # Pre-build 24 hourly buckets ending at ref_ts hour
        ref_hour_epoch = int(ref_ts // 3600) * 3600
        hour_epochs = [ref_hour_epoch - (23 - i) * 3600 for i in range(24)]

        specs = [
            {
                "id": "gemini-3.5-flash-lite",
                "provider": "gemini",
                "model": "gemini-3.5-flash-lite",
                "display_name": "Gemini 3.5 Flash Lite",
                "category": "Text-out models (Curación LLM)",
                "tier_name": "Google AI Studio · Free Tier",
                "rpm_limit": 15,
                "tpm_limit": 250000,
                "tpm_label": "TPM (Tokens entrada/min)",
                "tpm_unit": "tok",
                "rpd_limit": 500,
                "free_credit_usd": 0.0,
                "zero_cost_in_free_tier": True,
            },
            {
                "id": "nova-3",
                "provider": "deepgram",
                "model": "nova-3",
                "display_name": "Deepgram Nova-3",
                "category": "Speech-to-Text (Audio Opus)",
                "tier_name": "Deepgram · $200 Free Credit",
                "rpm_limit": 100,
                "tpm_limit": 36000,  # segundos audio / min capacidad ráfaga
                "tpm_label": "Audio/min (Segundos/min)",
                "tpm_unit": "seg",
                "rpd_limit": 5000,
                "free_credit_usd": 200.0,
                "zero_cost_in_free_tier": False,
            },
            {
                "id": "whisper-large-v3-turbo",
                "provider": "groq",
                "model": "whisper-large-v3-turbo",
                "display_name": "Groq Whisper v3 Turbo",
                "category": "Speech-to-Text (Respaldo)",
                "tier_name": "Groq Cloud · Free Tier",
                "rpm_limit": 20,
                "tpm_limit": 7200,
                "tpm_label": "Audio/hora (Segundos)",
                "tpm_unit": "seg",
                "rpd_limit": 2000,
                "free_credit_usd": 0.0,
                "zero_cost_in_free_tier": True,
            },
        ]

        models_out: List[Dict[str, Any]] = []
        for sp in specs:
            prov = sp["provider"]
            matching = [r for r in rows if str(r["provider"]).lower() == prov]
            recent_24h = [r for r in matching if float(r["created_at"] or 0.0) >= window_start]

            # Group by minute bucket for peak RPM and peak TPM
            min_rpm: Dict[int, int] = {}
            min_tpm: Dict[int, float] = {}
            for r in recent_24h:
                m_bucket = int(float(r["created_at"] or 0.0) // 60)
                min_rpm[m_bucket] = min_rpm.get(m_bucket, 0) + 1
                val = float(r["input_tokens"] or 0) if sp["tpm_unit"] == "tok" else float(r["units_billed"] or 0.0)
                min_tpm[m_bucket] = min_tpm.get(m_bucket, 0.0) + val

            peak_rpm = max(min_rpm.values(), default=0)
            peak_tpm = round(max(min_tpm.values(), default=0.0), 1)
            rpd_used = len(recent_24h)
            total_cost = round(sum(float(r["cost_usd"] or 0.0) for r in matching), 6)

            # Build 24h hourly trend series
            hourly_series: List[Dict[str, Any]] = []
            running_rpd = 0
            for h_ep in hour_epochs:
                h_end = h_ep + 3600
                h_rows = [r for r in recent_24h if h_ep <= float(r["created_at"] or 0.0) < h_end]
                h_min_rpm: Dict[int, int] = {}
                h_min_tpm: Dict[int, float] = {}
                for r in h_rows:
                    mb = int(float(r["created_at"] or 0.0) // 60)
                    h_min_rpm[mb] = h_min_rpm.get(mb, 0) + 1
                    v = float(r["input_tokens"] or 0) if sp["tpm_unit"] == "tok" else float(r["units_billed"] or 0.0)
                    h_min_tpm[mb] = h_min_tpm.get(mb, 0.0) + v
                running_rpd += len(h_rows)
                try:
                    lbl = datetime.fromtimestamp(h_ep).strftime("%H:%M")
                except Exception:
                    lbl = "00:00"
                hourly_series.append(
                    {
                        "hour_epoch": h_ep,
                        "label": lbl,
                        "peak_rpm": max(h_min_rpm.values(), default=0),
                        "peak_tpm": round(max(h_min_tpm.values(), default=0.0), 1),
                        "requests": len(h_rows),
                        "cumulative_rpd": running_rpd,
                    }
                )

            rpm_limit = int(sp["rpm_limit"])
            tpm_limit = float(sp["tpm_limit"])
            rpd_limit = int(sp["rpd_limit"])
            free_credit = float(sp["free_credit_usd"])

            within_free = (
                peak_rpm <= rpm_limit
                and peak_tpm <= tpm_limit
                and rpd_used <= rpd_limit
                and (free_credit == 0.0 or total_cost <= free_credit)
            )

            # Credit: estimated from local api_calls, or anchored to the real balance reported by the provider
            credit_source = "estimated"
            calibrated_at: Optional[float] = None
            used_since_calibration = 0.0
            credit_used = total_cost
            credit_remaining = max(0.0, free_credit - total_cost) if free_credit > 0 else 0.0
            calib = self.get_provider_balance(prov) if free_credit > 0 else None
            if calib:
                calibrated_at = float(calib["recorded_at"])
                free_credit = float(calib["credit_usd"] or free_credit)
                used_since_calibration = round(
                    sum(
                        float(r["cost_usd"] or 0.0)
                        for r in matching
                        if float(r["created_at"] or 0.0) > calibrated_at
                    ),
                    6,
                )
                credit_remaining = max(0.0, float(calib["balance_usd"]) - used_since_calibration)
                credit_used = max(0.0, free_credit - credit_remaining)
                credit_source = str(calib.get("source") or "manual")
                within_free = within_free and credit_remaining > 0

            models_out.append(
                {
                    "id": sp["id"],
                    "provider": prov,
                    "model": sp["model"],
                    "display_name": sp["display_name"],
                    "category": sp["category"],
                    "tier_name": sp["tier_name"],
                    "within_free_tier": within_free,
                    "zero_cost_in_free_tier": bool(sp["zero_cost_in_free_tier"]),
                    "rpm": {
                        "peak": peak_rpm,
                        "limit": rpm_limit,
                        "pct": round(min(100.0, (peak_rpm / max(1, rpm_limit)) * 100.0), 2),
                    },
                    "tpm": {
                        "peak": peak_tpm,
                        "limit": tpm_limit,
                        "pct": round(min(100.0, (peak_tpm / max(1.0, tpm_limit)) * 100.0), 2),
                        "label": sp["tpm_label"],
                        "unit": sp["tpm_unit"],
                    },
                    "rpd": {
                        "used": rpd_used,
                        "limit": rpd_limit,
                        "pct": round(min(100.0, (rpd_used / max(1, rpd_limit)) * 100.0), 2),
                    },
                    "credit": {
                        "limit_usd": free_credit,
                        "used_usd": round(credit_used, 6),
                        "remaining_usd": round(credit_remaining, 4) if free_credit > 0 else 0.0,
                        "pct": round(min(100.0, (credit_used / free_credit) * 100.0), 3) if free_credit > 0 else 0.0,
                        "estimated_used_usd": total_cost,
                        "source": credit_source,
                        "calibrated_at": calibrated_at,
                        "used_since_calibration_usd": used_since_calibration,
                    },
                    "timeline_24h": hourly_series,
                }
            )

        return {
            "window_hours": 24,
            "models": models_out,
        }

    def analytics_breakdown(self) -> Dict[str, Any]:
        """Group API usage by provider, model, calendar day, and session."""
        with self._lock:
            spent_total = max(0.0, self.total_spend_usd())

            prov_rows = self._conn.execute(
                """SELECT provider,
                          kind,
                          COUNT(*) AS calls,
                          COALESCE(SUM(CASE WHEN kind = 'stt' THEN units_billed ELSE 0.0 END), 0.0) AS audio_seconds,
                          COALESCE(SUM(input_tokens), 0) AS input_tokens,
                          COALESCE(SUM(output_tokens), 0) AS output_tokens,
                          COALESCE(SUM(cost_usd), 0.0) AS cost_usd,
                          COALESCE(AVG(latency_ms), 0.0) AS avg_latency_ms
                   FROM api_calls
                   GROUP BY provider, kind
                   ORDER BY cost_usd DESC, calls DESC"""
            ).fetchall()

            by_provider: List[Dict[str, Any]] = []
            for r in prov_rows:
                c_usd = round(float(r["cost_usd"] or 0.0), 6)
                a_sec = round(float(r["audio_seconds"] or 0.0), 3)
                in_tok = int(r["input_tokens"] or 0)
                out_tok = int(r["output_tokens"] or 0)
                by_provider.append(
                    {
                        "provider": str(r["provider"]),
                        "kind": str(r["kind"]),
                        "calls": int(r["calls"] or 0),
                        "audio_seconds": a_sec,
                        "audio_minutes": round(a_sec / 60.0, 2),
                        "audio_hours": round(a_sec / 3600.0, 4),
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "total_tokens": in_tok + out_tok,
                        "cost_usd": c_usd,
                        "share_pct": round((c_usd / spent_total) * 100.0, 2) if spent_total > 0 else 0.0,
                        "avg_latency_ms": int(round(float(r["avg_latency_ms"] or 0.0))),
                    }
                )

            model_rows = self._conn.execute(
                """SELECT provider,
                          model,
                          kind,
                          COUNT(*) AS calls,
                          COALESCE(SUM(units_billed), 0.0) AS units_billed,
                          COALESCE(SUM(CASE WHEN kind = 'stt' THEN units_billed ELSE 0.0 END), 0.0) AS audio_seconds,
                          COALESCE(SUM(input_tokens), 0) AS input_tokens,
                          COALESCE(SUM(output_tokens), 0) AS output_tokens,
                          COALESCE(SUM(cost_usd), 0.0) AS cost_usd,
                          COALESCE(AVG(latency_ms), 0.0) AS avg_latency_ms
                   FROM api_calls
                   GROUP BY provider, model, kind
                   ORDER BY cost_usd DESC, calls DESC"""
            ).fetchall()

            by_model: List[Dict[str, Any]] = []
            for r in model_rows:
                c_usd = round(float(r["cost_usd"] or 0.0), 6)
                a_sec = round(float(r["audio_seconds"] or 0.0), 3)
                in_tok = int(r["input_tokens"] or 0)
                out_tok = int(r["output_tokens"] or 0)
                by_model.append(
                    {
                        "provider": str(r["provider"]),
                        "model": str(r["model"]),
                        "kind": str(r["kind"]),
                        "calls": int(r["calls"] or 0),
                        "units_billed": round(float(r["units_billed"] or 0.0), 3),
                        "audio_seconds": a_sec,
                        "audio_minutes": round(a_sec / 60.0, 2),
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "total_tokens": in_tok + out_tok,
                        "cost_usd": c_usd,
                        "share_pct": round((c_usd / spent_total) * 100.0, 2) if spent_total > 0 else 0.0,
                        "avg_latency_ms": int(round(float(r["avg_latency_ms"] or 0.0))),
                    }
                )

            day_rows = self._conn.execute(
                """SELECT date(created_at, 'unixepoch', 'localtime') AS day_date,
                          COUNT(*) AS calls,
                          COALESCE(SUM(CASE WHEN kind = 'stt' THEN 1 ELSE 0 END), 0) AS stt_calls,
                          COALESCE(SUM(CASE WHEN kind = 'llm' THEN 1 ELSE 0 END), 0) AS llm_calls,
                          COALESCE(SUM(cost_usd), 0.0) AS cost_usd,
                          COALESCE(SUM(CASE WHEN kind = 'stt' THEN cost_usd ELSE 0.0 END), 0.0) AS stt_cost_usd,
                          COALESCE(SUM(CASE WHEN kind = 'llm' THEN cost_usd ELSE 0.0 END), 0.0) AS llm_cost_usd,
                          COALESCE(SUM(CASE WHEN kind = 'stt' THEN units_billed ELSE 0.0 END), 0.0) AS audio_seconds,
                          COALESCE(SUM(input_tokens), 0) AS input_tokens,
                          COALESCE(SUM(output_tokens), 0) AS output_tokens
                   FROM api_calls
                   GROUP BY day_date
                   ORDER BY day_date ASC"""
            ).fetchall()

            by_day: List[Dict[str, Any]] = []
            for r in day_rows:
                a_sec = round(float(r["audio_seconds"] or 0.0), 3)
                in_tok = int(r["input_tokens"] or 0)
                out_tok = int(r["output_tokens"] or 0)
                by_day.append(
                    {
                        "date": str(r["day_date"] or "unknown"),
                        "calls": int(r["calls"] or 0),
                        "stt_calls": int(r["stt_calls"] or 0),
                        "llm_calls": int(r["llm_calls"] or 0),
                        "cost_usd": round(float(r["cost_usd"] or 0.0), 6),
                        "stt_cost_usd": round(float(r["stt_cost_usd"] or 0.0), 6),
                        "llm_cost_usd": round(float(r["llm_cost_usd"] or 0.0), 6),
                        "audio_minutes": round(a_sec / 60.0, 2),
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "total_tokens": in_tok + out_tok,
                    }
                )

            sess_rows = self._conn.execute(
                """SELECT COALESCE(a.session_id, 'unassigned') AS session_id,
                          COALESCE(s.title, a.session_id, 'Sesión sin vincular') AS session_title,
                          COALESCE(s.state, 'UNKNOWN') AS state,
                          COUNT(*) AS calls,
                          COALESCE(SUM(CASE WHEN a.kind = 'stt' THEN 1 ELSE 0 END), 0) AS stt_calls,
                          COALESCE(SUM(CASE WHEN a.kind = 'llm' THEN 1 ELSE 0 END), 0) AS llm_calls,
                          COALESCE(SUM(a.cost_usd), 0.0) AS cost_usd,
                          COALESCE(SUM(CASE WHEN a.kind = 'stt' THEN a.cost_usd ELSE 0.0 END), 0.0) AS stt_cost_usd,
                          COALESCE(SUM(CASE WHEN a.kind = 'llm' THEN a.cost_usd ELSE 0.0 END), 0.0) AS llm_cost_usd,
                          COALESCE(SUM(CASE WHEN a.kind = 'stt' THEN a.units_billed ELSE 0.0 END), 0.0) AS audio_seconds,
                          COALESCE(SUM(a.input_tokens), 0) AS input_tokens,
                          COALESCE(SUM(a.output_tokens), 0) AS output_tokens,
                          MIN(a.created_at) AS first_call_at,
                          MAX(a.created_at) AS last_call_at,
                          (SELECT COUNT(*) FROM clips c WHERE c.session_id = a.session_id) AS clips_count
                   FROM api_calls a
                   LEFT JOIN sessions s ON s.id = a.session_id
                   GROUP BY a.session_id
                   ORDER BY last_call_at DESC"""
            ).fetchall()

            by_session: List[Dict[str, Any]] = []
            for r in sess_rows:
                c_usd = round(float(r["cost_usd"] or 0.0), 6)
                a_sec = round(float(r["audio_seconds"] or 0.0), 3)
                in_tok = int(r["input_tokens"] or 0)
                out_tok = int(r["output_tokens"] or 0)
                c_cnt = int(r["clips_count"] or 0)
                by_session.append(
                    {
                        "session_id": str(r["session_id"]),
                        "session_title": str(r["session_title"]),
                        "state": str(r["state"]),
                        "calls": int(r["calls"] or 0),
                        "stt_calls": int(r["stt_calls"] or 0),
                        "llm_calls": int(r["llm_calls"] or 0),
                        "cost_usd": c_usd,
                        "stt_cost_usd": round(float(r["stt_cost_usd"] or 0.0), 6),
                        "llm_cost_usd": round(float(r["llm_cost_usd"] or 0.0), 6),
                        "audio_seconds": a_sec,
                        "audio_minutes": round(a_sec / 60.0, 2),
                        "audio_hours": round(a_sec / 3600.0, 4),
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "total_tokens": in_tok + out_tok,
                        "clips_count": c_cnt,
                        "cost_per_clip_usd": round(c_usd / c_cnt, 6) if c_cnt > 0 else 0.0,
                        "first_call_at": float(r["first_call_at"] or 0.0),
                        "last_call_at": float(r["last_call_at"] or 0.0),
                    }
                )

            return {
                "spent_usd": spent_total,
                "by_provider": by_provider,
                "by_model": by_model,
                "by_day": by_day,
                "by_session": by_session,
            }

    def analytics_logs(
        self,
        provider: Optional[str] = None,
        kind: Optional[str] = None,
        session_id: Optional[str] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> Dict[str, Any]:
        """Return paginated individual API call logs with filters."""
        clauses: List[str] = []
        params: List[Any] = []

        if provider and provider.strip().lower() not in {"all", "todos", ""}:
            p = provider.strip().lower()
            if p in {"openai", "openai_compat"}:
                clauses.append("LOWER(a.provider) IN ('openai', 'openai_compat')")
            else:
                clauses.append("LOWER(a.provider) = ?")
                params.append(p)

        if kind and kind.strip().lower() not in {"all", "todos", ""}:
            clauses.append("LOWER(a.kind) = ?")
            params.append(kind.strip().lower())

        if session_id and session_id.strip().lower() not in {"all", "todas", ""}:
            clauses.append("a.session_id = ?")
            params.append(session_id.strip())

        ts_from = self._parse_date_bound(date_from, end_of_day=False)
        if ts_from is not None:
            clauses.append("a.created_at >= ?")
            params.append(ts_from)

        ts_to = self._parse_date_bound(date_to, end_of_day=True)
        if ts_to is not None:
            clauses.append("a.created_at <= ?")
            params.append(ts_to)

        if search and search.strip():
            q = f"%{search.strip().lower()}%"
            clauses.append(
                "(LOWER(a.id) LIKE ? OR LOWER(a.provider) LIKE ? OR LOWER(a.model) LIKE ? "
                "OR LOWER(COALESCE(a.session_id, '')) LIKE ? OR LOWER(COALESCE(s.title, '')) LIKE ? "
                "OR LOWER(a.task_hash) LIKE ?)"
            )
            params.extend([q, q, q, q, q, q])

        where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

        with self._lock:
            count_row = self._conn.execute(
                f"""SELECT COUNT(*) AS cnt,
                           COALESCE(SUM(a.cost_usd), 0.0) AS filtered_cost_usd
                    FROM api_calls a
                    LEFT JOIN sessions s ON s.id = a.session_id
                    {where_sql}""",
                params,
            ).fetchone()
            total = int(count_row["cnt"] or 0)
            filtered_cost_usd = round(float(count_row["filtered_cost_usd"] or 0.0), 6)

            rows = self._conn.execute(
                f"""SELECT a.*,
                           COALESCE(s.title, '') AS session_title
                    FROM api_calls a
                    LEFT JOIN sessions s ON s.id = a.session_id
                    {where_sql}
                    ORDER BY a.created_at DESC, a.id DESC
                    LIMIT ? OFFSET ?""",
                [*params, max(1, int(limit)), max(0, int(offset))],
            ).fetchall()

            items: List[Dict[str, Any]] = []
            for r in rows:
                k = str(r["kind"])
                u_billed = round(float(r["units_billed"] or 0.0), 3)
                a_sec = u_billed if k == "stt" else 0.0
                in_tok = int(r["input_tokens"] or 0)
                out_tok = int(r["output_tokens"] or 0)
                ts = float(r["created_at"] or 0.0)
                try:
                    iso_str = datetime.fromtimestamp(ts).isoformat(timespec="seconds")
                except Exception:
                    iso_str = ""
                items.append(
                    {
                        "id": str(r["id"]),
                        "session_id": r["session_id"],
                        "session_title": str(r["session_title"] or ""),
                        "task_hash": str(r["task_hash"]),
                        "provider": str(r["provider"]),
                        "model": str(r["model"]),
                        "kind": k,
                        "units_billed": u_billed,
                        "audio_seconds": a_sec,
                        "audio_minutes": round(a_sec / 60.0, 2) if k == "stt" else 0.0,
                        "input_tokens": in_tok,
                        "output_tokens": out_tok,
                        "total_tokens": in_tok + out_tok,
                        "cost_usd": round(float(r["cost_usd"] or 0.0), 6),
                        "latency_ms": int(r["latency_ms"] or 0),
                        "created_at": ts,
                        "created_iso": iso_str,
                    }
                )

            return {
                "total": total,
                "limit": int(limit),
                "offset": int(offset),
                "filtered_cost_usd": filtered_cost_usd,
                "items": items,
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
