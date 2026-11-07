"""Pure helpers around story selection: transcript windows for the LLM,
snapping cuts to sentence boundaries, de-duplication and scoring."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Tuple

from ..domain import Candidate, SignalTimeline, Speaker, Utterance

SPEAKER_TAG = {Speaker.STREAMER: "STREAMER", Speaker.GAME: "JUEGO", Speaker.UNKNOWN: "?"}


def fmt_time(sec: float) -> str:
    sec = max(0.0, sec)
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    tenths = int((sec - int(sec)) * 10)
    return f"{h}:{m:02d}:{s:02d}.{tenths}" if h else f"{m:02d}:{s:02d}.{tenths}"


def parse_time(value: str) -> float:
    parts = [float(p) for p in value.strip().split(":")]
    total = 0.0
    for p in parts:
        total = total * 60 + p
    return total


def utterance_line(u: Utterance) -> str:
    tag = SPEAKER_TAG[u.speaker]
    if u.speaker != Speaker.UNKNOWN and u.speaker_confidence < 0.5:
        tag += "?"
    return f"[{fmt_time(u.start)}-{fmt_time(u.end)}] {tag}: {u.text}"


def peak_line(p: Dict[str, float]) -> str:
    kinds = [name for name, key in (("risa", "laughter"), ("grito", "scream"), ("cara", "face"), ("juego", "game")) if p.get(key, 0) >= 0.6]
    return f"[{fmt_time(p['t'])}] >>> PICO DE REACCION {p['score']:.2f} ({', '.join(kinds) or 'energía'})"


def build_windows(
    utterances: Sequence[Utterance],
    timeline: Optional[SignalTimeline],
    duration: float,
    window_sec: float = 900.0,
    overlap_sec: float = 120.0,
) -> List[Tuple[float, float, str]]:
    """Overlapping transcript windows with reaction peaks interleaved."""
    peaks = timeline.peaks if timeline else []
    windows: List[Tuple[float, float, str]] = []
    start = 0.0
    while start < duration:
        end = min(duration, start + window_sec)
        items: List[Tuple[float, str]] = [(u.start, utterance_line(u)) for u in utterances if u.end > start and u.start < end]
        items += [(p["t"], peak_line(p)) for p in peaks if start <= p["t"] < end]
        if items:
            windows.append((start, end, "\n".join(line for _, line in sorted(items, key=lambda x: x[0]))))
        if end >= duration:
            break
        start = end - overlap_sec
    return windows


def snap_to_utterances(
    start: float,
    end: float,
    utterances: Sequence[Utterance],
    duration: float,
    min_len: float,
    max_len: float,
    lead: float = 0.3,
    tail: float = 1.5,
) -> Tuple[float, float]:
    """Never cut mid-sentence: start at a line's start, end after a line's end
    plus a short tail so the final reaction breathes."""
    ordered = sorted(utterances, key=lambda u: u.start)
    for u in ordered:
        if u.start <= start < u.end:
            start = u.start
            break
    for u in ordered:
        if u.start < end <= u.end:
            end = u.end
            break
    start = max(0.0, start - lead)
    end = min(duration, end + tail)

    if end - start > max_len:
        limit = start + max_len
        ends = [u.end for u in ordered if start < u.end <= limit - tail]
        end = min(duration, (max(ends) if ends else limit - tail) + tail)
    if end - start < min_len:
        for u in ordered:
            if u.end > end and u.end - start <= max_len:
                end = min(duration, u.end + tail)
                if end - start >= min_len:
                    break
        end = max(end, min(duration, start + min_len))
    return round(start, 2), round(end, 2)


def iou(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 0 else 0.0


def dedupe(candidates: List[Candidate], threshold: float = 0.4) -> List[Candidate]:
    kept: List[Candidate] = []
    for c in sorted(candidates, key=lambda c: c.final_score, reverse=True):
        if all(iou((c.start, c.end), (k.start, k.end)) < threshold for k in kept):
            kept.append(c)
    return kept


def signal_score(start: float, end: float, timeline: Optional[SignalTimeline]) -> float:
    if timeline is None:
        return 0.0
    values = timeline.series.get("excitement", [])[int(start) : int(end) + 1]
    if not values:
        return 0.0
    top = sorted(values, reverse=True)[: max(1, len(values) // 5)]
    return round(0.6 * (sum(top) / len(top)) + 0.4 * max(values), 3)


def reaction_peak(start: float, end: float, timeline: Optional[SignalTimeline]) -> Optional[float]:
    if timeline is None:
        return None
    values = timeline.series.get("reaction", [])
    a, b = int(start), min(len(values), int(end) + 1)
    if b <= a:
        return None
    i = max(range(a, b), key=lambda k: values[k])
    return float(i) if values[i] >= 0.5 else None


def final_score(llm: float, signal: float, verify: Optional[float]) -> float:
    if verify is None:
        return round(0.65 * llm + 35.0 * signal, 1)
    return round(0.35 * llm + 25.0 * signal + 0.4 * verify, 1)
