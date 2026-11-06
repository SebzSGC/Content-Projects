"""Resolves LLM phrase IDs (u0001..u9999) into exact word-level timestamps, clamps to 20-60s, dedupes, and scores."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from ..domain import CuratedClip, EmojiSuggestion, SignalSeries, Utterance, new_id

UTT_ID_RE = re.compile(r"u?(\d+)", re.IGNORECASE)


def _norm_uid(raw_id: str, valid_map: Dict[str, int]) -> Optional[int]:
    key = raw_id.strip().lower()
    if key in valid_map:
        return valid_map[key]
    m = UTT_ID_RE.search(key)
    if not m:
        return None
    canonical = f"u{int(m.group(1)):04d}"
    if canonical in valid_map:
        return valid_map[canonical]
    # Clamp to closest available index if slightly out of range
    idx = int(m.group(1)) - 1
    if 0 <= idx < len(valid_map):
        return idx
    return None


def adjust_utterance_span(
    start_idx: int,
    end_idx: int,
    utterances: Sequence[Utterance],
    vod_duration: float,
    min_sec: float = 20.0,
    max_sec: float = 60.0,
    lead_pad: float = 0.2,
    tail_pad: float = 0.8,
) -> Tuple[int, int, float, float]:
    """Expand or trim along utterance boundaries so clip stays in [min_sec, max_sec] without mid-sentence cuts."""
    n = len(utterances)
    s_i = max(0, min(n - 1, min(start_idx, end_idx)))
    e_i = max(s_i, min(n - 1, max(start_idx, end_idx)))

    def bounds(a_i: int, b_i: int) -> Tuple[float, float]:
        u_a, u_b = utterances[a_i], utterances[b_i]
        w_start = u_a.words[0].start if u_a.words else u_a.start
        w_end = u_b.words[-1].end if u_b.words else u_b.end
        return max(0.0, w_start - lead_pad), min(vod_duration, w_end + tail_pad)

    a, b = bounds(s_i, e_i)

    # Trim if > max_sec while keeping >= 1 utterance
    while b - a > max_sec and e_i > s_i:
        e_i -= 1
        a, b = bounds(s_i, e_i)
    if b - a > max_sec:
        b = min(vod_duration, a + max_sec)

    # Expand forward then backward along whole utterances if < min_sec
    while b - a < min_sec and (e_i + 1 < n or s_i > 0):
        expanded = False
        if e_i + 1 < n:
            cand_a, cand_b = bounds(s_i, e_i + 1)
            if cand_b - cand_a <= max_sec:
                e_i += 1
                a, b = cand_a, cand_b
                expanded = True
        if b - a < min_sec and s_i > 0:
            cand_a, cand_b = bounds(s_i - 1, e_i)
            if cand_b - cand_a <= max_sec:
                s_i -= 1
                a, b = cand_a, cand_b
                expanded = True
        if not expanded:
            break

    if b - a < min_sec and vod_duration >= min_sec:
        b = min(vod_duration, a + min_sec)
        if b - a < min_sec:
            a = max(0.0, b - min_sec)

    return s_i, e_i, round(a, 3), round(b, 3)


def compute_clip_signal_score(start: float, end: float, signals: Optional[SignalSeries]) -> Tuple[float, List[float]]:
    if signals is None or not signals.excitement:
        return 0.0, []
    lo = max(0, int(start))
    hi = min(len(signals.excitement), int(end) + 1)
    if hi <= lo:
        return 0.0, []
    exc = signals.excitement[lo:hi]
    top_k = sorted(exc, reverse=True)[: max(1, len(exc) // 5)]
    sig_score = round(0.6 * (sum(top_k) / len(top_k)) + 0.4 * max(exc), 3)

    # Find up to 3 reaction peaks inside [start, end], sorted by strength
    react = signals.reaction
    local_indices = list(range(lo, min(len(react), hi)))
    local_indices.sort(key=lambda idx: react[idx], reverse=True)
    chosen_peaks: List[float] = []
    for idx in local_indices:
        if react[idx] < 0.45:
            break
        if all(abs(idx - p) >= 3.5 for p in chosen_peaks):
            chosen_peaks.append(float(idx))
        if len(chosen_peaks) >= 3:
            break
    return sig_score, sorted(chosen_peaks)


def iou_1d(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    inter = max(0.0, min(a[1], b[1]) - max(a[0], b[0]))
    union = max(a[1], b[1]) - min(a[0], b[0])
    return inter / union if union > 1e-6 else 0.0


def dedupe_clips(clips: Sequence[CuratedClip], max_iou: float = 0.35) -> List[CuratedClip]:
    kept: List[CuratedClip] = []
    for c in sorted(clips, key=lambda x: x.final_score, reverse=True):
        if all(iou_1d((c.start, c.end), (k.start, k.end)) < max_iou for k in kept):
            kept.append(c)
    return kept


def resolve_curated_clips(
    llm_clips: Sequence[Dict[str, Any]],
    utterances: Sequence[Utterance],
    signals: Optional[SignalSeries],
    vod_duration: float,
    min_sec: float = 20.0,
    max_sec: float = 60.0,
) -> List[CuratedClip]:
    """Convert LLM utterance IDs into exact word-bounded CuratedClip objects."""
    if not utterances or not llm_clips:
        return []
    uid_map = {u.id.lower(): i for i, u in enumerate(utterances)}
    resolved: List[CuratedClip] = []

    for item in llm_clips:
        s_idx = _norm_uid(str(item.get("start_id", "")), uid_map)
        e_idx = _norm_uid(str(item.get("end_id", "")), uid_map)
        if s_idx is None or e_idx is None:
            continue

        s_i, e_i, start_t, end_t = adjust_utterance_span(
            s_idx, e_idx, utterances, vod_duration, min_sec=min_sec, max_sec=max_sec
        )
        if end_t - start_t < 3.0:
            continue

        llm_score = float(max(0.0, min(100.0, float(item.get("score", 0)))))
        sig_score, r_peaks = compute_clip_signal_score(start_t, end_t, signals)
        combined = round(min(100.0, 0.70 * llm_score + 30.0 * sig_score), 1)

        raw_emojis = item.get("emojis") or []
        emojis: List[EmojiSuggestion] = []
        for em in raw_emojis:
            if isinstance(em, dict) and em.get("word") and em.get("emoji"):
                emojis.append(EmojiSuggestion(word=str(em["word"]).strip(), emoji=str(em["emoji"]).strip()))

        resolved.append(
            CuratedClip(
                id=new_id("clip"),
                start_id=utterances[s_i].id,
                end_id=utterances[e_i].id,
                start=start_t,
                end=end_t,
                hook=str(item.get("hook", "")).strip(),
                overlay_title=str(item.get("overlay_title", "")).strip() or "Momentazo en directo",
                post_title=str(item.get("post_title", "")).strip() or "NO PUEDE SER ESTO 💀",
                hashtags=[str(h).lstrip("#").strip().lower() for h in (item.get("hashtags") or []) if str(h).strip()],
                emphasis_words=[str(w).strip() for w in (item.get("emphasis_words") or []) if str(w).strip()],
                emojis=emojis,
                llm_score=llm_score,
                signal_score=sig_score,
                final_score=combined,
                reason=str(item.get("reason", "")).strip(),
                reaction_peaks=r_peaks,
            )
        )

    return dedupe_clips(resolved)
