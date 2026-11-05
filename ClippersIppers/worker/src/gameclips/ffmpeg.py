"""Thin FFmpeg/FFprobe wrappers. Always argument lists, never a shell string."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List, Optional, Sequence

from .config import get_settings
from .domain import Rect, StreamInfo


class FfmpegError(RuntimeError):
    pass


def run(args: Sequence[str], timeout: Optional[float] = None) -> None:
    s = get_settings()
    cmd = [s.ffmpeg, "-hide_banner", "-nostdin", "-loglevel", "error", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-15:])
        raise FfmpegError(f"ffmpeg failed ({proc.returncode}):\n{tail}")


def probe(path: str) -> StreamInfo:
    s = get_settings()
    proc = subprocess.run(
        [s.ffprobe, "-v", "error", "-print_format", "json", "-show_format", "-show_streams", path],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe failed for {path}: {proc.stderr.strip()}")
    info = json.loads(proc.stdout)
    video = next((st for st in info.get("streams", []) if st.get("codec_type") == "video"), None)
    has_audio = any(st.get("codec_type") == "audio" for st in info.get("streams", []))
    if video is None:
        raise FfmpegError(f"{path} has no video stream")
    num, _, den = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0.0)
    return StreamInfo(
        path=str(path),
        duration=duration,
        width=int(video["width"]),
        height=int(video["height"]),
        fps=round(fps, 3) if fps > 0 else 30.0,
        has_audio=has_audio,
    )


def crop_filter(rect: Optional[Rect], width: int, height: int) -> List[str]:
    if rect is None:
        return []
    px = rect.to_pixels(width, height)
    return [f"crop={px.w}:{px.h}:{px.x}:{px.y}"]


def extract_audio(src: str, dst: Path, sample_rate: int = 16000, channels: int = 1) -> Path:
    run(["-i", src, "-vn", "-ac", str(channels), "-ar", str(sample_rate), "-c:a", "pcm_s16le", str(dst)])
    return dst


def resample_wav(src: Path, dst: Path, sample_rate: int, channels: int = 1) -> Path:
    return extract_audio(str(src), dst, sample_rate, channels)


def make_video_proxy(src: StreamInfo, dst: Path, height: int, fps: float, crop: Optional[Rect] = None) -> Path:
    vf = crop_filter(crop, src.width, src.height) + [f"fps={fps:g}", f"scale=-2:{height}"]
    run(["-i", src.path, "-an", "-vf", ",".join(vf), "-c:v", "libx264", "-preset", "veryfast", "-crf", "28", str(dst)])
    return dst


def extract_frame(src: str, t: float, dst: Path, crop: Optional[Rect] = None, size: Optional[StreamInfo] = None, width: int = 640) -> Path:
    vf: List[str] = []
    if crop is not None and size is not None:
        vf += crop_filter(crop, size.width, size.height)
    vf.append(f"scale={width}:-2")
    run(["-ss", f"{max(0.0, t):.3f}", "-i", src, "-frames:v", "1", "-vf", ",".join(vf), "-q:v", "3", str(dst)])
    return dst


def video_encoder_args() -> List[str]:
    if get_settings().use_nvenc:
        return ["-c:v", "h264_nvenc", "-preset", "p5", "-rc", "vbr", "-cq", "20", "-b:v", "0"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "19"]


def software_encoder_args() -> List[str]:
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "19"]
