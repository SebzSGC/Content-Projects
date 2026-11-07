"""Per-clip CPU face tracking: streams 15 fps / 640 px frames from FFmpeg pipe into MediaPipe Face Detector."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import List, Optional

import numpy as np
from clipscore.domain import FaceTrajectory, SyncResult
from clipsmedia.ffmpeg import probe, resolve_binary

DEFAULT_MODEL_PATH = Path(__file__).resolve().parent / "models" / "blaze_face_short_range.tflite"
MODEL_DOWNLOAD_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_short_range/float16/1/blaze_face_short_range.tflite"
)


def _even(v: float) -> int:
    i = max(2, int(round(v)))
    return i - (i % 2)


def ensure_face_detector_model(custom_path: Optional[Path] = None) -> Path:
    env_p = os.environ.get("CLIPS_FACE_DETECTOR_MODEL", "").strip()
    target = custom_path or (Path(env_p) if env_p else DEFAULT_MODEL_PATH)
    if target.is_file() and target.stat().st_size > 20_000:
        return target
    import httpx

    target.parent.mkdir(parents=True, exist_ok=True)
    resp = httpx.get(MODEL_DOWNLOAD_URL, follow_redirects=True, timeout=30.0)
    resp.raise_for_status()
    target.write_bytes(resp.content)
    return target


def track_clip_face(
    camera_path: str | Path,
    master_start: float,
    master_end: float,
    sync: SyncResult,
    out_parquet: Optional[Path] = None,
    fps: float = 15.0,
    pipe_width: int = 640,
    min_confidence: float = 0.45,
) -> FaceTrajectory:
    """Run MediaPipe Face Detector on [master_start, master_end] mapped through camera sync."""
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    cam_info = probe(camera_path)
    pipe_w = _even(pipe_width)
    pipe_h = _even(pipe_w * (cam_info.height / max(1, cam_info.width)))
    frame_bytes = pipe_w * pipe_h * 3

    cam_start = max(0.0, min(cam_info.duration, sync.camera_time(master_start)))
    cam_end = max(cam_start + 0.2, min(cam_info.duration, sync.camera_time(master_end)))
    cam_dur = max(0.2, cam_end - cam_start)

    # Adaptive downsampling: 10 fps for clips >= 30s (One Euro Filter smoothly interpolates to 60 fps)
    eff_fps = 10.0 if (fps == 15.0 and cam_dur >= 30.0) else fps

    model_file = ensure_face_detector_model()
    options = vision.FaceDetectorOptions(
        base_options=BaseOptions(model_asset_path=str(model_file)),
        running_mode=vision.RunningMode.VIDEO,
        min_detection_confidence=min_confidence,
    )

    cmd = [
        resolve_binary("ffmpeg"),
        "-hide_banner",
        "-nostdin",
        "-loglevel",
        "error",
        "-ss",
        f"{cam_start:.3f}",
        "-t",
        f"{cam_dur:.3f}",
        "-i",
        str(camera_path),
        "-an",
        "-vf",
        f"fps={eff_fps:g},scale={pipe_w}:{pipe_h}",
        "-f",
        "rawvideo",
        "-pix_fmt",
        "rgb24",
        "pipe:1",
    ]

    t_master: List[float] = []
    present: List[bool] = []
    cx_list: List[float] = []
    cy_list: List[float] = []
    size_list: List[float] = []
    conf_list: List[float] = []

    # Pre-allocated reusable frame buffer to avoid per-frame `.copy()` allocations
    reusable_arr = np.empty((pipe_h, pipe_w, 3), dtype=np.uint8)

    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    assert proc.stdout is not None
    try:
        with vision.FaceDetector.create_from_options(options) as detector:
            frame_idx = 0
            last_ts_ms = -1
            while True:
                buf = proc.stdout.read(frame_bytes)
                if len(buf) < frame_bytes:
                    break
                cam_t = cam_start + (frame_idx / eff_fps)
                ts_ms = int(round((frame_idx / eff_fps) * 1000.0))
                if ts_ms <= last_ts_ms:
                    ts_ms = last_ts_ms + 1
                last_ts_ms = ts_ms

                np.copyto(reusable_arr, np.frombuffer(buf, dtype=np.uint8).reshape((pipe_h, pipe_w, 3)))
                mp_img = mp.Image(image_format=mp.ImageFormat.SRGB, data=reusable_arr)
                res = detector.detect_for_video(mp_img, ts_ms)

                mt = round(sync.master_time(cam_t), 3)
                t_master.append(mt)

                if res.detections:
                    # Pick largest confident face
                    best = max(
                        res.detections,
                        key=lambda d: (d.bounding_box.width * d.bounding_box.height)
                        * (d.categories[0].score if d.categories else 1.0),
                    )
                    bb = best.bounding_box
                    score = float(best.categories[0].score) if best.categories else 0.8
                    nx = max(0.0, min(1.0, (bb.origin_x + bb.width * 0.5) / pipe_w))
                    ny = max(0.0, min(1.0, (bb.origin_y + bb.height * 0.5) / pipe_h))
                    nsz = max(0.05, min(1.0, bb.height / pipe_h))
                    present.append(True)
                    cx_list.append(round(nx, 4))
                    cy_list.append(round(ny, 4))
                    size_list.append(round(nsz, 4))
                    conf_list.append(round(score, 4))
                else:
                    present.append(False)
                    cx_list.append(cx_list[-1] if cx_list else 0.5)
                    cy_list.append(cy_list[-1] if cy_list else 0.45)
                    size_list.append(size_list[-1] if size_list else 0.32)
                    conf_list.append(0.0)

                frame_idx += 1
    finally:
        proc.stdout.close()
        if proc.stderr:
            proc.stderr.close()
        proc.wait(timeout=15)

    traj = FaceTrajectory(
        fps=eff_fps,
        width=pipe_w,
        height=pipe_h,
        master_start=round(master_start, 3),
        master_end=round(master_end, 3),
        t_master=t_master,
        present=present,
        cx=cx_list,
        cy=cy_list,
        size=size_list,
        confidence=conf_list,
    )
    if out_parquet is not None:
        traj.to_parquet(out_parquet)
    return traj
