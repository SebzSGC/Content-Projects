"""TTL storage cleanup for bulky intermediate session files (`WAV`, `Opus`, Drive `inputs/`) while preserving $0 re-run caches."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Dict, List

from .db import OrchestratorDB

TEMP_MEDIA_SUFFIXES = {".wav", ".opus", ".part"}


def _dir_bytes(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for p in path.rglob("*"):
        if p.is_file():
            try:
                total += p.stat().st_size
            except OSError:
                pass
    return total


def _session_temp_files(sdir: Path, include_inputs: bool = False) -> List[Path]:
    candidates: List[Path] = []
    media_dir = sdir / "media"
    if media_dir.is_dir():
        for p in media_dir.rglob("*"):
            if p.is_file() and p.suffix.lower() in TEMP_MEDIA_SUFFIXES:
                candidates.append(p)
    if include_inputs:
        inputs_dir = sdir / "inputs"
        if inputs_dir.is_dir():
            for p in inputs_dir.rglob("*"):
                if p.is_file():
                    candidates.append(p)
    return candidates


def compute_storage_stats(
    data_dir: Path,
    db: OrchestratorDB,
    temp_ttl_days: float = 7.0,
) -> Dict[str, Any]:
    """Compute disk usage breakdown separating purgeable temp audio/video from preserved $0-cache & renders."""
    now = time.time()
    cutoff = now - max(0.0, temp_ttl_days) * 86400.0
    sessions_root = data_dir / "sessions"

    temp_media_bytes = _dir_bytes(data_dir / "uploads")
    renders_bytes = _dir_bytes(data_dir / "render_cache")
    preserved_cache_bytes = _dir_bytes(data_dir / "raw_api") + _dir_bytes(data_dir / "artifacts")
    eligible_bytes = 0
    eligible_sessions = 0

    for row in db.list_sessions():
        sid = row["id"]
        sdir = sessions_root / sid
        if not sdir.is_dir():
            continue
        t_files = _session_temp_files(sdir, include_inputs=False)
        t_bytes = sum((f.stat().st_size for f in t_files if f.is_file()), 0)
        temp_media_bytes += t_bytes + _dir_bytes(sdir / "inputs")
        renders_bytes += _dir_bytes(sdir / "renders")

        for keep_p in (sdir / "utterances.json", sdir / "signals.parquet"):
            if keep_p.is_file():
                preserved_cache_bytes += keep_p.stat().st_size
        preserved_cache_bytes += _dir_bytes(sdir / "clips")

        if row.get("state") in ("DELIVERED", "CANCELLED") and float(row.get("updated_at") or now) <= cutoff and t_bytes > 0:
            eligible_bytes += t_bytes
            eligible_sessions += 1

    return {
        "temp_ttl_days": temp_ttl_days,
        "temp_media_bytes": temp_media_bytes,
        "renders_bytes": renders_bytes,
        "preserved_cache_bytes": preserved_cache_bytes,
        "eligible_cleanup_bytes": eligible_bytes,
        "eligible_sessions_count": eligible_sessions,
    }


def cleanup_temp_media(
    data_dir: Path,
    db: OrchestratorDB,
    ttl_days: float = 7.0,
    include_inputs: bool = False,
) -> Dict[str, Any]:
    """Purge intermediate WAV/Opus files on DELIVERED/CANCELLED sessions older than `ttl_days`."""
    now = time.time()
    cutoff = now - max(0.0, ttl_days) * 86400.0
    sessions_root = data_dir / "sessions"

    purged_files = 0
    freed_bytes = 0
    cleaned_sessions: List[str] = []

    for row in db.list_sessions():
        if row.get("state") not in ("DELIVERED", "CANCELLED"):
            continue
        if float(row.get("updated_at") or now) > cutoff:
            continue
        sid = row["id"]
        sdir = sessions_root / sid
        if not sdir.is_dir():
            continue

        targets = _session_temp_files(sdir, include_inputs=include_inputs)
        session_freed = 0
        for fp in targets:
            try:
                sz = fp.stat().st_size
                fp.unlink(missing_ok=True)
                purged_files += 1
                freed_bytes += sz
                session_freed += sz
            except OSError:
                continue

        # Remove empty opus_chunks directory if drained
        oc = sdir / "media" / "opus_chunks"
        if oc.is_dir() and not any(oc.iterdir()):
            try:
                oc.rmdir()
            except OSError:
                pass

        if session_freed > 0:
            cleaned_sessions.append(sid)

    return {
        "ttl_days": ttl_days,
        "purged_files": purged_files,
        "freed_bytes": freed_bytes,
        "cleaned_sessions": cleaned_sessions,
    }
