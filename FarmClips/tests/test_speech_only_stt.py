"""Tests for speech-only STT packing (long silences cut before upload, timestamps mapped back) and Gemini thinking-token accounting."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import List

import httpx
import pytest
from clipscore.domain import AudioChunk, SilenceSpan, SyncResult, TranscriptWord
from clipsmedia.ffmpeg import resolve_binary, run_ffmpeg
from clipsmedia.silence import (
    build_packed_segments,
    detect_silences,
    map_packed_time,
    plan_speech_only_spans,
    remap_packed_words,
    write_speech_only_opus,
)
from clipsproviders.http import FailoverRouter
from clipsproviders.llm import GeminiAdapter
from clipsproviders.stt import SttAdapter, SttResult
from clipsserver.config import ServerSettings
from clipsserver.orchestrator.db import OrchestratorDB
from clipsserver.pools.api_pool import ApiPool

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "api"


def _talk_silence_talk(dst: Path) -> Path:
    """4 s tone ("speech") + 8 s silence + 4 s tone + 1 s silence + 3 s tone = 20 s, encoded like a real chunk."""
    parts = [("sine=f=440", 4.0), ("anullsrc=r=16000:cl=mono", 8.0), ("sine=f=660", 4.0), ("anullsrc=r=16000:cl=mono", 1.0), ("sine=f=550", 3.0)]
    args: List[str] = ["-loglevel", "error"]
    for src, dur in parts:
        args += ["-f", "lavfi", "-t", f"{dur}", "-i", f"{src}:sample_rate=16000" if src.startswith("sine") else src]
    joined = "".join(f"[{i}:a]" for i in range(len(parts)))
    args += ["-filter_complex", f"{joined}concat=n={len(parts)}:v=0:a=1[out]", "-map", "[out]", "-ac", "1", "-ar", "16000", "-c:a", "libopus", "-b:a", "32k", str(dst)]
    run_ffmpeg(args)
    return dst


def test_plan_keeps_natural_pauses_and_cuts_long_silences() -> None:
    silences = [
        SilenceSpan(start=4.0, end=12.0),   # long: cut, keeping 0.35 s of padding on each side
        SilenceSpan(start=16.0, end=17.0),  # natural pause (< 2 s): kept
    ]
    spans = plan_speech_only_spans(20.0, silences)
    assert spans == [(0.0, 4.35), (11.65, 20.0)]
    assert plan_speech_only_spans(20.0, []) == [(0.0, 20.0)]
    # A silence touching the chunk edge is trimmed without creating empty spans
    assert plan_speech_only_spans(10.0, [SilenceSpan(start=0.0, end=5.0)]) == [(4.65, 10.0)]
    assert plan_speech_only_spans(10.0, [SilenceSpan(start=6.0, end=10.0)]) == [(0.0, 6.35)]


def test_remap_returns_original_timeline_and_never_spans_a_cut() -> None:
    segments = build_packed_segments([(0.0, 4.35), (11.65, 20.0)])
    assert map_packed_time(1.0, segments) == pytest.approx(1.0)
    assert map_packed_time(5.0, segments) == pytest.approx(12.3)  # 0.65 s into the second span
    words = [
        TranscriptWord(text="hola", start=0.5, end=0.9, prob=0.9),
        TranscriptWord(text="justo", start=4.2, end=4.6, prob=0.9),  # crosses the junction in packed time
        TranscriptWord(text="otra", start=5.0, end=5.4, prob=0.9),
    ]
    out = remap_packed_words(words, segments)
    assert [(w.start, w.end) for w in out] == [(0.5, 0.9), (4.2, 4.35), (12.3, 12.7)]


def test_speech_only_opus_matches_the_segment_map(tmp_path: Path) -> None:
    src = _talk_silence_talk(tmp_path / "chunk.opus")
    silences = detect_silences(src)
    chunk = AudioChunk(index=0, start_cam_sec=0.0, end_cam_sec=20.0, path=str(src), sha256="abc")
    packed = write_speech_only_opus(chunk, silences, tmp_path / "speech", )
    # Saves < 20 s: the default thresholds keep the original chunk
    assert packed is None

    from clipsmedia import silence as silence_mod

    old = silence_mod.SPEECH_ONLY_MIN_SAVED_SEC
    silence_mod.SPEECH_ONLY_MIN_SAVED_SEC = 2.0
    try:
        packed = write_speech_only_opus(chunk, silences, tmp_path / "speech")
    finally:
        silence_mod.SPEECH_ONLY_MIN_SAVED_SEC = old
    assert packed is not None
    assert len(packed.segments) == 2  # only the 8 s gap is cut; the 1 s pause stays
    assert packed.duration == pytest.approx(20.0 - 8.0 + 2 * 0.35, abs=0.15)
    real = subprocess.run(
        [resolve_binary("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(packed.path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    assert float(real) == pytest.approx(packed.duration, abs=0.08)


async def test_api_pool_sends_speech_only_and_maps_words_back(tmp_path: Path) -> None:
    from clipsmedia import silence as silence_mod

    src = _talk_silence_talk(tmp_path / "chunk.opus")
    silences = detect_silences(src)
    settings = ServerSettings(data_dir=tmp_path / "data", drive_mode="disabled")
    db = OrchestratorDB(settings.data_dir / "test.db")
    ses = db.create_session(title="Speech only")
    pool = ApiPool(settings, db)
    received: List[float] = []

    class EchoStt(SttAdapter):
        provider_name = "deepgram"
        model_name = "nova-3"

        async def transcribe_chunk(self, audio_path: Path, duration_sec: float, language: str = "es", keyterms=()):
            received.append(duration_sec)
            # One word right after the cut, in packed time (second span starts at 4.35 s packed)
            return SttResult(
                provider="deepgram",
                model="nova-3",
                words=[TranscriptWord(text="vamos", start=4.6, end=5.0, prob=0.99)],
                raw_response={},
                units_billed_sec=duration_sec,
            )

    class FixtureLikeStt(EchoStt):
        provider_name = "fixture_stt"
        accepts_speech_only_audio = False

    old = silence_mod.SPEECH_ONLY_MIN_SAVED_SEC
    silence_mod.SPEECH_ONLY_MIN_SAVED_SEC = 2.0
    try:
        chunk = AudioChunk(index=0, start_cam_sec=0.0, end_cam_sec=20.0, path=str(src), sha256="sp1")
        pool.stt_router = FailoverRouter(primary=EchoStt(), backup=None)
        words = await pool.transcribe_chunk_cached(ses["id"], chunk, SyncResult(shift_sec=0.0, scale=1.0), "es", [], silences, tmp_path / "work")
        assert received[-1] < 15.0  # the long silence was not uploaded
        gap = next(s for s in silences if s.duration >= 2.0)
        assert words[0].start == pytest.approx(gap.end - 0.35 + 0.25, abs=0.05)  # mapped back after the silence

        chunk2 = AudioChunk(index=1, start_cam_sec=0.0, end_cam_sec=20.0, path=str(src), sha256="sp2")
        pool.stt_router = FailoverRouter(primary=FixtureLikeStt(), backup=None)
        words2 = await pool.transcribe_chunk_cached(ses["id"], chunk2, SyncResult(shift_sec=0.0, scale=1.0), "es", [], silences, tmp_path / "work")
        assert received[-1] == pytest.approx(20.0)  # fixtures keep the original chunk
        assert words2[0].start == pytest.approx(4.6)
    finally:
        silence_mod.SPEECH_ONLY_MIN_SAVED_SEC = old
        await pool.aclose()
        db.close()


async def test_gemini_cost_includes_thinking_tokens() -> None:
    payload = json.loads((FIXTURES_DIR / "gemini_curate.json").read_text(encoding="utf-8"))
    payload["usageMetadata"] = {"promptTokenCount": 10_000, "candidatesTokenCount": 1_000, "thoughtsTokenCount": 3_000}
    gem = GeminiAdapter(api_key="gem_key")
    await gem._client.aclose()
    gem._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=payload)))
    out = await gem.generate_raw("sys", "u0001 [0:02] hola", {"type": "object"})
    await gem.aclose()
    assert out.output_tokens == 4_000
    assert out.cost_usd == pytest.approx(10_000 / 1e6 * 0.30 + 4_000 / 1e6 * 2.50)
