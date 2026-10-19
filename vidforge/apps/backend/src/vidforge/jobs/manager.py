"""Asynchronous JobManager with resource pools, cancellation and SSE EventBroker."""

from __future__ import annotations

import asyncio
import uuid
from typing import Any, Callable, Coroutine

from vidforge.infra.db import db, utc_now_iso


class CancelToken:
    def __init__(self) -> None:
        self._cancelled = False

    def cancel(self) -> None:
        self._cancelled = True

    def is_cancelled(self) -> bool:
        return self._cancelled


class EventBroker:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue] = set()
        self._seq = 0

    def publish(self, event_type: str, payload: dict[str, Any]) -> None:
        self._seq += 1
        msg = {
            "seq": self._seq,
            "ts": utc_now_iso(),
            "type": event_type,
            **payload,
        }
        for q in list(self._subscribers):
            try:
                q.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    async def subscribe(self):
        q: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._subscribers.add(q)
        try:
            while True:
                item = await q.get()
                yield item
        finally:
            self._subscribers.discard(q)


class JobManager:
    def __init__(self) -> None:
        self.broker = EventBroker()
        self._semaphores: dict[str, asyncio.Semaphore] = {}
        self._tokens: dict[str, CancelToken] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    def _get_sem(self, pool: str) -> asyncio.Semaphore:
        if pool not in self._semaphores:
            limits = {"gpu": 1, "cpu": 3, "net": 4, "io": 2}
            self._semaphores[pool] = asyncio.Semaphore(limits.get(pool, 2))
        return self._semaphores[pool]

    def submit(
        self,
        job_type: str,
        runner: Callable[[str, CancelToken, Callable[[float, str], None]], Coroutine[Any, Any, dict[str, Any]]],
        project_id: str | None = None,
        params: dict[str, Any] | None = None,
        pool: str = "cpu",
    ) -> dict[str, Any]:
        job_id = str(uuid.uuid4())
        job_doc = {
            "id": job_id,
            "project_id": project_id,
            "type": job_type,
            "state": "queued",
            "progress": 0.0,
            "stage": "En cola",
            "params": params or {},
            "result": None,
            "error": None,
            "created_at": utc_now_iso(),
            "started_at": None,
            "finished_at": None,
        }
        db.upsert_job(job_doc)
        token = CancelToken()
        self._tokens[job_id] = token
        self.broker.publish("job.queued", {"job_id": job_id, "job": job_doc})

        loop = asyncio.get_event_loop()
        task = loop.create_task(self._execute(job_doc, runner, token, pool))
        self._tasks[job_id] = task
        return job_doc

    async def _execute(
        self,
        job_doc: dict[str, Any],
        runner: Callable[[str, CancelToken, Callable[[float, str], None]], Coroutine[Any, Any, dict[str, Any]]],
        token: CancelToken,
        pool: str,
    ) -> None:
        job_id = job_doc["id"]
        sem = self._get_sem(pool)

        def report_progress(progress: float, stage: str = "") -> None:
            job_doc["progress"] = round(float(progress), 3)
            if stage:
                job_doc["stage"] = stage
            db.upsert_job(job_doc)
            self.broker.publish(
                "job.progress",
                {
                    "job_id": job_id,
                    "project_id": job_doc.get("project_id"),
                    "state": job_doc["state"],
                    "progress": job_doc["progress"],
                    "stage": job_doc["stage"],
                },
            )

        async with sem:
            if token.is_cancelled():
                job_doc["state"] = "cancelled"
                job_doc["finished_at"] = utc_now_iso()
                db.upsert_job(job_doc)
                self.broker.publish("job.cancelled", {"job_id": job_id, "job": job_doc})
                return

            job_doc["state"] = "running"
            job_doc["started_at"] = utc_now_iso()
            job_doc["stage"] = "Iniciando"
            db.upsert_job(job_doc)
            self.broker.publish("job.running", {"job_id": job_id, "job": job_doc})

            try:
                res = await runner(job_id, token, report_progress)
                if token.is_cancelled():
                    job_doc["state"] = "cancelled"
                    job_doc["finished_at"] = utc_now_iso()
                    db.upsert_job(job_doc)
                    self.broker.publish("job.cancelled", {"job_id": job_id, "job": job_doc})
                else:
                    job_doc["state"] = "succeeded"
                    job_doc["progress"] = 1.0
                    job_doc["stage"] = "Completado"
                    job_doc["result"] = res
                    job_doc["finished_at"] = utc_now_iso()
                    db.upsert_job(job_doc)
                    self.broker.publish("job.succeeded", {"job_id": job_id, "job": job_doc})
            except Exception as exc:
                if token.is_cancelled():
                    job_doc["state"] = "cancelled"
                else:
                    job_doc["state"] = "failed"
                    job_doc["error"] = {"code": "JOB_ERROR", "message": str(exc), "retryable": True}
                job_doc["finished_at"] = utc_now_iso()
                db.upsert_job(job_doc)
                self.broker.publish("job.failed", {"job_id": job_id, "job": job_doc})

    def cancel(self, job_id: str) -> dict[str, Any] | None:
        token = self._tokens.get(job_id)
        if token:
            token.cancel()
        job_doc = db.get_job(job_id)
        if job_doc and job_doc["state"] in ("queued", "running"):
            job_doc["state"] = "cancelled"
            job_doc["finished_at"] = utc_now_iso()
            db.upsert_job(job_doc)
            self.broker.publish("job.cancelled", {"job_id": job_id, "job": job_doc})
        return job_doc


job_manager = JobManager()
