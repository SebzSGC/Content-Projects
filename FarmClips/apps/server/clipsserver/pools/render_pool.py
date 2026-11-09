"""Priority Render Pool: 2-3 slots for NVENC or (cores / 4) for libx264, behind RenderBackend."""

from __future__ import annotations

import asyncio
import itertools
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, List, Optional

from clipscore.domain import SyncResult
from clipseditplan import EditPlan
from clipsrender import LocalFfmpegRenderBackend, RenderBackend, RenderQuality
from clipsstyles import StylePreset


@dataclass(order=True)
class _QueuedRender:
    sort_key: float
    seq: int
    execute: Callable[[], asyncio.Future] = field(compare=False)


class RenderPool:
    """Priority render queue: interactive editor renders (priority=1000) bypass automatic batch renders."""

    def __init__(
        self,
        backend: Optional[RenderBackend] = None,
        use_nvenc: bool = True,
        nvenc_slots: int = 2,
        cache_dir: Optional[Path] = None,
        use_videotoolbox: bool = True,
    ) -> None:
        cpu_slots = max(1, (os.cpu_count() or 4) // 4)
        self.slots = max(1, min(3, nvenc_slots)) if use_nvenc else cpu_slots
        self.backend: RenderBackend = backend or LocalFfmpegRenderBackend(
            use_nvenc=use_nvenc, cache_dir=cache_dir, use_videotoolbox=use_videotoolbox
        )
        self._queue: asyncio.PriorityQueue[_QueuedRender] = asyncio.PriorityQueue()
        self._counter = itertools.count()
        self._workers: List[asyncio.Task] = []
        self._started = False

    def _ensure_workers(self) -> None:
        if self._started:
            return
        self._started = True
        for i in range(self.slots):
            self._workers.append(asyncio.create_task(self._worker_loop(), name=f"render-slot-{i}"))

    async def _worker_loop(self) -> None:
        while True:
            item = await self._queue.get()
            try:
                await item.execute()
            finally:
                self._queue.task_done()

    async def submit(
        self,
        plan: EditPlan,
        preset: StylePreset,
        gameplay_path: Path,
        camera_path: Path,
        sync: SyncResult,
        out_dir: Path,
        quality: RenderQuality = "final",
        priority: float = 50.0,
        clean_game_audio_stream: Optional[int] = None,
        on_progress: Optional[Callable[[float, str], None]] = None,
    ) -> Path:
        self._ensure_workers()
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Path] = loop.create_future()

        async def _run() -> None:
            if fut.cancelled():
                return
            try:
                mp4 = await self.backend.render_plan(
                    plan=plan,
                    preset=preset,
                    gameplay_path=gameplay_path,
                    camera_path=camera_path,
                    sync=sync,
                    out_dir=out_dir,
                    quality=quality,
                    clean_game_audio_stream=clean_game_audio_stream,
                    on_progress=on_progress,
                )
                if not fut.done():
                    fut.set_result(mp4)
            except Exception as exc:
                if not fut.done():
                    fut.set_exception(exc)

        await self._queue.put(_QueuedRender(sort_key=-float(priority), seq=next(self._counter), execute=_run))  # type: ignore[arg-type]
        return await fut

    async def shutdown(self) -> None:
        for w in self._workers:
            w.cancel()
        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers.clear()
        self._started = False
