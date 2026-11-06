"""Groq whisper-large-v3-turbo STT adapter: verbose_json word timestamps, 25MB/100MB guard, 10s minimum billing."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
from clipscore.domain import TranscriptWord

from ..http import (
    FatalApiError,
    PayloadTooLargeError,
    ProviderRateLimiter,
    classify_http_error,
    execute_with_retry,
)
from .base import SttAdapter, SttResult

GROQ_WHISPER_TURBO_USD_PER_HOUR = 0.04


def parse_groq_words(payload: Dict[str, Any]) -> List[TranscriptWord]:
    raw_words = payload.get("words") or []
    words: List[TranscriptWord] = []
    for rw in raw_words:
        txt = str(rw.get("word") or "").strip()
        if not txt:
            continue
        s = float(rw.get("start", 0.0))
        e = float(rw.get("end", s + 0.05))
        words.append(TranscriptWord(text=txt, start=round(s, 3), end=round(max(s + 0.03, e), 3), prob=1.0))

    if not words and payload.get("segments"):
        # Fallback if endpoint returned segment-level tokens
        for seg in payload["segments"]:
            seg_text = str(seg.get("text") or "").strip()
            if not seg_text:
                continue
            toks = seg_text.split()
            s0 = float(seg.get("start", 0.0))
            s1 = float(seg.get("end", s0 + 0.5))
            step = max(0.05, (s1 - s0) / max(1, len(toks)))
            for i, tok in enumerate(toks):
                words.append(
                    TranscriptWord(
                        text=tok,
                        start=round(s0 + i * step, 3),
                        end=round(s0 + (i + 1) * step, 3),
                        prob=1.0,
                    )
                )
    return words


class GroqWhisperAdapter(SttAdapter):
    provider_name = "groq"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "whisper-large-v3-turbo",
        max_upload_mb: float = 24.5,
        limiter: Optional[ProviderRateLimiter] = None,
        base_url: str = "https://api.groq.com/openai/v1/audio/transcriptions",
    ) -> None:
        self.api_key = api_key or os.environ.get("GROQ_API_KEY", "").strip()
        self.model_name = model or "whisper-large-v3-turbo"
        self.max_upload_bytes = int(max_upload_mb * 1024 * 1024)
        self.base_url = base_url
        # Groq free tier: 20 RPM, 7,200 audio seconds per hour
        self.limiter = limiter or ProviderRateLimiter(
            max_concurrency=5,
            requests_per_minute=20.0,
            max_units_per_window=7200.0,
            unit_window_sec=3600.0,
        )
        self._client = httpx.AsyncClient()

    async def transcribe_chunk(
        self,
        audio_path: Path,
        duration_sec: float,
        language: str = "es",
        keyterms: Sequence[str] = (),
    ) -> SttResult:
        if not self.api_key:
            raise FatalApiError("Falta GROQ_API_KEY para usar Groq Whisper.", status_code=401)

        size = audio_path.stat().st_size
        if size > self.max_upload_bytes:
            raise PayloadTooLargeError(
                f"El tramo de audio ({size / (1024 * 1024):.1f} MB) supera el límite de Groq ({self.max_upload_bytes / (1024 * 1024):.1f} MB).",
                status_code=413,
            )

        audio_bytes = audio_path.read_bytes()
        mime = "audio/ogg" if audio_path.suffix.lower() in {".opus", ".ogg"} else "audio/wav"
        prompt_hint = ", ".join(keyterms[:25]) if keyterms else ""
        req_timeout = max(45.0, duration_sec * 0.45)

        async def _do_post() -> Tuple[Dict[str, Any], int]:
            t0 = time.perf_counter()
            data_fields: Dict[str, str] = {
                "model": self.model_name,
                "response_format": "verbose_json",
                "timestamp_granularities[]": "word",
                "language": (language or "es").split("-")[0],
            }
            if prompt_hint:
                data_fields["prompt"] = prompt_hint

            resp = await self._client.post(
                self.base_url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                data=data_fields,
                files={"file": (audio_path.name, audio_bytes, mime)},
                timeout=httpx.Timeout(req_timeout, connect=15.0),
            )
            lat = int((time.perf_counter() - t0) * 1000)
            if resp.status_code >= 400:
                raise classify_http_error("Groq", resp)
            return resp.json(), lat

        billed_est = max(10.0, duration_sec)  # Groq bills minimum 10s per request
        raw, latency_ms = await execute_with_retry(
            _do_post,
            limiter=self.limiter,
            estimated_units=billed_est,
        )
        actual_dur = float(raw.get("duration") or duration_sec)
        billed_sec = max(10.0, actual_dur)
        cost = round((billed_sec / 3600.0) * GROQ_WHISPER_TURBO_USD_PER_HOUR, 6)
        return SttResult(
            provider=self.provider_name,
            model=self.model_name,
            words=parse_groq_words(raw),
            raw_response=raw,
            units_billed_sec=round(billed_sec, 3),
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
