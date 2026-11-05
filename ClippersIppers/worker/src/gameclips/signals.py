"""Fuse every per-second signal into one excitement curve on the master timeline.

The pattern a good clip of this style follows: **something happens in the game**
(event, character line, chaos) and **right after the streamer reacts** (laugh,
scream, face). Audio reactions are noisy with a mixed track, so the facecam
blendshapes carry real weight and agreement between both is rewarded.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Dict, List, Optional, Sequence

from .domain import FaceTrack, SignalTimeline, SyncResult


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, v))


def fit_length(values: Sequence[float], n: int, fill: float = 0.0) -> List[float]:
    out = list(values[:n])
    return out + [fill] * (n - len(out))


def robust_norm(values: Sequence[float]) -> List[float]:
    """Map to 0..1 relative to this VOD's own baseline (median / MAD)."""
    if not values:
        return []
    med = median(values)
    mad = median(abs(v - med) for v in values) * 1.4826
    scale = mad if mad > 1e-9 else (max(values) - med) / 3 or 1.0
    # z = 0 (typical) → ~0.08, z = 1.5 → 0.5, z = 3 (clear outlier) → ~0.92
    return [_clamp01(1.0 / (1.0 + math.exp(-1.6 * ((v - med) / scale - 1.5)))) for v in values]


def smooth_max(values: Sequence[float], radius: int = 1) -> List[float]:
    n = len(values)
    return [max(values[max(0, i - radius) : min(n, i + radius + 1)]) for i in range(n)]


def face_per_second(face: FaceTrack, sync: SyncResult, seconds: int, attr: str) -> List[float]:
    """Max of a face series over each master second, mapped through the sync."""
    series = getattr(face, attr)
    out: List[float] = []
    for s in range(seconds):
        a = int(sync.camera_time(s) * face.fps)
        b = int(sync.camera_time(s + 1) * face.fps)
        window = [series[i] for i in range(max(0, a), min(len(series), b)) if face.present[i]]
        out.append(max(window) if window else 0.0)
    return out


def mouth_motion_per_second(face: FaceTrack, sync: SyncResult, seconds: int) -> List[float]:
    out: List[float] = []
    for s in range(seconds):
        a = max(1, int(sync.camera_time(s) * face.fps))
        b = min(len(face.jaw_open), int(sync.camera_time(s + 1) * face.fps))
        diffs = [abs(face.jaw_open[i] - face.jaw_open[i - 1]) for i in range(a, b) if face.present[i]]
        out.append(sum(diffs) / len(diffs) if diffs else 0.0)
    return out


def find_peaks(values: Sequence[float], threshold: float, min_distance: int, limit: int) -> List[int]:
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    chosen: List[int] = []
    for i in order:
        if values[i] < threshold or len(chosen) >= limit:
            break
        if all(abs(i - j) >= min_distance for j in chosen):
            chosen.append(i)
    return sorted(chosen)


def build_timeline(
    duration: float,
    audio: Dict[str, List[float]],
    loudness_db: List[float],
    motion: Dict[str, List[float]],
    face: Optional[FaceTrack],
    sync: SyncResult,
) -> SignalTimeline:
    n = int(math.ceil(duration))
    laughter = robust_norm(fit_length(audio.get("laughter", []), n))
    scream = robust_norm(fit_length(audio.get("scream", []), n))
    game_events = robust_norm(fit_length(audio.get("game_events", []), n))
    loud = robust_norm(fit_length(loudness_db, n, fill=-60.0))
    mot = robust_norm(fit_length(motion.get("motion", []), n))
    scene = fit_length(motion.get("scene_cut", []), n)
    if face is not None:
        smile = robust_norm(face_per_second(face, sync, n, "smile"))
        surprise = robust_norm(face_per_second(face, sync, n, "surprise"))
        mouth = robust_norm(mouth_motion_per_second(face, sync, n))
    else:
        smile = surprise = mouth = [0.0] * n

    reaction: List[float] = []
    for i in range(n):
        audio_r = max(laughter[i], scream[i])
        face_r = max(smile[i], surprise[i])
        both = 0.2 if audio_r > 0.5 and face_r > 0.5 else 0.0
        weight_face = 0.45 if face is not None else 0.0
        reaction.append(_clamp01((1 - weight_face) * audio_r + weight_face * face_r + both))
    game = [max(game_events[i], 0.8 * mot[i]) for i in range(n)]
    setup_payoff = [reaction[i] * max(game[max(0, i - 6) : i + 1]) for i in range(n)]
    excitement = smooth_max(
        [_clamp01(0.5 * reaction[i] + 0.2 * game[i] + 0.15 * loud[i] + 0.15 * setup_payoff[i]) for i in range(n)],
        radius=1,
    )

    peaks = [
        {
            "t": float(i),
            "score": round(excitement[i], 3),
            "laughter": round(laughter[i], 3),
            "scream": round(scream[i], 3),
            "face": round(max(smile[i], surprise[i]), 3),
            "game": round(game[i], 3),
        }
        for i in find_peaks(excitement, threshold=0.55, min_distance=20, limit=80)
    ]
    r = lambda xs: [round(x, 3) for x in xs]  # noqa: E731 - keeps the JSON small
    return SignalTimeline(
        duration=duration,
        series={
            "laughter": r(laughter),
            "scream": r(scream),
            "game_events": r(game_events),
            "loudness": r(loud),
            "motion": r(mot),
            "scene_cut": r(scene),
            "smile": r(smile),
            "surprise": r(surprise),
            "mouth": r(mouth),
            "reaction": r(reaction),
            "game": r(game),
            "excitement": r(excitement),
        },
        peaks=peaks,
    )
