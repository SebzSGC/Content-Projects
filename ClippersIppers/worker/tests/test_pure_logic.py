"""Tests for the pure modules (no ML stack, no FFmpeg needed)."""

from __future__ import annotations

from gameclips.domain import (
    FaceTrack,
    OcrLine,
    PixelRect,
    Rect,
    RenderOptions,
    SignalTimeline,
    Speaker,
    SyncResult,
    Utterance,
    Word,
)
from gameclips.ingest.kick import is_kick_url, kick_kind
from gameclips.render import ass, compose, framing
from gameclips.selection import candidates as cand
from gameclips.signals import build_timeline, find_peaks, robust_norm
from gameclips.speakers import label_speakers


def utt(uid, start, end, text, speaker=Speaker.UNKNOWN):
    words = []
    tokens = text.split()
    step = (end - start) / max(1, len(tokens))
    for i, tok in enumerate(tokens):
        words.append(Word(tok, start + i * step, start + (i + 1) * step))
    return Utterance(id=uid, start=start, end=end, text=text, words=words, speaker=speaker)


# --- Kick ---------------------------------------------------------------------


def test_kick_urls():
    assert kick_kind("https://kick.com/streamer/videos/0d3f2a1b-1c2d-4e5f-8a9b-0c1d2e3f4a5b") == "vod"
    assert kick_kind("https://kick.com/streamer/clips/clip_01ABCDEF") == "clip"
    assert kick_kind("https://kick.com/streamer?clip=clip_01ABCDEF") == "clip"
    assert not is_kick_url("https://www.youtube.com/watch?v=abc")


# --- Sync mapping ---------------------------------------------------------------


def test_sync_camera_time():
    s = SyncResult(shift_sec=-1.5, scale=1.0001)
    assert abs(s.camera_time(100.0) - (100.01 - 1.5)) < 1e-9


# --- Speakers -------------------------------------------------------------------


def _face_with_mouth(talking_ranges, duration=40.0, fps=10.0):
    n = int(duration * fps)
    track = FaceTrack(fps=fps, width=640, height=480)
    for i in range(n):
        t = i / fps
        talking = any(a <= t < b for a, b in talking_ranges)
        track.t.append(t)
        track.present.append(True)
        track.cx.append(0.5)
        track.cy.append(0.4)
        track.size.append(0.3)
        track.jaw_open.append((0.5 if i % 2 else 0.05) if talking else 0.05 + 0.005 * (i % 2))
        track.smile.append(0.1)
        track.surprise.append(0.1)
    return track


def test_mouth_activity_labels_streamer_and_game():
    utts = [utt("a", 2, 6, "bueno hermanita ponte el cinturón"), utt("b", 10, 13, "dile que avance lentamente")]
    face = _face_with_mouth([(2, 6)])
    out = label_speakers(utts, 40.0, face, SyncResult(), {}, [])
    by_id = {u.id: u for u in out}
    assert by_id["a"].speaker == Speaker.STREAMER
    assert by_id["b"].speaker == Speaker.GAME


def test_ocr_marks_game_and_adds_missing_lines():
    utts = [utt("a", 10, 13, "Dile que se abroche el cinturón")]
    ocr = [OcrLine(10.2, 13.0, "¡Dile que se abroche el cinturón!"), OcrLine(20.0, 22.0, "¡Cuidado con el poste!")]
    out = label_speakers(utts, 40.0, None, SyncResult(), {}, ocr)
    assert out[0].speaker == Speaker.GAME
    assert len(out) == 2 and out[1].source == "ocr" and out[1].speaker == Speaker.GAME


# --- Signals --------------------------------------------------------------------


def test_robust_norm_highlights_outliers():
    values = [0.1] * 50 + [0.9]
    norm = robust_norm(values)
    assert norm[-1] > 0.9 and max(norm[:-1]) < 0.2


def test_find_peaks_respects_distance():
    values = [0.0] * 100
    values[10], values[15], values[60] = 0.9, 0.8, 0.7
    assert find_peaks(values, 0.5, 20, 10) == [10, 60]


def test_build_timeline_reaction_peak():
    n = 120
    laughter = [0.02] * n
    laughter[50] = laughter[51] = 0.95
    game = [0.05] * n
    game[46] = 0.9
    tl = build_timeline(float(n), {"laughter": laughter, "scream": [0.0] * n, "game_events": game}, [-30.0] * n, {}, None, SyncResult())
    assert tl.peaks and abs(tl.peaks[0]["t"] - 50) <= 2
    assert tl.series["excitement"][50] > tl.series["excitement"][20]


# --- Candidates -----------------------------------------------------------------


def test_time_format_roundtrip():
    assert cand.parse_time(cand.fmt_time(3725.4)) == 3725.4
    assert cand.parse_time("12:04.2") == 724.2


def test_snap_to_utterances_never_cuts_mid_sentence():
    utts = [utt("a", 10, 14, "uno dos tres"), utt("b", 15, 19, "cuatro cinco"), utt("c", 40, 44, "seis siete")]
    a, b = cand.snap_to_utterances(11.0, 17.0, utts, 100.0, min_len=5, max_len=90)
    assert a == 9.7 and b == 20.5


def test_snap_extends_short_clips():
    utts = [utt("a", 10, 12, "hola"), utt("b", 20, 30, "algo largo"), utt("c", 31, 40, "remate")]
    a, b = cand.snap_to_utterances(10, 12, utts, 100.0, min_len=20, max_len=90)
    assert b - a >= 20


def test_build_windows_overlap_and_peaks():
    utts = [utt(str(i), i * 30, i * 30 + 5, f"linea {i}", Speaker.STREAMER) for i in range(80)]
    tl = SignalTimeline(duration=2400, peaks=[{"t": 100.0, "score": 0.8, "laughter": 0.9, "scream": 0, "face": 0.7, "game": 0}])
    windows = cand.build_windows(utts, tl, 2400, window_sec=900, overlap_sec=120)
    assert len(windows) == 3
    assert windows[1][0] == 780
    assert "PICO DE REACCION" in windows[0][2] and "STREAMER" in windows[0][2]


def test_dedupe_keeps_best():
    from gameclips.domain import Candidate

    c1 = Candidate("1", 10, 50, "a", "A", final_score=80)
    c2 = Candidate("2", 15, 55, "b", "B", final_score=70)
    c3 = Candidate("3", 100, 140, "c", "C", final_score=60)
    assert [c.id for c in cand.dedupe([c2, c1, c3])] == ["1", "3"]


# --- Framing --------------------------------------------------------------------


def test_camera_crop_stays_inside_region_and_keeps_aspect():
    region = PixelRect(100, 50, 640, 360)
    aspect = 1080 / 768
    crop = framing.camera_crop(region, aspect, (0.95, 0.1, 0.25))
    assert crop.x >= region.x and crop.y >= region.y
    assert crop.x + crop.w <= region.x + region.w and crop.y + crop.h <= region.y + region.h
    assert abs(crop.w / crop.h - aspect) < 0.02
    assert crop.w % 2 == 0 and crop.h % 2 == 0


def test_gameplay_crop_centered():
    crop = framing.gameplay_crop(PixelRect(0, 0, 1920, 1080), 1080 / 1152)
    assert crop.h == 1080 and abs((crop.x + crop.w / 2) - 960) <= 2


def test_rect_to_pixels_is_even_and_clamped():
    px = Rect(0.7, 0.0, 0.5, 0.33).to_pixels(1920, 1080)
    assert px.x + px.w <= 1920 and px.w % 2 == 0 and px.h % 2 == 0


# --- ASS ------------------------------------------------------------------------


def test_ass_title_and_captions():
    utts = [
        utt("a", 100, 102, "bueno hermanita ponte el cinturón", Speaker.STREAMER),
        utt("b", 103, 105, "dile que avance", Speaker.GAME),
    ]
    text = ass.build_ass(99.0, 130.0, utts, "Enseñándole a mi hermana a conducir", RenderOptions(), 768, 768, 1152, "Montserrat", "Montserrat")
    assert "Enseñándole a mi\\Nhermana a conducir" in text
    assert "Style: Title" in text and "\\pos(540,768)" in text
    assert "HERMANITA" in text  # streamer captions
    assert "dile que avance" not in text  # game lines hidden in "streamer" mode
    text_all = ass.build_ass(99.0, 130.0, utts, "x", RenderOptions(captions="all"), 768, 768, 1152, "M", "M")
    assert ",Game,," in text_all


def test_ass_escape_and_time():
    assert ass.escape("{\\b1}hola\n") == "(b1)hola"
    assert ass.ass_time(3725.999) == "1:02:06.00"


# --- Compose --------------------------------------------------------------------


def _spec(split: bool, punch: bool):
    return compose.ComposeSpec(
        split_mode=split,
        duration=42.0,
        gameplay_path="C:\\vods\\game.mkv",
        gameplay_seek=100.0,
        camera_path="/vods/cam.mkv" if split else None,
        camera_seek=99.5,
        camera_scale=1.0001,
        camera_lead_pad=0.0,
        camera_crop=PixelRect(10, 20, 640, 456),
        camera_zoom_crop=PixelRect(100, 80, 474, 338) if punch else None,
        punch_window=(10.0, 11.8) if punch else None,
        gameplay_crop=PixelRect(454, 0, 1012, 1080),
        camera_height=768,
        gameplay_height=1152,
        fps=60,
        ass_path="C:\\data\\clips\\c's.ass",
        fonts_dir=None,
        options=RenderOptions(),
    )


def test_filtergraph_split_with_punch_in():
    graph = compose.build_filtergraph(_spec(True, True))
    assert "[0:v]setpts=(PTS-STARTPTS)/1.000100[camsrc]" in graph
    assert "overlay=0:0:enable='between(t,10.00,11.80)'" in graph
    assert "[cam][game]vstack=inputs=2" in graph
    assert "[1:a]" in graph and "loudnorm=I=-14" in graph
    assert "subtitles='C\\:/data/clips/c\\'s.ass'" in graph


def test_args_composite_single_input():
    args = compose.build_args(_spec(False, False), ["-c:v", "libx264"], __import__("pathlib").Path("out.mp4"))
    assert args.count("-i") == 1
    graph = args[args.index("-filter_complex") + 1]
    assert "split=2[camsrc][gamesrc]" in graph and "[0:a]" in graph


# --- LLM providers ----------------------------------------------------------------


def _reset_provider(monkey_env):
    import os

    from gameclips.config import get_settings
    from gameclips.selection import providers

    for k, v in monkey_env.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    get_settings.cache_clear()
    providers.get_provider.cache_clear()
    return providers


def test_provider_parse_handles_fences():
    from gameclips.selection.providers import _parse

    assert _parse('```json\n{"stories": []}\n```') == {"stories": []}


def test_provider_selection_and_defaults():
    p = _reset_provider({"CLIPS_LLM_PROVIDER": "gemini", "CLIPS_LLM_MODEL": None, "CLIPS_LLM_BASE_URL": None})
    prov = p.get_provider()
    assert prov.name == "gemini" and prov.model == "gemini-2.5-flash"

    p = _reset_provider({"CLIPS_LLM_PROVIDER": "openai_compatible", "CLIPS_LLM_MODEL": "llama-3.3-70b-versatile", "CLIPS_LLM_BASE_URL": "https://api.groq.com/openai/v1"})
    prov = p.get_provider()
    assert prov.name == "openai" and prov.base_url.endswith("/v1") and prov.model == "llama-3.3-70b-versatile"

    p = _reset_provider({"CLIPS_LLM_PROVIDER": "openai_compatible", "CLIPS_LLM_MODEL": "x", "CLIPS_LLM_BASE_URL": None})
    try:
        p.get_provider()
        raise AssertionError("expected LlmError")
    except p.LlmError:
        pass
    _reset_provider({"CLIPS_LLM_PROVIDER": None, "CLIPS_LLM_MODEL": None, "CLIPS_LLM_BASE_URL": None})
