"""Windows process management with Job Objects and CREATE_NO_WINDOW."""

from __future__ import annotations

import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

CREATE_NO_WINDOW = 0x08000000 if sys.platform == "win32" else 0
CREATE_NEW_PROCESS_GROUP = 0x00000200 if sys.platform == "win32" else 0

_JOB_HANDLE = None
_JOB_LOCK = threading.Lock()


def _ensure_job_object():
    global _JOB_HANDLE
    if sys.platform != "win32":
        return None
    with _JOB_LOCK:
        if _JOB_HANDLE is not None:
            return _JOB_HANDLE
        try:
            import win32job
            hjob = win32job.CreateJobObject(None, "")
            info = win32job.QueryInformationJobObject(hjob, win32job.JobObjectExtendedLimitInformation)
            info["BasicLimitInformation"]["LimitFlags"] |= win32job.JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
            win32job.SetInformationJobObject(hjob, win32job.JobObjectExtendedLimitInformation, info)
            _JOB_HANDLE = hjob
        except Exception:
            _JOB_HANDLE = None
        return _JOB_HANDLE


def assign_to_job_object(pid: int) -> bool:
    if sys.platform != "win32":
        return False
    hjob = _ensure_job_object()
    if not hjob:
        return False
    try:
        import win32api
        import win32con
        import win32job
        hproc = win32api.OpenProcess(win32con.PROCESS_SET_QUOTA | win32con.PROCESS_TERMINATE, False, pid)
        win32job.AssignProcessToJobObject(hjob, hproc)
        win32api.CloseHandle(hproc)
        return True
    except Exception:
        return False


def spawn_hidden(
    args: list[str],
    cwd: str | Path | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.Popen:
    flags = CREATE_NO_WINDOW | CREATE_NEW_PROCESS_GROUP
    proc = subprocess.Popen(
        [str(a) for a in args],
        cwd=str(cwd) if cwd else None,
        env=env,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        creationflags=flags,
        encoding="utf-8",
        errors="replace",
    )
    assign_to_job_object(proc.pid)
    return proc


def run_hidden(
    args: list[str],
    cwd: str | Path | None = None,
    timeout: float = 300.0,
) -> subprocess.CompletedProcess:
    flags = CREATE_NO_WINDOW
    return subprocess.run(
        [str(a) for a in args],
        cwd=str(cwd) if cwd else None,
        capture_output=True,
        creationflags=flags,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        check=False,
    )


def run_ffmpeg_with_progress(
    ffmpeg_path: str,
    args: list[str],
    total_duration_us: int,
    on_progress: Callable[[float], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
    cwd: str | Path | None = None,
) -> None:
    full_args = [ffmpeg_path, "-hide_banner", "-nostats", "-progress", "pipe:1", *args]
    proc = spawn_hidden(full_args, cwd=cwd)
    stderr_chunks: list[str] = []

    def _drain_stderr():
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_chunks.append(line)

    t = threading.Thread(target=_drain_stderr, daemon=True)
    t.start()

    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            if cancel_check and cancel_check():
                proc.terminate()
                raise RuntimeError("Render cancelled by user")
            line = line.strip()
            if line.startswith("out_time_us="):
                val_str = line.split("=", 1)[1].strip()
                if val_str.isdigit() and total_duration_us > 0:
                    cur_us = int(val_str)
                    ratio = min(0.99, max(0.0, cur_us / total_duration_us))
                    if on_progress:
                        on_progress(ratio)
            elif line == "progress=end":
                if on_progress:
                    on_progress(1.0)
        rc = proc.wait()
        t.join(timeout=2.0)
        if rc != 0:
            err_tail = "".join(stderr_chunks[-25:])
            raise RuntimeError(f"FFmpeg failed (code {rc}): {err_tail}")
    finally:
        if proc.poll() is None:
            proc.kill()
