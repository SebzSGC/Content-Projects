"""Unit tests for styles, EditPlan v2 contract, compact timeline, phrase-ID selection, camera math, jump cuts, and ASS/FFmpeg compilers."""

from __future__ import annotations

from pathlib import Path

import numpy as np
from clipscore.directors import build_editplan, compute_jump_cut_ranges
from clipscore.domain import (
    CuratedClip,
    EmojiSuggestion,
    FaceTrajectory,
    SignalPeak,
    SignalSeries,
    SilenceSpan,
    SyncResult,
    TranscriptWord,
)
from clipscore.framing import (
    OneEuroFilter,
    apply_deadzone_series,
    fill_face_gaps,
    ramer_douglas_peucker,
)
from clipscore.selection import resolve_curated_clips
from clipscore.signals import snap_word_starts_to_attack
from clipscore.timeline import build_compact_timeline, group_words_into_utterances
from clipseditplan import EditPlan, SourcePlan, export_json_schema
from clipsrender import compile_ass, compile_ffmpeg_plan
from clipsstyles import (
    ensure_emoji_png,
    ensure_sfx_wav,
    hex_to_ass_bgr,
    load_preset,
)


def test_style_preset_and_assets(tmp_path: Path) -> None:
    preset = load_preset("hormozi-gaming")
    assert preset.id == "hormozi-gaming"
    assert preset.format.width == 1080
    assert preset.format.height == 1920
    assert preset.format.target_lufs == -14.0
    assert preset.layout.camera_ratio == 0.40
    assert preset.layout.gameplay_ratio == 0.60
    assert preset.captions.active_word.color_hex == "#FFD400"
    assert preset.captions.emphasis_word.color_hex == "#39FF14"
    assert len(preset.content_hash()) == 16

    # Verify ASS BGR conversion (#FFD400 -> R=FF, G=D4, B=00 -> &H0000D4FF&)
    assert hex_to_ass_bgr("#FFD400") == "&H0000D4FF&"
    assert hex_to_ass_bgr("#39FF14") == "&H0014FF39&"

    png = ensure_emoji_png("1f525", cache_dir=tmp_path / "emojis")
    assert png.is_file() and png.stat().st_size > 200

    wav = ensure_sfx_wav("boom", cache_dir=tmp_path / "sfx")
    assert wav.is_file() and wav.stat().st_size > 1000


def test_editplan_timeline_mapping_and_schema(tmp_path: Path) -> None:
    plan = EditPlan(
        clip_id="clip_test",
        source=SourcePlan(session="ses_1", ranges=[(10.0, 15.0), (16.5, 21.5)]),
    )
    assert plan.total_duration() == 10.0
    assert plan.master_to_clip_time(12.0) == 2.0
    # Inside jump-cut removed gap [15.0..16.5] -> None
    assert plan.master_to_clip_time(15.8) is None
    # After jump-cut gap: 17.5 master -> 5.0 + (17.5 - 16.5) = 6.0 clip time
    assert plan.master_to_clip_time(17.5) == 6.0
    assert plan.clip_to_master_time(6.0) == (1, 17.5)

    h1 = plan.plan_hash(style_hash="abc123", quality="final")
    h2 = plan.plan_hash(style_hash="abc123", quality="final")
    h_draft = plan.plan_hash(style_hash="abc123", quality="draft")
    assert h1 == h2
    assert h1 != h_draft

    schema_out = export_json_schema(tmp_path / "editplan.schema.json")
    assert schema_out.is_file()


def test_compact_timeline_and_phrase_id_resolution() -> None:
    words = []
    # Build 8 utterances (~4s each, spaced by 0.8s -> ~38s total)
    cursor = 2.0
    for u_idx in range(8):
        for w_idx, tok in enumerate(["Jugada", "increíble", "número", f"{u_idx + 1}."]):
            ws = round(cursor + w_idx * 0.75, 3)
            we = round(ws + 0.60, 3)
            words.append(TranscriptWord(text=tok, start=ws, end=we, prob=0.99))
        cursor += 4.2

    utts = group_words_into_utterances(words)
    assert len(utts) == 8
    assert utts[0].id == "u0001"
    assert utts[-1].id == "u0008"

    signals = SignalSeries(
        duration=45.0,
        mic_rms=[0.5] * 45,
        game_rms=[0.4] * 45,
        excitement=[0.7] * 45,
        reaction=[0.8 if i == 18 else 0.2 for i in range(45)],
        peaks=[SignalPeak(t=18.0, score=0.92, mic=0.88, game=0.65)],
    )

    compact = build_compact_timeline(utts, signals)
    assert "u0001 [0:02] Jugada increíble número 1." in compact
    assert ">>> PICO [0:18]" in compact
    # Ensure individual word decimal timestamps are NOT leaked into LLM prompt
    assert "2.75" not in compact

    # LLM proposes a too-short span (u0003..u0004 ~7.2s) -> resolver expands along utterance boundaries to >= 20s!
    proposals = [
        {
            "start_id": "u0003",
            "end_id": "u0004",
            "hook": "Jugada increíble",
            "overlay_title": "Ronda perfecta en torneo",
            "post_title": "HICE ESTO EN VIVO 🔥",
            "hashtags": ["#Gaming", "Clutch"],
            "emphasis_words": ["increíble"],
            "emojis": [{"word": "increíble", "emoji": "1f525"}],
            "score": 85,
            "reason": "Gran reacción.",
        },
        # Overlapping duplicate with lower score -> deduped
        {
            "start_id": "u0003",
            "end_id": "u0005",
            "hook": "Duplicado",
            "overlay_title": "Duplicado",
            "post_title": "DUPLICADO 💀",
            "hashtags": ["gaming"],
            "emphasis_words": [],
            "emojis": [],
            "score": 62,
            "reason": "Solapado.",
        },
    ]
    curated = resolve_curated_clips(proposals, utts, signals, vod_duration=45.0, min_sec=20.0, max_sec=60.0)
    assert len(curated) == 1
    assert 20.0 <= curated[0].duration <= 60.0
    assert curated[0].hashtags == ["gaming", "clutch"]
    assert curated[0].final_score > 60.0


def test_word_attack_snapping_and_parquet_roundtrip(tmp_path: Path) -> None:
    # Simulate a sharp voice attack at t = 5.04s while STT reported word start = 5.11s (+70ms late)
    attack = np.zeros(300, dtype=np.float32)  # 3.0s at 100 Hz starting at t=4.0s
    attack[104] = 0.95  # index 104 -> 4.0 + 1.04 = 5.04s
    words = [TranscriptWord(text="fuego", start=5.11, end=5.48, prob=0.95)]
    snapped = snap_word_starts_to_attack(words, attack, env_start_sec=4.0, max_shift_sec=0.12)
    assert abs(snapped[0].start - 5.04) <= 0.015
    assert snapped[0].end == 5.48

    sig = SignalSeries(duration=5.0, mic_rms=[0.1, 0.5, 0.9, 0.3, 0.2], excitement=[0.2, 0.6, 0.95, 0.4, 0.1])
    pq = tmp_path / "sig.parquet"
    sig.to_parquet(pq)
    loaded = SignalSeries.from_parquet(pq)
    assert loaded.excitement == sig.excitement


def test_camera_gap_fill_one_euro_deadzone_and_rdp() -> None:
    # 15 fps over 4 seconds (60 samples):
    # - [0.5..1.0s] (0.5s <= 1s gap) -> linear interpolation between 0.25 and 0.35
    # - [1.8..3.3s] (1.5s > 1s gap)  -> eases back toward center (0.50)
    fps = 15.0
    t = [round(i / fps, 3) for i in range(60)]
    present = []
    cx = []
    cy = []
    sz = []
    for ti in t:
        if 0.5 <= ti <= 1.0 or 1.8 <= ti <= 3.3:
            present.append(False)
            cx.append(0.0)
        elif ti < 0.5:
            present.append(True)
            cx.append(0.25)
        else:
            present.append(True)
            cx.append(0.35)
        cy.append(0.42)
        sz.append(0.32)

    gx, _, _ = fill_face_gaps(t, present, cx, cy, sz)
    mid_short_idx = t.index(0.733)
    assert 0.27 < gx[mid_short_idx] < 0.33  # interpolated across <1s gap!
    mid_long_idx = t.index(2.6)
    assert abs(gx[mid_long_idx] - 0.50) < 0.03  # returned to center on >1s gap!

    # One Euro + deadzone suppress tiny jitter completely
    filt = OneEuroFilter(min_cutoff=0.8, beta=0.35)
    jitter = [0.50 + (0.008 if i % 2 == 0 else -0.008) for i in range(30)]
    sm = [filt(i / 15.0, v) for i, v in enumerate(jitter)]
    dz_x, _ = apply_deadzone_series(sm, [0.45] * 30, deadzone_x=0.04)
    assert len(set(dz_x)) == 1  # Zero camera shake during micro-jitter!

    # RDP compresses collinear points to endpoints while keeping true peaks
    pts = [(i * 0.1, 0.5, 0.45, 1.0 + (0.35 if i == 10 else 0.0)) for i in range(21)]
    simplified = ramer_douglas_peucker(pts, epsilon=0.02)
    assert 3 <= len(simplified) <= 5
    assert any(abs(p[3] - 1.35) < 1e-6 for p in simplified)


def test_jump_cuts_scream_protection_and_compilers(tmp_path: Path) -> None:
    preset = load_preset("hormozi-gaming")
    words = [
        TranscriptWord(text="primero", start=10.0, end=10.6),
        # Silence 1: [10.6 .. 12.0] = 1.4s quiet -> MUST BE CUT
        TranscriptWord(text="segundo", start=12.0, end=12.6),
        # Silence 2: [12.6 .. 14.2] = 1.6s, BUT streamer is laughing/screaming at t=13 -> MUST NOT BE CUT!
        TranscriptWord(text="remate", start=14.2, end=15.0),
    ]
    reaction = [0.1] * 20
    reaction[13] = 0.92  # Scream/laugh during second gap
    signals = SignalSeries(duration=20.0, reaction=reaction, excitement=reaction)

    ranges = compute_jump_cut_ranges(10.0, 15.5, words, [], signals, preset)
    # Only the first silence [10.75..11.85] is cut -> 2 ranges, and t=13.3 remains intact inside range 2!
    assert len(ranges) == 2
    assert ranges[0] == (10.0, 10.75)
    assert ranges[1][0] == 11.85 and ranges[1][1] == 15.5

    # Full EditPlan + ASS + FFmpeg filtergraph compilation check
    utt = group_words_into_utterances(words)
    clip = CuratedClip(
        id="clip_u1",
        start_id=utt[0].id,
        end_id=utt[-1].id,
        start=10.0,
        end=15.5,
        hook="primero",
        overlay_title="Risa épica en directo",
        post_title="ME MORÍ DE RISA 😂",
        hashtags=["gaming"],
        emphasis_words=["segundo"],
        emojis=[EmojiSuggestion(word="segundo", emoji="1f525")],
        llm_score=88,
        signal_score=0.8,
        final_score=85.6,
        reason="Test",
        reaction_peaks=[13.0],
    )
    face = FaceTrajectory(
        fps=15.0,
        width=640,
        height=360,
        master_start=9.0,
        master_end=16.0,
        t_master=[9.0 + i * 0.2 for i in range(35)],
        present=[True] * 35,
        cx=[0.52] * 35,
        cy=[0.43] * 35,
        size=[0.33] * 35,
        confidence=[0.9] * 35,
    )
    plan = build_editplan("ses_1", clip, utt, signals, face, preset)
    assert any(ev.kind == "camera_full" for ev in plan.layout)
    assert any(kf.ease == "outBack" for kf in plan.camera_crop)
    assert len(plan.overlays) == 1

    ass_txt = compile_ass(plan, preset, 1080, 1920)
    assert "\\fscx115\\fscy115" in ass_txt
    assert "&H0000D4FF&" in ass_txt  # #FFD400 active word
    assert "&H0014FF39&" in ass_txt  # #39FF14 emphasis word

    ass_file = tmp_path / "test.ass"
    ass_file.write_text(ass_txt, encoding="utf-8")
    compiled = compile_ffmpeg_plan(
        plan=plan,
        preset=preset,
        gameplay_path="game.mp4",
        camera_path="cam.mp4",
        sync=SyncResult(shift_sec=0.4, scale=1.0, method="audio_xcorr", confidence=0.9),
        ass_path=ass_file,
        quality="final",
        clean_game_audio_stream=1,
    )
    assert "eval=frame" in compiled.filtergraph
    assert "sidechaincompress" in compiled.filtergraph
    assert "loudnorm=I=-14.0" in compiled.filtergraph
