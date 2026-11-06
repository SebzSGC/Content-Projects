"""Safe FFmpeg/FFprobe subprocess wrappers with automatic WinGet binary discovery on Windows."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional, Sequence

from clipscore.domain import AudioStreamMeta, StreamProbe


class FfmpegError(RuntimeError):
    pass


@lru_cache(maxsize=2)
def resolve_binary(name: str = "ffmpeg") -> str:
    """Find ffmpeg or ffprobe via env var, PATH, or Windows WinGet installation directory."""
    env_key = "CLIPS_FFMPEG" if name == "ffmpeg" else "CLIPS_FFPROBE"
    configured = os.environ.get(env_key, "").strip()
    if configured and (shutil.which(configured) or Path(configured).is_file()):
        return configured

    found = shutil.which(name)
    if found:
        return found

    if os.name == "nt":
        exe = f"{name}.exe"
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            winget_links = Path(local_app) / "Microsoft" / "WinGet" / "Links" / exe
            if winget_links.is_file():
                return str(winget_links)
            pkgs = Path(local_app) / "Microsoft" / "WinGet" / "Packages"
            if pkgs.is_dir():
                matches = sorted(pkgs.glob(f"Gyan.FFmpeg*/**/{exe}"), reverse=True)
                if matches:
                    return str(matches[0])
    return name


def run_ffmpeg(args: Sequence[str], timeout: Optional[float] = None) -> str:
    cmd = [resolve_binary("ffmpeg"), "-hide_banner", "-nostdin", "-y", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout)
    if proc.returncode != 0:
        tail = "\n".join(proc.stderr.strip().splitlines()[-18:])
        raise FfmpegError(f"FFmpeg falló ({proc.returncode}):\n{tail}")
    return proc.stderr


def probe(path: str | Path) -> StreamProbe:
    p = str(path)
    cmd = [
        resolve_binary("ffprobe"),
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        p,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if proc.returncode != 0:
        raise FfmpegError(f"ffprobe falló para {p}: {proc.stderr.strip()}")
    info = json.loads(proc.stdout)
    streams = info.get("streams", [])
    video = next((st for st in streams if st.get("codec_type") == "video"), None)
    if video is None:
        raise FfmpegError(f"El archivo no contiene pista de video: {p}")

    audio_streams: List[AudioStreamMeta] = []
    audio_pos = 0
    for st in streams:
        if st.get("codec_type") == "audio":
            tags = st.get("tags") or {}
            audio_streams.append(
                AudioStreamMeta(
                    index=audio_pos,
                    codec_name=str(st.get("codec_name", "aac")),
                    channels=int(st.get("channels") or 2),
                    sample_rate=int(st.get("sample_rate") or 48000),
                    title=str(tags.get("title") or tags.get("handler_name") or ""),
                )
            )
            audio_pos += 1

    num, _, den = str(video.get("avg_frame_rate") or video.get("r_frame_rate") or "30/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 30.0
    duration = float(info.get("format", {}).get("duration") or video.get("duration") or 0.0)
    return StreamProbe(
        path=str(Path(p).resolve()),
        duration=round(duration, 3),
        width=int(video["width"]),
        height=int(video["height"]),
        fps=round(fps, 3) if fps > 0 else 30.0,
        has_audio=len(audio_streams) > 0,
        audio_streams=audio_streams,
    )


def detect_clean_game_audio_stream(gameplay_probe: StreamProbe) -> Optional[int]:
    """If gameplay carries >= 2 audio tracks (track 0 = stream mix, track 1 = game-only), return game-only audio index."""
    if len(gameplay_probe.audio_streams) < 2:
        return None
    for st in gameplay_probe.audio_streams[1:]:
        low = st.title.lower()
        if any(k in low for k in ("game", "juego", "desktop", "escritorio")):
            return st.index
    return 1


def extract_wav16k(src: str | Path, dst: Path, audio_track_index: int = 0) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-loglevel",
            "error",
            "-i",
            str(src),
            "-map",
            f"0:a:{audio_track_index}",
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(dst),
        ]
    )
    return dst


def extract_opus_mono(
    src: str | Path,
    dst: Path,
    start_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
    bitrate: str = "32k",
) -> Path:
    """Extract camera voice to compact 16kHz mono Opus (~2.4 MB per 10 min)."""
    dst.parent.mkdir(parents=True, exist_ok=True)
    args: List[str] = ["-loglevel", "error"]
    if start_sec is not None and start_sec > 0:
        args += ["-ss", f"{start_sec:.3f}"]
    args += ["-i", str(src)]
    if duration_sec is not None and duration_sec > 0:
        args += ["-t", f"{duration_sec:.3f}"]
    args += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", bitrate, "-vbr", "on", str(dst)]
    run_ffmpeg(args)
    return dst


def extract_frame(src: str | Path, t: float, dst: Path, width: int = 640) -> Path:
    dst.parent.mkdir(parents=True, exist_ok=True)
    run_ffmpeg(
        [
            "-loglevel",
            "error",
            "-ss",
            f"{max(0.0, t):.3f}",
            "-i",
            str(src),
            "-frames:v",
            "1",
            "-vf",
            f"scale={width}:-2",
            "-q:v",
            "3",
            str(dst),
        ]
    )
    return dst


def measure_loudnorm(src: str | Path, start_sec: float = 0.0, duration_sec: float = 30.0) -> Optional[Dict[str, str]]:
    """Measure integrated loudness with FFmpeg loudnorm filter (pass 1) for accurate -14 LUFS normalization."""
    stderr = run_ffmpeg(
        [
            "-ss",
            f"{max(0.0, start_sec):.3f}",
            "-t",
            f"{max(1.0, duration_sec):.3f}",
            "-i",
            str(src),
            "-vn",
            "-af",
            "loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    start_idx = stderr.rfind("{")
    end_idx = stderr.rfind("}")
    if start_idx != -1 and end_idx > start_idx:
        try:
            return json.loads(stderr[start_idx : end_idx + 1])
        except json.JSONDecodeError:
            return None
    return None
