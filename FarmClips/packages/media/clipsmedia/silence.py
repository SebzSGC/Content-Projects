"""FFmpeg silencedetect wrapper and zero-overlap 10-minute chunk slicer."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import List, Sequence, Tuple

from clipscore.domain import AudioChunk, SilenceSpan

from .ffmpeg import extract_opus_mono, run_ffmpeg


def _chunk_digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(1024 * 256)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:24]

SILENCE_START_RE = re.compile(r"silence_start:\s*([0-9.]+)")
SILENCE_END_RE = re.compile(r"silence_end:\s*([0-9.]+)")


def detect_silences(
    audio_path: str | Path,
    noise_db: float = -36.0,
    min_silence_sec: float = 0.35,
) -> List[SilenceSpan]:
    """Run FFmpeg silencedetect on mono audio and return ordered SilenceSpan list."""
    stderr = run_ffmpeg(
        [
            "-loglevel",
            "info",
            "-i",
            str(audio_path),
            "-af",
            f"silencedetect=noise={noise_db:.1f}dB:d={min_silence_sec:.2f}",
            "-f",
            "null",
            "-",
        ]
    )
    spans: List[SilenceSpan] = []
    cur_start: float | None = None
    for line in stderr.splitlines():
        m_s = SILENCE_START_RE.search(line)
        if m_s:
            cur_start = float(m_s.group(1))
            continue
        m_e = SILENCE_END_RE.search(line)
        if m_e and cur_start is not None:
            end_val = float(m_e.group(1))
            if end_val > cur_start:
                spans.append(SilenceSpan(start=round(cur_start, 3), end=round(end_val, 3)))
            cur_start = None
    return spans


def compute_chunk_boundaries(
    total_duration: float,
    silences: Sequence[SilenceSpan],
    target_chunk_sec: float = 600.0,
    search_window_sec: float = 75.0,
) -> List[Tuple[float, float]]:
    """Split timeline near multiples of target_chunk_sec (10 min) at silence midpoints — zero overlap, zero split words."""
    if total_duration <= 0:
        return []
    if total_duration <= target_chunk_sec * 1.12:
        return [(0.0, round(total_duration, 3))]

    midpoints = [round((s.start + s.end) / 2.0, 3) for s in silences if s.duration >= 0.3]
    cuts: List[float] = [0.0]
    cursor = 0.0

    while total_duration - cursor > target_chunk_sec * 1.10:
        ideal = cursor + target_chunk_sec
        lo = max(cursor + target_chunk_sec * 0.4, ideal - search_window_sec)
        hi = min(total_duration - 5.0, ideal + search_window_sec)
        candidates = [m for m in midpoints if lo <= m <= hi]
        if candidates:
            cut = min(candidates, key=lambda m: abs(m - ideal))
        else:
            cut = round(ideal, 3)
        cuts.append(round(cut, 3))
        cursor = cut

    cuts.append(round(total_duration, 3))
    return [(cuts[i], cuts[i + 1]) for i in range(len(cuts) - 1) if cuts[i + 1] - cuts[i] > 0.2]


def slice_opus_chunks(
    camera_opus_or_wav: str | Path,
    chunks_dir: Path,
    total_duration: float,
    silences: Sequence[SilenceSpan],
    target_chunk_sec: float = 600.0,
) -> List[AudioChunk]:
    """Slice camera audio into Opus chunks aligned to silences."""
    chunks_dir.mkdir(parents=True, exist_ok=True)
    bounds = compute_chunk_boundaries(total_duration, silences, target_chunk_sec=target_chunk_sec)
    out: List[AudioChunk] = []
    for idx, (a, b) in enumerate(bounds):
        dst = chunks_dir / f"chunk_{idx:04d}_{int(a * 1000)}_{int(b * 1000)}.opus"
        if not dst.is_file() or dst.stat().st_size == 0:
            extract_opus_mono(camera_opus_or_wav, dst, start_sec=a, duration_sec=b - a)
        out.append(
            AudioChunk(
                index=idx,
                start_cam_sec=a,
                end_cam_sec=b,
                path=str(dst.resolve()),
                size_bytes=dst.stat().st_size,
                sha256=_chunk_digest(dst),
            )
        )
    return out


def resplit_chunk_finer(
    chunk: AudioChunk,
    chunks_dir: Path,
    silences: Sequence[SilenceSpan],
) -> List[AudioChunk]:
    """Re-cut a single AudioChunk in half (aligned to silence) when an API returns 413 Payload Too Large."""
    dur = chunk.duration
    if dur <= 15.0:
        raise ValueError(f"No se puede subdividir un tramo de {dur:.1f}s aún más tras un error 413.")
    local_silences = [
        SilenceSpan(start=s.start - chunk.start_cam_sec, end=s.end - chunk.start_cam_sec)
        for s in silences
        if s.end > chunk.start_cam_sec and s.start < chunk.end_cam_sec
    ]
    if not local_silences and Path(chunk.path).is_file():
        local_silences = detect_silences(chunk.path)
    sub_bounds = compute_chunk_boundaries(dur, local_silences, target_chunk_sec=dur / 2.0, search_window_sec=dur * 0.25)
    if len(sub_bounds) < 2:
        mid = round(dur / 2.0, 3)
        sub_bounds = [(0.0, mid), (mid, dur)]

    sub_chunks: List[AudioChunk] = []
    for sub_i, (la, lb) in enumerate(sub_bounds):
        ga = round(chunk.start_cam_sec + la, 3)
        gb = round(chunk.start_cam_sec + lb, 3)
        dst = chunks_dir / f"sub_{chunk.index:04d}_{sub_i}_{int(ga * 1000)}_{int(gb * 1000)}.opus"
        extract_opus_mono(chunk.path, dst, start_sec=la, duration_sec=lb - la)
        sub_chunks.append(
            AudioChunk(
                index=chunk.index * 10 + sub_i,
                start_cam_sec=ga,
                end_cam_sec=gb,
                path=str(dst.resolve()),
                size_bytes=dst.stat().st_size,
                sha256=_chunk_digest(dst),
            )
        )
    return sub_chunks
