"""FFmpeg command for the stacked 9:16 Short: camera on top, gameplay below,
ASS title/captions burned in, loudness-normalized audio.

The command builder is pure (unit-tested); ``render_clip`` in ``pipeline.py``
resolves inputs and runs it.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from ..domain import PixelRect, RenderOptions


@dataclass
class ComposeSpec:
    split_mode: bool  # True: input 0 = camera, input 1 = gameplay; False: single composite input
    duration: float
    gameplay_path: str
    gameplay_seek: float
    camera_path: Optional[str]
    camera_seek: float
    camera_scale: float  # sync scale: camera seconds per master second
    camera_lead_pad: float  # seconds of frozen first frame when the camera starts late
    camera_crop: PixelRect
    camera_zoom_crop: Optional[PixelRect]
    punch_window: Optional[Tuple[float, float]]  # clip-relative seconds
    gameplay_crop: PixelRect
    camera_height: int
    gameplay_height: int
    fps: float
    ass_path: Optional[str]
    fonts_dir: Optional[str]
    options: RenderOptions


def filter_path(path: str) -> str:
    """Quote a path for use inside a filtergraph option (works on Windows too)."""
    p = path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"'{p}'"


def _crop(r: PixelRect) -> str:
    return f"crop={r.w}:{r.h}:{r.x}:{r.y}"


def build_filtergraph(spec: ComposeSpec) -> str:
    o = spec.options
    w = o.width
    cam_src = "[0:v]"
    game_src = "[1:v]" if spec.split_mode else "[0:v]"
    audio_src = "[1:a]" if spec.split_mode else "[0:a]"
    parts: List[str] = []

    if spec.split_mode:
        pre = [f"setpts=(PTS-STARTPTS)/{spec.camera_scale:.6f}"]
        if spec.camera_lead_pad > 0:
            pre.append(f"tpad=start_duration={spec.camera_lead_pad:.3f}:start_mode=clone")
        parts.append(f"{cam_src}{','.join(pre)}[camsrc]")
        parts.append(f"{game_src}setpts=PTS-STARTPTS[gamesrc]")
    else:
        parts.append(f"{cam_src}setpts=PTS-STARTPTS,split=2[camsrc][gamesrc]")

    cam_scale = f"scale={w}:{spec.camera_height}:flags=lanczos,setsar=1"
    if spec.camera_zoom_crop is not None and spec.punch_window is not None:
        a, b = spec.punch_window
        parts.append("[camsrc]split=2[cam_a][cam_b]")
        parts.append(f"[cam_a]{_crop(spec.camera_crop)},{cam_scale}[cam_base]")
        parts.append(f"[cam_b]{_crop(spec.camera_zoom_crop)},{cam_scale}[cam_zoom]")
        parts.append(f"[cam_base][cam_zoom]overlay=0:0:enable='between(t,{a:.2f},{b:.2f})'[cam]")
    else:
        parts.append(f"[camsrc]{_crop(spec.camera_crop)},{cam_scale}[cam]")

    parts.append(f"[gamesrc]{_crop(spec.gameplay_crop)},scale={w}:{spec.gameplay_height}:flags=lanczos,setsar=1[game]")

    tail = [f"fps={spec.fps:g}", "format=yuv420p"]
    if spec.ass_path:
        sub = f"subtitles={filter_path(spec.ass_path)}"
        if spec.fonts_dir:
            sub += f":fontsdir={filter_path(spec.fonts_dir)}"
        tail.append(sub)
    parts.append(f"[cam][game]vstack=inputs=2,{','.join(tail)}[v]")

    audio = ["asetpts=PTS-STARTPTS"]
    if o.voice_boost:
        audio += ["highpass=f=70", "equalizer=f=3000:t=q:w=1.2:g=3"]
    audio += ["loudnorm=I=-14:TP=-1.5:LRA=11", "aresample=48000"]
    parts.append(f"{audio_src}{','.join(audio)}[a]")
    return ";".join(parts)


def build_args(spec: ComposeSpec, encoder_args: List[str], out_path: Path) -> List[str]:
    args: List[str] = []
    if spec.split_mode:
        assert spec.camera_path is not None
        cam_dur = spec.duration * spec.camera_scale + 1.0
        args += ["-ss", f"{spec.camera_seek:.3f}", "-t", f"{cam_dur:.3f}", "-i", spec.camera_path]
    args += ["-ss", f"{spec.gameplay_seek:.3f}", "-t", f"{spec.duration + 0.5:.3f}", "-i", spec.gameplay_path]
    args += [
        "-filter_complex", build_filtergraph(spec),
        "-map", "[v]", "-map", "[a]",
        "-t", f"{spec.duration:.3f}",
        *encoder_args,
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        str(out_path),
    ]
    return args
