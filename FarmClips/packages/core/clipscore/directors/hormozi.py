"""EditPlan director: combines STT words, LLM curation, MediaPipe trajectory, signals, and hormozi-gaming preset."""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
from clipseditplan import (
    AudioPlan,
    CaptionGroup,
    CaptionsPlan,
    CaptionWord,
    CropKeyframe,
    EditPlan,
    EmojiCue,
    GameplayCropKeyframe,
    LayoutEvent,
    OutputPlan,
    OverlayItem,
    SfxCue,
    SourcePlan,
)
from clipsstyles import StylePreset, normalize_emoji_id

from ..domain import CuratedClip, FaceTrajectory, SignalSeries, SilenceSpan, TranscriptWord, Utterance
from ..framing import build_base_camera_keyframes
from ..signals import snap_word_starts_to_attack

PUNCT_CLEAN_RE = re.compile(r"[^\wáéíóúüñÁÉÍÓÚÜÑ]+", re.UNICODE)


def _clean_token(tok: str) -> str:
    return PUNCT_CLEAN_RE.sub("", tok).lower()


def compute_jump_cut_ranges(
    clip_start: float,
    clip_end: float,
    words: Sequence[TranscriptWord],
    silences: Sequence[SilenceSpan],
    signals: Optional[SignalSeries],
    preset: StylePreset,
) -> List[Tuple[float, float]]:
    """Cut silences > 0.7s leaving 0.15s margin, NEVER cutting during laughter/screams."""
    min_sil = preset.cuts.min_silence_sec
    margin = preset.cuts.margin_sec
    protect_reactions = preset.cuts.never_cut_laughter_or_scream

    # Derive silence gaps from both FFmpeg silencedetect AND word gaps inside [clip_start, clip_end]
    candidate_gaps: List[Tuple[float, float]] = []
    for s in silences:
        a = max(clip_start, s.start)
        b = min(clip_end, s.end)
        if b - a >= min_sil:
            candidate_gaps.append((a, b))

    clip_words = [w for w in words if w.end > clip_start and w.start < clip_end]
    for i in range(len(clip_words) - 1):
        g_a = max(clip_start, clip_words[i].end)
        g_b = min(clip_end, clip_words[i + 1].start)
        if g_b - g_a >= min_sil:
            candidate_gaps.append((g_a, g_b))

    if not candidate_gaps:
        return [(round(clip_start, 3), round(clip_end, 3))]

    # Merge overlapping gaps
    candidate_gaps.sort()
    merged: List[Tuple[float, float]] = []
    for a, b in candidate_gaps:
        if merged and a <= merged[-1][1] + 0.05:
            merged[-1] = (merged[-1][0], max(merged[-1][1], b))
        else:
            merged.append((a, b))

    # Filter out gaps where streamer is laughing/screaming (high mic burst/reaction)
    cuts_to_remove: List[Tuple[float, float]] = []
    for a, b in merged:
        cut_a = a + margin
        cut_b = b - margin
        if cut_b - cut_a < 0.20:
            continue
        if protect_reactions and signals is not None and signals.reaction:
            lo_s = max(0, int(a))
            hi_s = min(len(signals.reaction), int(b) + 1)
            if hi_s > lo_s and max(signals.reaction[lo_s:hi_s]) >= 0.50:
                continue
        cuts_to_remove.append((round(cut_a, 3), round(cut_b, 3)))

    if not cuts_to_remove:
        return [(round(clip_start, 3), round(clip_end, 3))]

    ranges: List[Tuple[float, float]] = []
    cursor = clip_start
    for c_a, c_b in cuts_to_remove:
        if c_a - cursor >= 0.35:
            ranges.append((round(cursor, 3), round(c_a, 3)))
        cursor = c_b
    if clip_end - cursor >= 0.35:
        ranges.append((round(cursor, 3), round(clip_end, 3)))

    return ranges or [(round(clip_start, 3), round(clip_end, 3))]


def build_hormozi_captions(
    words_in_clip: Sequence[TranscriptWord],
    plan_for_mapping: EditPlan,
    emphasis_words: Sequence[str],
    emoji_suggestions: Sequence[Tuple[str, str]],
    preset: StylePreset,
) -> CaptionsPlan:
    """Group words into 1-3 words (<=14 chars), pause >0.3s or punctuation, mark emphasis & attach sparse emojis."""
    emph_set = {_clean_token(t) for phrase in emphasis_words for t in phrase.split() if _clean_token(t)}
    emoji_map: Dict[str, str] = {}
    for w_str, em_str in emoji_suggestions:
        tok = _clean_token(w_str)
        if tok:
            emoji_map[tok] = normalize_emoji_id(em_str)

    cap_cfg = preset.captions
    mapped_words: List[Tuple[CaptionWord, str]] = []
    for w in words_in_clip:
        cs = plan_for_mapping.master_to_clip_time(w.start)
        ce = plan_for_mapping.master_to_clip_time(w.end)
        if cs is None and ce is None:
            continue
        s_t = cs if cs is not None else plan_for_mapping.master_to_nearest_clip_time(w.start)
        e_t = ce if ce is not None else plan_for_mapping.master_to_nearest_clip_time(w.end)
        if e_t <= s_t:
            e_t = round(s_t + 0.08, 3)
        raw_txt = w.text.strip()
        if not raw_txt:
            continue
        clean = _clean_token(raw_txt)
        disp = raw_txt.upper() if cap_cfg.uppercase else raw_txt
        is_emph = clean in emph_set if clean else False
        mapped_words.append(
            (
                CaptionWord(
                    w=disp,
                    s=round(s_t, 3),
                    e=round(e_t, 3),
                    emphasis=True if is_emph else None,
                ),
                raw_txt,
            )
        )

    groups_raw: List[List[Tuple[CaptionWord, str]]] = []
    cur: List[Tuple[CaptionWord, str]] = []
    for cw, raw_txt in mapped_words:
        if cur:
            prev_cw, prev_raw = cur[-1]
            cand_chars = sum(len(x[0].w) for x in cur) + len(cur) + len(cw.w)
            gap = cw.s - prev_cw.e
            ended_punct = prev_raw.endswith((".", "?", "!", ",", ";", ":", "…"))
            if (
                len(cur) >= cap_cfg.max_words
                or cand_chars > cap_cfg.max_chars
                or gap > cap_cfg.pause_split_sec
                or ended_punct
            ):
                groups_raw.append(cur)
                cur = []
        cur.append((cw, raw_txt))
    if cur:
        groups_raw.append(cur)

    groups: List[CaptionGroup] = []
    last_emoji_t = -999.0
    default_emojis = ["1f525", "1f631", "1f480", "1f92f"]
    em_cycle = 0

    for g in groups_raw:
        cwords = [item[0] for item in g]
        emoji_cue: Optional[EmojiCue] = None
        emph_candidates = [cw for cw in cwords if cw.emphasis]
        target_words = emph_candidates if preset.emojis.only_on_emphasis else (emph_candidates or cwords[:1])
        if target_words:
            tw = target_words[0]
            if tw.s - last_emoji_t >= preset.emojis.max_interval_sec:
                tok = _clean_token(tw.w)
                eid = emoji_map.get(tok)
                if eid is None and tw.emphasis:
                    eid = default_emojis[em_cycle % len(default_emojis)]
                    em_cycle += 1
                if eid:
                    emoji_cue = EmojiCue(id=eid, at=tw.s)
                    last_emoji_t = tw.s
        groups.append(CaptionGroup(words=cwords, emoji=emoji_cue))

    return CaptionsPlan(preset=cap_cfg.preset, groups=groups)


def _inject_zoom_events(
    base_kfs: Sequence[Tuple[float, float, float, float]],
    impact_times_clip: Sequence[float],
    clip_dur: float,
    preset: StylePreset,
) -> Tuple[List[CropKeyframe], List[SfxCue]]:
    """Overlay impact punch-in zooms (outBack -> hold -> inOutSine) and slow setup zooms onto base face trajectory."""

    def interp_base(t: float) -> Tuple[float, float, float]:
        if t <= base_kfs[0][0]:
            return base_kfs[0][1], base_kfs[0][2], base_kfs[0][3]
        if t >= base_kfs[-1][0]:
            return base_kfs[-1][1], base_kfs[-1][2], base_kfs[-1][3]
        for i in range(len(base_kfs) - 1):
            t0, x0, y0, z0 = base_kfs[i]
            t1, x1, y1, z1 = base_kfs[i + 1]
            if t0 <= t <= t1:
                u = (t - t0) / max(1e-4, t1 - t0)
                return x0 + (x1 - x0) * u, y0 + (y1 - y0) * u, z0 + (z1 - z0) * u
        return 0.5, 0.45, 1.0

    iz = preset.impact_zoom
    in_s = iz.in_ms / 1000.0
    hold_s = iz.hold_sec
    out_s = iz.out_ms / 1000.0

    accepted_impacts: List[float] = []
    for t in sorted(impact_times_clip):
        if t < 0.25 or t > clip_dur - (in_s + hold_s + 0.2):
            continue
        if all(abs(t - prev) >= iz.min_interval_sec for prev in accepted_impacts):
            accepted_impacts.append(round(t, 3))

    # Build occupied windows from impact zooms
    occupied: List[Tuple[float, float]] = [
        (max(0.0, t - 0.05), min(clip_dur, t + in_s + hold_s + out_s + 0.05))
        for t in accepted_impacts
    ]

    kfs_by_t: Dict[float, CropKeyframe] = {}
    for t, cx, cy, bz in base_kfs:
        if not any(a < t < b for a, b in occupied):
            kfs_by_t[round(t, 3)] = CropKeyframe(t=round(t, 3), cx=round(cx, 4), cy=round(cy, 4), zoom=round(bz, 3))

    sfx_cues: List[SfxCue] = []
    for idx, t in enumerate(accepted_impacts):
        t_start = round(max(0.0, t), 3)
        t_peak = round(min(clip_dur, t_start + in_s), 3)
        t_hold = round(min(clip_dur, t_peak + hold_s), 3)
        t_end = round(min(clip_dur, t_hold + out_s), 3)

        cx0, cy0, bz0 = interp_base(t_start)
        cxp, cyp, bzp = interp_base(t_peak)
        cxh, cyh, bzh = interp_base(t_hold)
        cxe, cye, bze = interp_base(t_end)

        peak_z = round(min(3.0, bzp * iz.scale), 3)
        hold_z = round(min(3.0, bzh * iz.scale), 3)

        kfs_by_t[t_start] = CropKeyframe(t=t_start, cx=round(cx0, 4), cy=round(cy0, 4), zoom=round(bz0, 3))
        kfs_by_t[t_peak] = CropKeyframe(t=t_peak, cx=round(cxp, 4), cy=round(cyp, 4), zoom=peak_z, ease="outBack")
        kfs_by_t[t_hold] = CropKeyframe(t=t_hold, cx=round(cxh, 4), cy=round(cyh, 4), zoom=hold_z, ease="linear")
        kfs_by_t[t_end] = CropKeyframe(t=t_end, cx=round(cxe, 4), cy=round(cye, 4), zoom=round(bze, 3), ease="inOutSine")
        if idx == 0:
            sfx_cues.append(SfxCue(t=t_start, id="boom", gain_db=-6.0))

    # Add slow creep zoom (1.0 -> 1.1x) on quiet setup intervals > 5s
    sz = preset.slow_zoom
    free_boundaries = [0.0] + [b for _, b in occupied]
    free_ends = [a for a, _ in occupied] + [clip_dur]
    for seg_a, seg_b in zip(free_boundaries, free_ends):
        if seg_b - seg_a >= sz.min_setup_sec + 0.6:
            sa = round(seg_a + 0.2, 3)
            sb = round(seg_b - 0.25, 3)
            cxa, cya, bza = interp_base(sa)
            cxb, cyb, bzb = interp_base(sb)
            # Clear intermediate base points inside the slow zoom ramp for smooth continuous creep
            for k in list(kfs_by_t.keys()):
                if sa < k < sb:
                    del kfs_by_t[k]
            kfs_by_t[sa] = CropKeyframe(t=sa, cx=round(cxa, 4), cy=round(cya, 4), zoom=round(bza * sz.start_scale, 3))
            kfs_by_t[sb] = CropKeyframe(
                t=sb,
                cx=round(cxb, 4),
                cy=round(cyb, 4),
                zoom=round(min(3.0, bzb * sz.end_scale), 3),
                ease="inOutSine",
            )

    ordered = [kfs_by_t[k] for k in sorted(kfs_by_t.keys())]
    if not ordered:
        ordered = [CropKeyframe(t=0.0, cx=0.5, cy=0.45, zoom=1.0)]
    return ordered, sfx_cues


def build_editplan(
    session_id: str,
    clip: CuratedClip,
    utterances: Sequence[Utterance],
    signals: Optional[SignalSeries],
    face: Optional[FaceTrajectory],
    preset: StylePreset,
    speech_silences: Sequence[SilenceSpan] = (),
    mic_attack_100hz: Optional[np.ndarray] = None,
    mic_attack_start_sec: float = 0.0,
    source_fps: float = 60.0,
) -> EditPlan:
    """Compile all inputs into a declarative, self-contained EditPlan v2."""
    raw_words: List[TranscriptWord] = [
        w
        for u in utterances
        for w in u.words
        if w.end > clip.start and w.start < clip.end
    ]
    snapped_words = snap_word_starts_to_attack(raw_words, mic_attack_100hz, mic_attack_start_sec)

    ranges = compute_jump_cut_ranges(clip.start, clip.end, snapped_words, speech_silences, signals, preset)
    out_fps = min(preset.format.max_fps, max(24, int(round(source_fps or 60))))

    plan = EditPlan(
        version=2,
        clip_id=clip.id,
        candidate_id=clip.id,
        source=SourcePlan(session=session_id, ranges=ranges),
        output=OutputPlan(
            w=preset.format.width,
            h=preset.format.height,
            fps=out_fps,
            style=preset.id,
        ),
    )
    clip_dur = plan.total_duration()

    # 1. Resolver semantic zoom anchor guiado por IA (o fallback local)
    semantic_zoom_ct: Optional[float] = None
    if clip.zoom_word:
        clean_target = _clean_token(clip.zoom_word)
        for w in snapped_words:
            if _clean_token(w.text) == clean_target:
                ct = plan.master_to_clip_time(w.start)
                if ct is not None:
                    semantic_zoom_ct = ct
                    break

    # Layouts: base split 40/60 + camera_full 2s en las reacciones más fuertes
    layouts: List[LayoutEvent] = [LayoutEvent(t=0.0, kind="split", camera_ratio=preset.layout.camera_ratio)]
    peak_candidates = list(clip.reaction_peaks)
    if signals is not None and signals.reaction and not peak_candidates:
        lo, hi = max(0, int(clip.start)), min(len(signals.reaction), int(clip.end) + 1)
        ranked_secs = sorted(range(lo, hi), key=lambda s: signals.reaction[s], reverse=True)
        for s in ranked_secs:
            if signals.reaction[s] >= 0.55 and all(abs(s - p) >= 4.0 for p in peak_candidates):
                peak_candidates.append(float(s))
            if len(peak_candidates) >= preset.layout.camera_full_max_reactions:
                break

    cam_full_added = 0
    used_full_windows: List[Tuple[float, float]] = []

    # Si la IA indicó foco en rostro para el clímax semántico, priorizar camera_full en ese momento
    if clip.zoom_focus == "face" and semantic_zoom_ct is not None:
        f_start = round(max(preset.title.duration_sec + 0.2, semantic_zoom_ct - 0.2), 3)
        f_end = round(min(clip_dur - 0.1, f_start + preset.layout.camera_full_sec), 3)
        if f_end - f_start >= 1.0:
            layouts.append(LayoutEvent(t=f_start, kind="camera_full", until=f_end))
            used_full_windows.append((f_start, f_end))
            cam_full_added += 1

    for mp in peak_candidates:
        if cam_full_added >= preset.layout.camera_full_max_reactions:
            break
        ct = plan.master_to_clip_time(mp)
        if ct is None:
            continue
        # Si el clímax era enfocado en el gameplay, evitar tapar la pantalla con cámara completa
        if clip.zoom_focus == "game" and semantic_zoom_ct is not None and abs(ct - semantic_zoom_ct) < 2.0:
            continue
        f_start = round(max(preset.title.duration_sec + 0.2, ct - 0.3), 3)
        f_end = round(min(clip_dur - 0.1, f_start + preset.layout.camera_full_sec), 3)
        if f_end - f_start >= 1.0 and all(f_end < a - 1.0 or f_start > b + 1.0 for a, b in used_full_windows):
            layouts.append(LayoutEvent(t=f_start, kind="camera_full", until=f_end))
            used_full_windows.append((f_start, f_end))
            cam_full_added += 1
    plan.layout = sorted(layouts, key=lambda ev: (ev.t, 0 if ev.kind == "split" else 1))

    # 2. Captions + emphasis times for impact zooms
    emoji_pairs = [(e.word, e.emoji) for e in clip.emojis]
    plan.captions = build_hormozi_captions(snapped_words, plan, clip.emphasis_words, emoji_pairs, preset)

    impact_triggers: List[float] = []
    # Prioridad 1: Clímax semántico exacto guiado por zoom_word
    if semantic_zoom_ct is not None:
        impact_triggers.append(max(0.0, semantic_zoom_ct - 0.08))
    # Prioridad 2: Palabras de énfasis en subtítulos
    for g in plan.captions.groups:
        for cw in g.words:
            if cw.emphasis:
                impact_triggers.append(max(0.0, cw.s - 0.08))
    # Prioridad 3: Picos acústicos de reacción
    for mp in peak_candidates:
        ct = plan.master_to_clip_time(mp)
        if ct is not None:
            impact_triggers.append(max(0.0, ct - 0.10))

    # 3. Camera crop trajectory + impact & slow zooms
    base_kfs = build_base_camera_keyframes(face, clip_dur, plan.master_to_clip_time)
    cam_kfs, sfx_cues = _inject_zoom_events(base_kfs, impact_triggers, clip_dur, preset)
    plan.camera_crop = cam_kfs

    # Optional gameplay horizontal centroid crop if motion_cx has meaningful panning
    if signals is not None and signals.motion_cx:
        lo, hi = max(0, int(clip.start)), min(len(signals.motion_cx), int(clip.end) + 1)
        if hi > lo:
            avg_cx = round(float(np.median(signals.motion_cx[lo:hi])), 3)
            if abs(avg_cx - 0.5) >= 0.08:
                plan.gameplay_crop = [GameplayCropKeyframe(t=0.0, cx=avg_cx, cy=0.5, zoom=1.0)]

    # 4. Title overlay (first 3s at seam)
    if clip.overlay_title.strip() and preset.title.duration_sec > 0:
        plan.overlays = [
            OverlayItem(
                kind="title",
                text=clip.overlay_title.strip(),
                start=0.0,
                end=round(min(clip_dur, preset.title.duration_sec), 3),
            )
        ]

    # 5. Audio plan
    plan.audio = AudioPlan(
        mic_gain_db=preset.audio.mic_gain_db,
        duck_game_db=preset.audio.duck_game_db,
        sfx=sfx_cues,
    )
    return plan
