"""Groups words into numbered utterances (u0001...) and builds the compact LLM timeline."""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

from ..domain import SignalPeak, SignalSeries, TranscriptWord, Utterance

SENTENCE_ENDINGS = (".", "?", "!", "…")


def fmt_hms(sec: float) -> str:
    sec = max(0, int(round(sec)))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    return f"{h}:{m:02d}:{s:02d}" if h else f"{m}:{s:02d}"


def group_words_into_utterances(
    words: Sequence[TranscriptWord],
    max_pause_sec: float = 0.65,
    max_words_per_utterance: int = 20,
    max_duration_sec: float = 10.0,
) -> List[Utterance]:
    """Group ordered words into natural utterances with compact IDs (u0001, u0002, ...)."""
    if not words:
        return []
    ordered = sorted(words, key=lambda w: (w.start, w.end))
    utterances: List[Utterance] = []
    buf: List[TranscriptWord] = []

    def flush() -> None:
        if not buf:
            return
        uid = f"u{len(utterances) + 1:04d}"
        text = " ".join(w.text.strip() for w in buf if w.text.strip()).strip()
        if text:
            utterances.append(
                Utterance(
                    id=uid,
                    start=round(buf[0].start, 3),
                    end=round(buf[-1].end, 3),
                    text=text,
                    words=list(buf),
                    speaker="STREAMER",
                )
            )
        buf.clear()

    for w in ordered:
        if not w.text.strip():
            continue
        if buf:
            gap = w.start - buf[-1].end
            prev_text = buf[-1].text.strip()
            ended_sentence = prev_text.endswith(SENTENCE_ENDINGS)
            span = w.end - buf[0].start
            if (
                gap >= max_pause_sec
                or (ended_sentence and gap >= 0.15)
                or len(buf) >= max_words_per_utterance
                or span >= max_duration_sec
            ):
                flush()
        buf.append(w)

    flush()
    return utterances


def _format_peak(p: SignalPeak) -> str:
    parts = [f"score={p.score:.2f}"]
    if p.mic >= 0.45:
        parts.append(f"mic={p.mic:.2f}")
    if p.game >= 0.45:
        parts.append(f"juego={p.game:.2f}")
    if p.motion >= 0.45:
        parts.append(f"mov={p.motion:.2f}")
    if getattr(p, "hud", 0.0) >= 0.45:
        parts.append(f"hud={p.hud:.2f}")
    return f">>> PICO [{fmt_hms(p.t)}] ({' '.join(parts)})"


def prune_utterances_by_signal_clusters(
    utterances: Sequence[Utterance],
    signals: Optional[SignalSeries],
    min_vod_sec: float = 600.0,
    pre_peak_sec: float = 45.0,
    post_peak_sec: float = 60.0,
    min_excitement: float = 0.42,
) -> List[Utterance]:
    """Two-stage coarse-to-fine token filter: prune low-energy dead zones in long VODs (>= 10 min) using CPU signals."""
    if not utterances or signals is None:
        return list(utterances)
    total_dur = max(float(signals.duration or 0.0), max(u.end for u in utterances))
    if total_dur < min_vod_sec:
        return list(utterances)

    raw_spans: List[Tuple[float, float]] = []
    for p in signals.peaks:
        raw_spans.append((max(0.0, p.t - pre_peak_sec), min(total_dur, p.t + post_peak_sec)))

    for idx, exc in enumerate(signals.excitement):
        if exc >= min_excitement:
            t_sec = float(idx)
            raw_spans.append((max(0.0, t_sec - pre_peak_sec * 0.6), min(total_dur, t_sec + post_peak_sec * 0.6)))

    if not raw_spans:
        return list(utterances)

    raw_spans.sort(key=lambda item: item[0])
    merged: List[Tuple[float, float]] = [raw_spans[0]]
    for s, e in raw_spans[1:]:
        prev_s, prev_e = merged[-1]
        if s <= prev_e + 5.0:
            merged[-1] = (prev_s, max(prev_e, e))
        else:
            merged.append((s, e))

    kept = [
        u
        for u in utterances
        if any(u.end >= span_s and u.start <= span_e for span_s, span_e in merged)
    ]
    if len(kept) < min(len(utterances), 8):
        return list(utterances)
    return kept


def build_compact_timeline(
    utterances: Sequence[Utterance],
    signals: Optional[SignalSeries] = None,
) -> str:
    """Build the exact compact text timeline for the LLM: `u0412 [1:02:03] texto` + peak markers."""
    events: List[Tuple[float, int, str]] = []
    for u in utterances:
        events.append((u.start, 1, f"{u.id} [{fmt_hms(u.start)}] {u.text}"))
    if signals:
        for p in signals.peaks:
            events.append((p.t, 0, _format_peak(p)))
    events.sort(key=lambda item: (item[0], item[1]))
    return "\n".join(line for _, _, line in events)


def build_timeline_windows_if_needed(
    utterances: Sequence[Utterance],
    signals: Optional[SignalSeries],
    max_chars_per_call: int = 320_000,
    window_sec: float = 3600.0,
    overlap_sec: float = 180.0,
    prune_dead_zones: bool = True,
) -> List[str]:
    """Single call for normal VODs (with CPU signal-cluster dead-zone pruning on >=10m streams); splits if exceeding cap."""
    active_utts = (
        prune_utterances_by_signal_clusters(utterances, signals)
        if prune_dead_zones
        else list(utterances)
    )
    full_text = build_compact_timeline(active_utts, signals)
    if len(full_text) <= max_chars_per_call or not active_utts:
        return [full_text] if full_text.strip() else []

    total_dur = max(u.end for u in active_utts)
    windows: List[str] = []
    start = 0.0
    while start < total_dur:
        end = min(total_dur, start + window_sec)
        sub_utts = [u for u in active_utts if u.end > start and u.start < end]
        sub_sig = None
        if signals is not None:
            sub_peaks = [p for p in signals.peaks if start <= p.t < end]
            sub_sig = SignalSeries(duration=signals.duration, peaks=sub_peaks)
        text = build_compact_timeline(sub_utts, sub_sig)
        if text.strip():
            windows.append(text)
        if end >= total_dur:
            break
        start = end - overlap_sec
    return windows
