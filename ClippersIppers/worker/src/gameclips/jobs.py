"""Background job queue.

Analysis is GPU-heavy and runs for minutes to hours, so it never happens inside
an HTTP request. Jobs run one at a time on a worker thread; their status is
persisted so the UI can poll it and a restart doesn't lose finished results.
"""

from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from .config import get_settings
from .domain import new_id
from .storage import read_json, write_json

ProgressFn = Callable[[str, float, str], None]


@dataclass
class Job:
    id: str
    kind: str  # analyze | render
    session_id: str
    status: str = "queued"  # queued | running | done | error
    stage: str = ""
    progress: float = 0.0
    message: str = ""
    error: Optional[str] = None
    result: Optional[Dict[str, Any]] = None
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)


class JobManager:
    def __init__(self) -> None:
        self._dir = get_settings().data_dir / "jobs"
        self._dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._jobs: Dict[str, Job] = {}
        self._pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="gameclips-job")
        for p in self._dir.glob("*.json"):
            job = Job(**read_json(p))
            if job.status in {"queued", "running"}:
                job.status, job.error = "error", "Interrumpido por reinicio del worker"
            self._jobs[job.id] = job

    def _persist(self, job: Job) -> None:
        job.updated_at = time.time()
        write_json(self._dir / f"{job.id}.json", job)

    def get(self, job_id: str) -> Optional[Job]:
        return self._jobs.get(job_id)

    def list(self, session_id: Optional[str] = None) -> List[Job]:
        jobs = [j for j in self._jobs.values() if session_id is None or j.session_id == session_id]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)

    def active_for(self, session_id: str, kind: str) -> Optional[Job]:
        return next(
            (j for j in self.list(session_id) if j.kind == kind and j.status in {"queued", "running"}),
            None,
        )

    def submit(self, kind: str, session_id: str, fn: Callable[[ProgressFn], Optional[Dict[str, Any]]]) -> Job:
        job = Job(id=new_id("job"), kind=kind, session_id=session_id)
        with self._lock:
            self._jobs[job.id] = job
            self._persist(job)

        def report(stage: str, progress: float, message: str = "") -> None:
            with self._lock:
                job.stage, job.progress, job.message = stage, max(0.0, min(1.0, progress)), message
                self._persist(job)

        def runner() -> None:
            with self._lock:
                job.status = "running"
                self._persist(job)
            try:
                result = fn(report)
                with self._lock:
                    job.status, job.progress, job.result = "done", 1.0, result
                    self._persist(job)
            except Exception as exc:  # noqa: BLE001 - surface any failure to the UI
                with self._lock:
                    job.status = "error"
                    job.error = f"{type(exc).__name__}: {exc}"
                    job.message = traceback.format_exc(limit=6)
                    self._persist(job)

        self._pool.submit(runner)
        return job


_manager: Optional[JobManager] = None


def get_job_manager() -> JobManager:
    global _manager
    if _manager is None:
        _manager = JobManager()
    return _manager
