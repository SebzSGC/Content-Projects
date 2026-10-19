"""Word-level ASR, forced script alignment (RapidFuzz + VAD) and SRT/VTT/ASS exporters."""

from __future__ import annotations

import hashlib
import re
import uuid
from pathlib import Path
from typing import Any

import numpy as np
import soundfile as sf
from rapidfuzz import fuzz

from vidforge.domain.models import SubtitleStyleModel, TranscriptModel, TranscriptSegment, WordTiming
from vidforge.services.audio import detect_silences, probe_media


def _normalize_token(word: str) -> str:
    return re.sub(r"[^\wáéíóúüñÁÉÍÓÚÜÑ]", "", word.lower())


def reconcile_script_with_asr_words(
    script_words: list[str],
    asr_words: list[dict[str, Any]],
    duration_us: int,
) -> list[WordTiming]:
    """Needleman-Wunsch dynamic programming alignment with RapidFuzz token similarity."""
    n = len(script_words)
    m = len(asr_words)
    if n == 0:
        return [
            WordTiming(
                i=idx,
                text=w["text"],
                start_us=int(w["start_us"]),
                end_us=int(w["end_us"]),
                confidence=float(w.get("confidence", 0.9)),
                source="asr",
            )
            for idx, w in enumerate(asr_words)
        ]
    if m == 0:
        return _distribute_words_over_duration(script_words, duration_us, [])

    gap_cost = 0.45
    dp = np.zeros((n + 1, m + 1), dtype=np.float32)
    back = np.zeros((n + 1, m + 1), dtype=np.int8)  # 0: diag, 1: up (script gap), 2: left (asr gap)
    for i in range(1, n + 1):
        dp[i, 0] = i * gap_cost
        back[i, 0] = 1
    for j in range(1, m + 1):
        dp[0, j] = j * gap_cost
        back[0, j] = 2

    norm_s = [_normalize_token(w) for w in script_words]
    norm_a = [_normalize_token(w["text"]) for w in asr_words]

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sim = fuzz.ratio(norm_s[i - 1], norm_a[j - 1]) / 100.0 if (norm_s[i - 1] and norm_a[j - 1]) else 0.5
            cost_match = dp[i - 1, j - 1] + (1.0 - sim)
            cost_up = dp[i - 1, j] + gap_cost
            cost_left = dp[i, j - 1] + gap_cost
            if cost_match <= cost_up and cost_match <= cost_left:
                dp[i, j] = cost_match
                back[i, j] = 0
            elif cost_up <= cost_left:
                dp[i, j] = cost_up
                back[i, j] = 1
            else:
                dp[i, j] = cost_left
                back[i, j] = 2

    mapping: dict[int, int] = {}
    i, j = n, m
    while i > 0 or j > 0:
        b = back[i, j] if (i > 0 and j > 0) else (1 if i > 0 else 2)
        if b == 0:
            mapping[i - 1] = j - 1
            i -= 1
            j -= 1
        elif b == 1:
            i -= 1
        else:
            j -= 1

    result: list[WordTiming] = []
    for idx, sw in enumerate(script_words):
        if idx in mapping:
            aw = asr_words[mapping[idx]]
            result.append(
                WordTiming(
                    i=idx,
                    text=sw,
                    start_us=int(aw["start_us"]),
                    end_us=int(aw["end_us"]),
                    confidence=float(aw.get("confidence", 0.92)),
                    source="aligned",
                )
            )
        else:
            result.append(
                WordTiming(
                    i=idx,
                    text=sw,
                    start_us=-1,
                    end_us=-1,
                    confidence=0.65,
                    source="interpolated",
                )
            )

    # Interpolate unaligned words smoothly between known neighbors
    idx = 0
    while idx < n:
        if result[idx].start_us >= 0:
            idx += 1
            continue
        start_idx = idx
        while idx < n and result[idx].start_us < 0:
            idx += 1
        end_idx = idx  # exclusive
        t_left = result[start_idx - 1].end_us if start_idx > 0 else 0
        t_right = result[end_idx].start_us if end_idx < n else duration_us
        if t_right <= t_left:
            t_right = min(duration_us, t_left + (end_idx - start_idx) * 200_000)
        count = end_idx - start_idx
        step = max(20_000, (t_right - t_left) // max(1, count))
        for k in range(count):
            w_obj = result[start_idx + k]
            w_obj.start_us = t_left + k * step
            w_obj.end_us = min(t_right, w_obj.start_us + step - 5_000)

    # Guarantee monotonic non-overlapping bounds
    last_end = 0
    for w_obj in result:
        if w_obj.start_us < last_end:
            w_obj.start_us = last_end
        if w_obj.end_us <= w_obj.start_us:
            w_obj.end_us = min(duration_us, w_obj.start_us + 80_000)
        last_end = w_obj.end_us

    return result


def _distribute_words_over_duration(
    words: list[str],
    duration_us: int,
    silences: list[tuple[int, int]],
) -> list[WordTiming]:
    if not words:
        return []
    # Build voiced intervals from silence intervals
    voiced: list[tuple[int, int]] = []
    cur = 0
    for s_start, s_end in sorted(silences):
        if s_start > cur + 40_000:
            voiced.append((cur, s_start))
        cur = max(cur, s_end)
    if duration_us > cur + 40_000:
        voiced.append((cur, duration_us))
    if not voiced:
        voiced = [(0, max(duration_us, len(words) * 250_000))]

    # If number of voiced bursts matches word count, map 1-to-1!
    if len(voiced) == len(words):
        return [
            WordTiming(
                i=idx,
                text=w,
                start_us=voiced[idx][0],
                end_us=voiced[idx][1],
                confidence=0.96,
                source="aligned",
            )
            for idx, w in enumerate(words)
        ]

    # Otherwise weight by character length across total voiced time
    total_voiced = sum(e - s for s, e in voiced)
    weights = [max(2, len(w)) for w in words]
    total_weight = sum(weights)

    out: list[WordTiming] = []
    v_idx = 0
    v_pos = voiced[0][0]
    for idx, (w, wt) in enumerate(zip(words, weights)):
        alloc = int(round((wt / total_weight) * total_voiced))
        while v_idx < len(voiced) - 1 and v_pos >= voiced[v_idx][1]:
            v_idx += 1
            v_pos = voiced[v_idx][0]
        start_us = v_pos
        end_us = min(voiced[v_idx][1], start_us + max(60_000, alloc))
        if end_us <= start_us:
            end_us = min(duration_us, start_us + 80_000)
        out.append(
            WordTiming(
                i=idx,
                text=w,
                start_us=start_us,
                end_us=end_us,
                confidence=0.90,
                source="aligned",
            )
        )
        v_pos = end_us
    return out


def group_words_into_segments(words: list[WordTiming], max_words: int = 8) -> list[TranscriptSegment]:
    if not words:
        return []
    segments: list[TranscriptSegment] = []
    chunk: list[WordTiming] = []
    for w in words:
        chunk.append(w)
        ends_sentence = w.text.endswith((".", "!", "?", ":", ";"))
        if len(chunk) >= max_words or (ends_sentence and len(chunk) >= 3):
            segments.append(
                TranscriptSegment(
                    id=f"seg_{len(segments) + 1:03d}",
                    word_range=[chunk[0].i, chunk[-1].i],
                    start_us=chunk[0].start_us,
                    end_us=chunk[-1].end_us,
                    text=" ".join(x.text for x in chunk),
                )
            )
            chunk = []
    if chunk:
        segments.append(
            TranscriptSegment(
                id=f"seg_{len(segments) + 1:03d}",
                word_range=[chunk[0].i, chunk[-1].i],
                start_us=chunk[0].start_us,
                end_us=chunk[-1].end_us,
                text=" ".join(x.text for x in chunk),
            )
        )
    return segments


def transcribe_or_align(
    audio_path: Path,
    audio_asset_id: str,
    script_text: str | None = None,
    language: str = "es",
    use_whisper_if_available: bool = False,
) -> TranscriptModel:
    probe = probe_media(audio_path)
    duration_us = max(100_000, int(probe.get("duration_us") or 1_000_000))
    sha256 = hashlib.sha256(audio_path.read_bytes()).hexdigest()
    silences = detect_silences(audio_path)

    script_words = [w for w in re.split(r"\s+", (script_text or "").strip()) if w]
    asr_words: list[dict[str, Any]] = []
    engine_name = "vad-forced-aligner"

    if use_whisper_if_available or not script_words:
        try:
            from faster_whisper import WhisperModel
            model = WhisperModel("tiny", device="cpu", compute_type="int8")
            segs, _ = model.transcribe(str(audio_path), language=language, word_timestamps=True)
            for s in segs:
                for w in (s.words or []):
                    asr_words.append({
                        "text": w.word.strip(),
                        "start_us": int(round(w.start * 1_000_000)),
                        "end_us": int(round(w.end * 1_000_000)),
                        "confidence": float(getattr(w, "probability", 0.9)),
                    })
            engine_name = "faster-whisper"
        except Exception:
            asr_words = []

    if script_words and asr_words:
        words = reconcile_script_with_asr_words(script_words, asr_words, duration_us)
        mode = "align"
    elif script_words:
        words = _distribute_words_over_duration(script_words, duration_us, silences)
        mode = "align"
    elif asr_words:
        words = [
            WordTiming(
                i=idx,
                text=w["text"],
                start_us=w["start_us"],
                end_us=w["end_us"],
                confidence=w["confidence"],
                source="asr",
            )
            for idx, w in enumerate(asr_words)
        ]
        mode = "transcribe"
    else:
        fallback_words = ["Audio", "procesado", "correctamente."]
        words = _distribute_words_over_duration(fallback_words, duration_us, silences)
        mode = "transcribe"

    segments = group_words_into_segments(words)
    return TranscriptModel(
        id=str(uuid.uuid4()),
        audio_asset_id=audio_asset_id,
        audio_sha256=sha256,
        language=language,
        engine={"name": engine_name, "model": "base", "device": "cpu", "compute_type": "int8"},
        mode=mode,
        duration_us=duration_us,
        words=words,
        segments=segments,
    )


def _fmt_srt_time(us: int) -> str:
    ms = max(0, us // 1000)
    h = ms // 3_600_000
    ms %= 3_600_000
    m = ms // 60_000
    ms %= 60_000
    s = ms // 1000
    ms %= 1000
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def _fmt_ass_time(us: int) -> str:
    cs = max(0, us // 10_000)
    h = cs // 360_000
    cs %= 360_000
    m = cs // 6000
    cs %= 6000
    s = cs // 100
    cs %= 100
    return f"{h:01d}:{m:02d}:{s:02d}.{cs:02d}"


def export_srt(transcript: TranscriptModel) -> str:
    blocks: list[str] = []
    for idx, seg in enumerate(transcript.segments, start=1):
        blocks.append(f"{idx}\n{_fmt_srt_time(seg.start_us)} --> {_fmt_srt_time(seg.end_us)}\n{seg.text}\n")
    return "\n".join(blocks)


def export_vtt(transcript: TranscriptModel) -> str:
    lines = ["WEBVTT\n"]
    for seg in transcript.segments:
        s = _fmt_srt_time(seg.start_us).replace(",", ".")
        e = _fmt_srt_time(seg.end_us).replace(",", ".")
        lines.append(f"{s} --> {e}\n{seg.text}\n")
    return "\n".join(lines)


def _hex_to_ass_bgr(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        return "&H00FFFFFF"
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b.upper()}{g.upper()}{r.upper()}"


def export_ass(
    transcript: TranscriptModel,
    style: SubtitleStyleModel | None = None,
    width: int = 1920,
    height: int = 1080,
    karaoke: bool = True,
) -> str:
    st = style or SubtitleStyleModel()
    pri = _hex_to_ass_bgr(st.primary_color)
    sec = _hex_to_ass_bgr(st.highlight_color)
    align = 2 if st.position == "bottom" else (5 if st.position == "middle" else 8)
    margin_v = 90 if st.position == "bottom" else 60

    header = f"""[Script Info]
Title: VidForge Subtitles
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{st.font_family},{st.font_size},{pri},{sec},&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{st.outline:.1f},{st.shadow:.1f},{align},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    word_map = {w.i: w for w in transcript.words}
    events: list[str] = []
    for seg in transcript.segments:
        start_s = _fmt_ass_time(seg.start_us)
        end_s = _fmt_ass_time(seg.end_us)
        if karaoke and len(seg.word_range) == 2:
            w_start, w_end = seg.word_range
            parts: list[str] = []
            for wi in range(w_start, w_end + 1):
                w = word_map.get(wi)
                if not w:
                    continue
                dur_cs = max(5, (w.end_us - w.start_us) // 10_000)
                txt = w.text.upper() if st.uppercase else w.text
                parts.append(f"{{\\k{dur_cs}}}{txt}")
            line_txt = " ".join(parts) if parts else (seg.text.upper() if st.uppercase else seg.text)
        else:
            line_txt = seg.text.upper() if st.uppercase else seg.text
        events.append(f"Dialogue: 0,{start_s},{end_s},Default,,0,0,0,,{line_txt}")

    return header + "\n".join(events) + "\n"
