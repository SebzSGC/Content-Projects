"""CPU Process Pool (`núcleos - 1` processes) with top-level Windows-spawn-safe worker functions."""

from __future__ import annotations

import asyncio
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Sequence, TypeVar

from clipscore.directors import build_editplan
from clipscore.domain import (
    CuratedClip,
    FaceTrajectory,
    PreparedMedia,
    SignalSeries,
    SilenceSpan,
    SyncResult,
    Utterance,
)
from clipscore.signals import build_signal_series, compute_mic_envelope_100hz
from clipseditplan import EditPlan
from clipsmedia.sync import prepare_session_media
from clipsstyles import load_preset
from clipstracking import track_clip_face

T = TypeVar("T")


# --- Top-level picklable functions for Windows `spawn` ProcessPoolExecutor ---


def worker_prepare_media(
    session_id: str,
    gameplay_path: str,
    camera_path: str,
    work_dir_str: str,
    manual_sync_dict: Optional[Dict[str, Any]],
    target_chunk_sec: float,
) -> Dict[str, Any]:
    ms = SyncResult.model_validate(manual_sync_dict) if manual_sync_dict else None
    prep = prepare_session_media(
        session_id=session_id,
        gameplay_path=gameplay_path,
        camera_path=camera_path,
        work_dir=Path(work_dir_str),
        manual_sync=ms,
        target_chunk_sec=target_chunk_sec,
    )
    return prep.model_dump(mode="json")


def worker_compute_signals(
    duration: float,
    camera_wav16k: str,
    gameplay_wav16k: str,
    sync_shift_sec: float,
    sync_scale: float,
    gameplay_video_path: Optional[str],
    enable_motion: bool,
    out_parquet_str: str,
) -> str:
    sig = build_signal_series(
        duration=duration,
        camera_wav16k=camera_wav16k,
        gameplay_wav16k=gameplay_wav16k,
        sync_shift_sec=sync_shift_sec,
        sync_scale=sync_scale,
        gameplay_video_path=gameplay_video_path,
        enable_motion=enable_motion,
    )
    out = Path(out_parquet_str)
    sig.to_parquet(out)
    return str(out.resolve())


def worker_track_face(
    camera_path: str,
    master_start: float,
    master_end: float,
    sync_dict: Dict[str, Any],
    out_parquet_str: str,
) -> str:
    sync = SyncResult.model_validate(sync_dict)
    out = Path(out_parquet_str)
    track_clip_face(
        camera_path=camera_path,
        master_start=master_start,
        master_end=master_end,
        sync=sync,
        out_parquet=out,
        fps=15.0,
        pipe_width=640,
    )
    return str(out.resolve())


def worker_build_editplan(
    session_id: str,
    clip_dict: Dict[str, Any],
    utterances_list: Sequence[Dict[str, Any]],
    signals_parquet_str: Optional[str],
    face_parquet_str: Optional[str],
    style_preset_id: str,
    speech_silences_list: Sequence[Dict[str, Any]],
    camera_wav16k: Optional[str],
    sync_dict: Dict[str, Any],
    source_fps: float,
    out_json_str: str,
) -> str:
    clip = CuratedClip.model_validate(clip_dict)
    utts = [Utterance.model_validate(u) for u in utterances_list]
    signals = SignalSeries.from_parquet(Path(signals_parquet_str)) if signals_parquet_str and Path(signals_parquet_str).is_file() else None
    face = FaceTrajectory.from_parquet(Path(face_parquet_str)) if face_parquet_str and Path(face_parquet_str).is_file() else None
    preset = load_preset(style_preset_id)
    silences = [SilenceSpan.model_validate(s) for s in speech_silences_list]
    sync = SyncResult.model_validate(sync_dict)

    mic_attack = None
    mic_env_start_master = clip.start
    if camera_wav16k and Path(camera_wav16k).is_file():
        cam_a = max(0.0, sync.camera_time(clip.start))
        cam_b = max(cam_a + 0.5, sync.camera_time(clip.end))
        raw_attack, env_cam_s0 = compute_mic_envelope_100hz(camera_wav16k, cam_a, cam_b)
        mic_attack = raw_attack
        mic_env_start_master = sync.master_time(env_cam_s0)

    plan: EditPlan = build_editplan(
        session_id=session_id,
        clip=clip,
        utterances=utts,
        signals=signals,
        face=face,
        preset=preset,
        speech_silences=silences,
        mic_attack_100hz=mic_attack,
        mic_attack_start_sec=mic_env_start_master,
        source_fps=source_fps,
    )
    out = Path(out_json_str)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(plan.model_dump_json(indent=2, exclude_none=True) + "\n", encoding="utf-8")
    return str(out.resolve())


class CpuPool:
    """ProcessPoolExecutor wrapper (`max_workers = cpu_count - 1`) with graceful fallback in constrained test runners."""

    def __init__(self, max_workers: int = 2, use_processes: bool = True) -> None:
        self.max_workers = max(1, max_workers)
        self.use_processes = use_processes
        self._executor: Optional[ProcessPoolExecutor] = (
            ProcessPoolExecutor(max_workers=self.max_workers) if use_processes else None
        )
        self._sem = asyncio.Semaphore(self.max_workers)

    async def run(self, fn: Callable[..., T], *args: Any) -> T:
        async with self._sem:
            if self._executor is not None:
                loop = asyncio.get_running_loop()
                return await loop.run_in_executor(self._executor, fn, *args)
            return await asyncio.to_thread(fn, *args)

    def shutdown(self) -> None:
        if self._executor is not None:
            self._executor.shutdown(wait=False, cancel_futures=True)
            self._executor = None
