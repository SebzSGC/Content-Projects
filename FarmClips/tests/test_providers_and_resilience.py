"""Tests for STT & LLM adapters, rate limiter, Retry-After 429, 413 audio resplitting, Pydantic repair retry, circuit breaker failover, and USD budget cap."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

import httpx
import pytest
from clipscore.domain import AudioChunk, SyncResult
from clipsmedia.ffmpeg import extract_opus_mono
from clipsproviders.http import (
    FailoverRouter,
    FatalApiError,
    PayloadTooLargeError,
    ProviderRateLimiter,
    TransientApiError,
    execute_with_retry,
)
from clipsproviders.llm import (
    GeminiAdapter,
    LlmAdapter,
    OpenAICompatibleAdapter,
    RawLlmCallOutput,
    normalize_gemini_model,
    normalize_openai_model,
)
from clipsproviders.stt import (
    DeepgramNova3Adapter,
    GroqWhisperAdapter,
    SttAdapter,
    SttResult,
    parse_deepgram_words,
    parse_groq_words,
)
from clipsserver.config import ServerSettings
from clipsserver.orchestrator.db import BudgetExceededError, OrchestratorDB
from clipsserver.pools.api_pool import ApiPool

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures" / "api"
GOLDEN_CAM = Path(__file__).resolve().parent / "golden" / "camara.mp4"


def test_model_retirement_normalizers_and_fixture_parsers() -> None:
    assert normalize_gemini_model(None) == "gemini-3.5-flash-lite"
    assert normalize_gemini_model("gemini-1.5-flash") == "gemini-3.5-flash-lite"
    assert normalize_gemini_model("gemini-2.5-flash") == "gemini-3.5-flash-lite"
    assert normalize_gemini_model("gemini-3.8-flash") == "gemini-3.8-flash"

    assert normalize_openai_model(None) == "gpt-6-luna"
    assert normalize_openai_model("gpt-4o-mini") == "gpt-6-luna"

    dg_raw = json.loads((FIXTURES_DIR / "deepgram_nova3.json").read_text(encoding="utf-8"))
    dg_words = parse_deepgram_words(dg_raw)
    assert len(dg_words) > 40
    assert dg_words[0].text == "Bueno"

    gq_raw = json.loads((FIXTURES_DIR / "groq_whisper.json").read_text(encoding="utf-8"))
    gq_words = parse_groq_words(gq_raw)
    assert len(gq_words) == len(dg_words)


async def test_deepgram_and_groq_mock_http_adapters(tmp_path: Path) -> None:
    audio_file = tmp_path / "sample.opus"
    audio_file.write_bytes(b"OggS-fake-opus-bytes" * 40)

    dg_fixture = json.loads((FIXTURES_DIR / "deepgram_nova3.json").read_text(encoding="utf-8"))
    captured_dg_urls: List[str] = []

    def dg_handler(request: httpx.Request) -> httpx.Response:
        captured_dg_urls.append(str(request.url))
        assert request.headers["Authorization"] == "Token dg_test_key"
        assert request.headers["Content-Type"] == "audio/ogg"
        return httpx.Response(200, json=dg_fixture)

    dg = DeepgramNova3Adapter(api_key="dg_test_key", model="nova-3")
    await dg._client.aclose()
    dg._client = httpx.AsyncClient(transport=httpx.MockTransport(dg_handler))
    res_dg = await dg.transcribe_chunk(audio_file, duration_sec=30.0, language="es", keyterms=["Valorant", "clutch"])
    await dg.aclose()

    assert "keyterm=Valorant" in captured_dg_urls[0]
    assert "keyterm=clutch" in captured_dg_urls[0]
    assert res_dg.provider == "deepgram"
    assert res_dg.cost_usd > 0
    assert len(res_dg.words) > 40

    # Groq 10s minimum billing + 25 MB pre-flight PayloadTooLargeError guard
    gq_fixture = json.loads((FIXTURES_DIR / "groq_whisper.json").read_text(encoding="utf-8"))
    gq_fixture["duration"] = 4.0  # Shorter than 10s -> must still bill 10.0s!

    gq = GroqWhisperAdapter(api_key="gq_test_key", max_upload_mb=0.0001)
    with pytest.raises(PayloadTooLargeError):
        await gq.transcribe_chunk(audio_file, duration_sec=4.0)
    await gq.aclose()

    gq2 = GroqWhisperAdapter(api_key="gq_test_key", max_upload_mb=24.5)
    await gq2._client.aclose()
    gq2._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=gq_fixture)))
    res_gq = await gq2.transcribe_chunk(audio_file, duration_sec=4.0, language="es-419", keyterms=["Jett"])
    await gq2.aclose()
    assert res_gq.units_billed_sec == 10.0


async def test_retry_after_429_and_fail_fast_401() -> None:
    limiter = ProviderRateLimiter(max_concurrency=2, requests_per_minute=60.0)
    attempts = 0

    async def flaky_op() -> str:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise TransientApiError("Rate limit", status_code=429, retry_after=0.05)
        return "ok"

    out = await execute_with_retry(flaky_op, limiter=limiter, base_delay_sec=0.02)
    assert out == "ok"
    assert attempts == 2
    assert limiter.rate_multiplier < 1.0  # Reduced rate after 429, then nudged up on success

    fatal_calls = 0

    async def auth_fail() -> str:
        nonlocal fatal_calls
        fatal_calls += 1
        raise FatalApiError("Invalid API key", status_code=401)

    with pytest.raises(FatalApiError):
        await execute_with_retry(auth_fail, limiter=limiter, base_delay_sec=0.01)
    assert fatal_calls == 1  # Never retry 401!


async def test_llm_pydantic_repair_retry_and_openai_fallback_format() -> None:
    # 1. Test Pydantic validation failure -> automatic second call with error feedback
    class ScriptedLlm(LlmAdapter):
        provider_name = "scripted"
        model_name = "test-llm"

        def __init__(self) -> None:
            self.prompts_seen: List[str] = []

        async def generate_raw(
            self,
            system_prompt: str,
            user_text: str,
            json_schema: Dict[str, Any],
            max_output_tokens: int = 8192,
        ) -> RawLlmCallOutput:
            self.prompts_seen.append(user_text)
            if len(self.prompts_seen) == 1:
                # Invalid JSON schema (missing required fields & wrong type)
                bad = '{"clips": [{"start_id": "u0001"}]}'
                return RawLlmCallOutput(provider="scripted", model="test", raw_text=bad, input_tokens=100, output_tokens=20)
            valid = json.dumps(
                {
                    "clips": [
                        {
                            "start_id": "u0002",
                            "end_id": "u0006",
                            "hook": "Gancho",
                            "overlay_title": "Jugada maestra final",
                            "post_title": "GANAMOS LA PARTIDA 🔥",
                            "hashtags": ["gaming"],
                            "emphasis_words": ["maestra"],
                            "emojis": [{"word": "maestra", "emoji": "1f525"}],
                            "score": 82,
                            "reason": "Arco completo.",
                        }
                    ]
                }
            )
            return RawLlmCallOutput(provider="scripted", model="test", raw_text=valid, input_tokens=150, output_tokens=80)

    raw_archived: List[RawLlmCallOutput] = []
    llm = ScriptedLlm()
    curated = await llm.curate_timeline("u0001 [0:02] hola", on_raw_call=raw_archived.append)
    assert len(llm.prompts_seen) == 2
    assert "CORRECCIÓN DE ESQUEMA REQUERIDA" in llm.prompts_seen[1]
    assert len(raw_archived) == 2  # Both raw responses archived!
    assert curated.envelope.clips[0].score == 82

    # 2. Test OpenAI-compatible 400 on strict json_schema falling back to json_object + Gemini adapter
    oa_reqs: List[Dict[str, Any]] = []

    def oa_handler(req: httpx.Request) -> httpx.Response:
        body = json.loads(req.content.decode("utf-8"))
        oa_reqs.append(body)
        if body["response_format"]["type"] == "json_schema":
            return httpx.Response(400, json={"error": "json_schema unsupported on this endpoint"})
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"clips": []}'}}],
                "usage": {"prompt_tokens": 200, "completion_tokens": 10},
            },
        )

    oa = OpenAICompatibleAdapter(api_key="oa_key", model="gpt-4o-mini")
    assert oa.model_name == "gpt-6-luna"
    await oa._client.aclose()
    oa._client = httpx.AsyncClient(transport=httpx.MockTransport(oa_handler))
    res_oa = await oa.curate_timeline("u0001 [0:02] prueba")
    await oa.aclose()
    assert len(oa_reqs) == 2
    assert oa_reqs[1]["response_format"]["type"] == "json_object"
    assert res_oa.envelope.clips == []

    gem_fixture = json.loads((FIXTURES_DIR / "gemini_curate.json").read_text(encoding="utf-8"))
    gem = GeminiAdapter(api_key="gem_key", model="gemini-1.5-flash")
    assert gem.model_name == "gemini-3.5-flash-lite"
    await gem._client.aclose()
    gem._client = httpx.AsyncClient(transport=httpx.MockTransport(lambda req: httpx.Response(200, json=gem_fixture)))
    res_gem = await gem.curate_timeline("u0001 [0:02] prueba")
    await gem.aclose()
    assert len(res_gem.envelope.clips) == 1


async def test_circuit_breaker_failover_413_resplit_and_budget_cap(tmp_path: Path) -> None:
    # 1. Circuit breaker opens after 3 failures and routes straight to backup without touching primary
    primary_hits = 0
    backup_hits = 0

    class BrokenStt(SttAdapter):
        provider_name = "broken"
        model_name = "broken"

        async def transcribe_chunk(self, audio_path: Path, duration_sec: float, language: str = "es", keyterms=()):
            nonlocal primary_hits
            primary_hits += 1
            raise TransientApiError("503 Service Unavailable", status_code=503)

    class HealthyBackupStt(SttAdapter):
        provider_name = "groq"
        model_name = "whisper-large-v3-turbo"

        async def transcribe_chunk(self, audio_path: Path, duration_sec: float, language: str = "es", keyterms=()):
            nonlocal backup_hits
            backup_hits += 1
            return SttResult(provider="groq", model="whisper-large-v3-turbo", words=[], raw_response={"ok": True}, units_billed_sec=duration_sec, cost_usd=0.001)

    router = FailoverRouter(primary=BrokenStt(), backup=HealthyBackupStt(), failure_threshold=2, open_seconds=120.0)
    f = tmp_path / "dummy.opus"
    f.write_bytes(b"123")
    await router.call(lambda a: a.transcribe_chunk(f, 10.0))
    await router.call(lambda a: a.transcribe_chunk(f, 10.0))
    assert router.primary_breaker.is_open is True
    # 3rd call skips open primary completely!
    await router.call(lambda a: a.transcribe_chunk(f, 10.0))
    assert primary_hits == 2
    assert backup_hits == 3

    # 2. HTTP 413 PayloadTooLargeError triggers automatic finer Opus splitting in ApiPool
    opus_full = tmp_path / "cam36s.opus"
    extract_opus_mono(GOLDEN_CAM, opus_full, start_sec=0.0, duration_sec=36.0)

    settings = ServerSettings(
        data_dir=tmp_path / "data",
        drive_mode="disabled",
        max_budget_usd=0.05,
    )
    db = OrchestratorDB(settings.data_dir / "test.db")
    ses = db.create_session(title="Resplit Test")
    pool = ApiPool(settings, db)

    class RejectOver22sStt(SttAdapter):
        provider_name = "groq"
        model_name = "whisper-large-v3-turbo"

        async def transcribe_chunk(self, audio_path: Path, duration_sec: float, language: str = "es", keyterms=()):
            if duration_sec > 22.0:
                raise PayloadTooLargeError("Chunk > 22s simulated 413", status_code=413)
            from clipscore.domain import TranscriptWord

            return SttResult(
                provider="groq",
                model="whisper-large-v3-turbo",
                words=[TranscriptWord(text="hola", start=1.0, end=1.5, prob=0.99)],
                raw_response={"duration": duration_sec},
                units_billed_sec=duration_sec,
                cost_usd=0.02,
            )

    pool.stt_router = FailoverRouter(primary=RejectOver22sStt(), backup=None)
    big_chunk = AudioChunk(index=0, start_cam_sec=0.0, end_cam_sec=36.0, path=str(opus_full), size_bytes=opus_full.stat().st_size)
    words = await pool.transcribe_chunk_cached(
        session_id=ses["id"],
        chunk=big_chunk,
        sync=SyncResult(shift_sec=0.0, scale=1.0),
        language="es",
        keyterms=[],
        silences=[],
        chunks_work_dir=tmp_path / "subchunks",
    )
    assert len(words) == 2  # Two finer sub-chunks transcribed & merged!
    assert db.total_spend_usd() == pytest.approx(0.04)

    # 3. Budget cap ($0.05) blocks further uncached calls when exceeded
    db.record_api_call(
        session_id=ses["id"],
        task_hash="extra_spend",
        provider="gemini",
        model="gemini-3.5-flash-lite",
        kind="llm",
        raw_response_path=tmp_path / "raw.json",
        units_billed=1000,
        cost_usd=0.02,
    )
    with pytest.raises(BudgetExceededError):
        db.assert_within_budget(settings.max_budget_usd)

    await pool.aclose()
    db.close()
