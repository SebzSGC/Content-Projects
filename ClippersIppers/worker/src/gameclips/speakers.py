"""Who said each line: STREAMER, GAME or UNKNOWN.

With a single mixed audio track, three independent pieces of evidence are fused:

* **mouth** — lip activity on the facecam while the line plays (strongest:
  the separate camera makes the face large and sharp)
* **voice** — similarity to the enrolled streamer voiceprint
* **ocr**   — the line matches dialogue the game printed on screen → GAME

Each yields a score in −1 (game) .. +1 (streamer), or None when unavailable.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from statistics import median
from typing import Dict, List, Optional, Sequence

from .domain import FaceTrack, OcrLine, Speaker, SyncResult, Utterance, new_id

WEIGHTS = {"mouth": 0.5, "voice": 0.3, "ocr": 0.7}
LABEL_THRESHOLD = 0.2


def _clamp(v: float, lo: float = -1.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, v))


def text_similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _frame_range(face: FaceTrack, cam_start: float, cam_end: float) -> range:
    a = max(0, int(cam_start * face.fps))
    b = min(len(face.jaw_open), int(cam_end * face.fps) + 1)
    return range(a, max(a, b))


def mouth_activity(face: FaceTrack, frames: range) -> Optional[float]:
    """Mean frame-to-frame jaw movement; None if the face is mostly missing."""
    idx = [i for i in frames if i > 0 and face.present[i] and face.present[i - 1]]
    if len(idx) < max(3, len(frames) // 2):
        return None
    return sum(abs(face.jaw_open[i] - face.jaw_open[i - 1]) for i in idx) / len(idx)


def silence_baseline(face: FaceTrack, sync: SyncResult, utterances: Sequence[Utterance], duration: float) -> Optional[float]:
    """Typical mouth movement while nobody is speaking (master-time gaps ≥ 1 s)."""
    gaps = []
    cursor = 0.0
    for u in sorted(utterances, key=lambda x: x.start):
        if u.start - cursor >= 1.0:
            gaps.append((cursor, u.start))
        cursor = max(cursor, u.end)
    if duration - cursor >= 1.0:
        gaps.append((cursor, duration))
    values = []
    for a, b in gaps:
        act = mouth_activity(face, _frame_range(face, sync.camera_time(a), sync.camera_time(b)))
        if act is not None:
            values.append(act)
    return median(values) if values else None


def mouth_score(activity: Optional[float], baseline: Optional[float]) -> Optional[float]:
    if activity is None or not baseline:
        return None
    ratio = activity / baseline
    return _clamp((ratio - 1.5) / 1.5)  # 1.5× baseline → neutral, 3× → streamer


def voice_score(similarity: Optional[float]) -> Optional[float]:
    if similarity is None:
        return None
    return _clamp((similarity - 0.35) / 0.2)


def ocr_score(u: Utterance, ocr: Sequence[OcrLine], tolerance: float = 1.0) -> Optional[float]:
    best = 0.0
    for line in ocr:
        if line.end + tolerance < u.start or line.start - tolerance > u.end:
            continue
        best = max(best, text_similarity(u.text, line.text))
    return _clamp(-(best - 0.5) / 0.3) if best >= 0.6 else None


def fuse(evidence: Dict[str, Optional[float]]) -> float:
    num = sum(WEIGHTS[k] * v for k, v in evidence.items() if v is not None)
    den = sum(WEIGHTS[k] for k, v in evidence.items() if v is not None)
    return num / den if den else 0.0


def label_speakers(
    utterances: List[Utterance],
    duration: float,
    face: Optional[FaceTrack],
    sync: SyncResult,
    voice_similarity: Dict[str, Optional[float]],
    ocr: Sequence[OcrLine],
) -> List[Utterance]:
    baseline = silence_baseline(face, sync, utterances, duration) if face else None
    for u in utterances:
        activity = (
            mouth_activity(face, _frame_range(face, sync.camera_time(u.start), sync.camera_time(u.end)))
            if face
            else None
        )
        evidence = {
            "mouth": mouth_score(activity, baseline),
            "voice": voice_score(voice_similarity.get(u.id)),
            "ocr": ocr_score(u, ocr),
        }
        combined = fuse(evidence)
        u.evidence = {k: (round(v, 3) if v is not None else None) for k, v in evidence.items()}
        u.speaker_confidence = round(abs(combined), 3)
        if combined > LABEL_THRESHOLD:
            u.speaker = Speaker.STREAMER
        elif combined < -LABEL_THRESHOLD:
            u.speaker = Speaker.GAME
        else:
            u.speaker = Speaker.UNKNOWN

    # Game lines the ASR missed (e.g. spoken over the streamer) come from OCR alone.
    extra: List[Utterance] = []
    for line in ocr:
        overlapping = [u for u in utterances if not (u.end + 1.0 < line.start or u.start - 1.0 > line.end)]
        if any(text_similarity(u.text, line.text) >= 0.6 for u in overlapping):
            continue
        extra.append(
            Utterance(
                id=new_id("u"),
                start=line.start,
                end=line.end,
                text=line.text,
                speaker=Speaker.GAME,
                speaker_confidence=0.8,
                source="ocr",
                evidence={"mouth": None, "voice": None, "ocr": -1.0},
            )
        )
    return sorted(utterances + extra, key=lambda u: u.start)
