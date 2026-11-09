"""FFmpeg silencedetect wrapper, zero-overlap 10-minute chunk slicer and speech-only STT packing."""

from __future__ import annotations

import bisect
import hashlib
import re
from pathlib import Path
from typing import List, NamedTuple, Optional, Sequence, Tuple

from clipscore.domain import AudioChunk, SilenceSpan, TranscriptWord

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


# ───────────────────────── Speech-only STT packing ─────────────────────────
# STT providers bill per second of audio sent. Long silences (gameplay without talking, AFK) are cut out
# of the chunk before upload and every word timestamp is mapped back to the original chunk timeline, so
# the transcript downstream is identical in timing. Short pauses are always kept: the STT model needs
# them for punctuation, and the kept padding leaves >= 0.7 s between sentences (utterance grouping
# splits at 0.65 s on the remapped, original timestamps anyway).
SPEECH_ONLY_MIN_GAP_SEC = 2.0
SPEECH_ONLY_PAD_SEC = 0.35
SPEECH_ONLY_MIN_SAVED_SEC = 20.0
SPEECH_ONLY_MIN_SAVED_RATIO = 0.15
SPEECH_ONLY_MAX_SEGMENTS = 300


class PackedSegment(NamedTuple):
    packed_start: float
    orig_start: float
    length: float


class SpeechOnlyAudio(NamedTuple):
    path: Path
    duration: float
    segments: List[PackedSegment]


def plan_speech_only_spans(
    chunk_duration: float,
    local_silences: Sequence[SilenceSpan],
    min_gap_sec: float = SPEECH_ONLY_MIN_GAP_SEC,
    pad_sec: float = SPEECH_ONLY_PAD_SEC,
) -> List[Tuple[float, float]]:
    """Chunk-local spans to keep: everything except silences >= min_gap_sec, each cut shrunk by pad_sec."""
    keep: List[Tuple[float, float]] = []
    cursor = 0.0
    for s in sorted(local_silences, key=lambda x: x.start):
        if s.duration < min_gap_sec:
            continue
        # No padding at the chunk edges: there is no speech beyond them to protect.
        cut_a = cursor if s.start <= 0.001 else max(cursor, s.start + pad_sec)
        cut_b = chunk_duration if s.end >= chunk_duration - 0.001 else min(chunk_duration, s.end - pad_sec)
        if cut_b <= cut_a:
            continue
        if cut_a > cursor:
            keep.append((cursor, cut_a))
        cursor = cut_b
    if cursor < chunk_duration:
        keep.append((cursor, chunk_duration))
    return [(round(a, 3), round(b, 3)) for a, b in keep if b - a > 0.05]


def build_packed_segments(spans: Sequence[Tuple[float, float]]) -> List[PackedSegment]:
    out: List[PackedSegment] = []
    packed = 0.0
    for a, b in spans:
        out.append(PackedSegment(packed_start=round(packed, 6), orig_start=a, length=round(b - a, 6)))
        packed += b - a
    return out


def map_packed_time(t: float, segments: Sequence[PackedSegment]) -> float:
    """Map a timestamp of the packed (speech-only) audio back to the original chunk timeline."""
    if not segments:
        return t
    starts = [s.packed_start for s in segments]
    i = max(0, bisect.bisect_right(starts, t) - 1)
    seg = segments[i]
    return seg.orig_start + min(max(0.0, t - seg.packed_start), seg.length)


def remap_packed_words(words: Sequence[TranscriptWord], segments: Sequence[PackedSegment]) -> List[TranscriptWord]:
    """Map STT words from packed time to original chunk time. A word never stretches across a removed silence."""
    if not segments:
        return list(words)
    starts = [s.packed_start for s in segments]
    out: List[TranscriptWord] = []
    for w in words:
        i = max(0, bisect.bisect_right(starts, w.start) - 1)
        seg = segments[i]
        offset = seg.orig_start - seg.packed_start
        seg_end = seg.packed_start + seg.length
        s = w.start + offset
        e = min(w.end, seg_end) + offset
        out.append(TranscriptWord(text=w.text, start=round(s, 3), end=round(max(s + 0.03, e), 3), prob=w.prob))
    return out


def _local_silences(chunk: AudioChunk, silences: Sequence[SilenceSpan]) -> List[SilenceSpan]:
    out: List[SilenceSpan] = []
    for s in silences:
        a = max(0.0, s.start - chunk.start_cam_sec)
        b = min(chunk.duration, s.end - chunk.start_cam_sec)
        if b > a:
            out.append(SilenceSpan(start=round(a, 3), end=round(b, 3)))
    return out


def write_speech_only_opus(
    chunk: AudioChunk,
    silences: Sequence[SilenceSpan],
    work_dir: Path,
    bitrate: str = "48k",
) -> Optional[SpeechOnlyAudio]:
    """Build a speech-only Opus file for a chunk, or None when cutting would save too little to be worth it.

    Segments are cut with sample-accurate `atrim` and joined with `concat`, so the packed timeline matches
    the segment map exactly. Re-encoding uses a higher bitrate than the source chunk to avoid audible
    generational loss on the voice.
    """
    local = _local_silences(chunk, silences)
    min_gap = SPEECH_ONLY_MIN_GAP_SEC
    spans = plan_speech_only_spans(chunk.duration, local, min_gap_sec=min_gap)
    while len(spans) > SPEECH_ONLY_MAX_SEGMENTS:
        min_gap *= 1.5
        spans = plan_speech_only_spans(chunk.duration, local, min_gap_sec=min_gap)
    packed_dur = sum(b - a for a, b in spans)
    saved = chunk.duration - packed_dur
    if not spans or saved < SPEECH_ONLY_MIN_SAVED_SEC or saved < chunk.duration * SPEECH_ONLY_MIN_SAVED_RATIO:
        return None

    work_dir.mkdir(parents=True, exist_ok=True)
    dst = work_dir / f"speech_{chunk.sha256 or chunk.index}_{len(spans)}.opus"
    if not dst.is_file() or dst.stat().st_size == 0:
        branches = "".join(
            f"[0:a]atrim=start={a:.3f}:end={b:.3f},asetpts=PTS-STARTPTS[s{i}];" for i, (a, b) in enumerate(spans)
        )
        joined = "".join(f"[s{i}]" for i in range(len(spans)))
        graph = f"{branches}{joined}concat=n={len(spans)}:v=0:a=1[out]"
        run_ffmpeg(
            [
                "-loglevel", "error",
                "-i", str(chunk.path),
                "-filter_complex", graph,
                "-map", "[out]",
                "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", bitrate, "-vbr", "on",
                str(dst),
            ]
        )
    return SpeechOnlyAudio(path=dst, duration=round(packed_dur, 3), segments=build_packed_segments(spans))
