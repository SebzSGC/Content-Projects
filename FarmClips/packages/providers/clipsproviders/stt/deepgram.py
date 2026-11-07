"""Deepgram Nova-3 STT adapter: word timestamps, Spanish (`es`/`es-419`), keyterms, direct HTTP without webhooks."""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import httpx
from clipscore.domain import TranscriptWord

from ..http import FatalApiError, ProviderRateLimiter, classify_http_error, execute_with_retry
from .base import SttAdapter, SttResult

DEEPGRAM_NOVA3_USD_PER_MIN = float(os.environ.get("CLIPS_DEEPGRAM_USD_PER_MIN", "0.0043") or 0.0043)
# Keyterm Prompting is billed by Deepgram as a separate add-on on top of the base rate.
DEEPGRAM_KEYTERM_USD_PER_MIN = float(os.environ.get("CLIPS_DEEPGRAM_KEYTERM_USD_PER_MIN", "0.0013") or 0.0013)


def deepgram_usd_per_min(uses_keyterms: bool) -> float:
    return DEEPGRAM_NOVA3_USD_PER_MIN + (DEEPGRAM_KEYTERM_USD_PER_MIN if uses_keyterms else 0.0)


def parse_deepgram_words(payload: Dict[str, Any]) -> List[TranscriptWord]:
    channels = payload.get("results", {}).get("channels", [])
    if not channels:
        return []
    alts = channels[0].get("alternatives", [])
    if not alts:
        return []
    raw_words = alts[0].get("words", [])
    words: List[TranscriptWord] = []
    for rw in raw_words:
        txt = str(rw.get("punctuated_word") or rw.get("word") or "").strip()
        if not txt:
            continue
        s = float(rw.get("start", 0.0))
        e = float(rw.get("end", s + 0.05))
        prob = float(rw.get("confidence", 1.0))
        words.append(TranscriptWord(text=txt, start=round(s, 3), end=round(max(s + 0.03, e), 3), prob=round(prob, 4)))
    return words


class DeepgramNova3Adapter(SttAdapter):
    provider_name = "deepgram"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = "nova-3",
        limiter: Optional[ProviderRateLimiter] = None,
        base_url: str = "https://api.deepgram.com/v1/listen",
    ) -> None:
        self.api_key = api_key or os.environ.get("DEEPGRAM_API_KEY", "").strip()
        self.model_name = model or "nova-3"
        self.base_url = base_url
        self.limiter = limiter or ProviderRateLimiter(
            max_concurrency=8,
            requests_per_minute=100.0,
            max_units_per_window=72_000.0,
            unit_window_sec=3600.0,
        )
        self._client = httpx.AsyncClient(http2=False)

    async def transcribe_chunk(
        self,
        audio_path: Path,
        duration_sec: float,
        language: str = "es",
        keyterms: Sequence[str] = (),
    ) -> SttResult:
        if not self.api_key:
            raise FatalApiError("Falta DEEPGRAM_API_KEY para usar Deepgram Nova-3.", status_code=401)

        audio_bytes = audio_path.read_bytes()
        content_type = "audio/ogg" if audio_path.suffix.lower() in {".opus", ".ogg"} else "audio/wav"

        params: List[Tuple[str, str]] = [
            ("model", self.model_name),
            ("language", language or "es"),
            ("smart_format", "true"),
            ("punctuate", "true"),
        ]
        # Nova-3 exclusive keyterm boosting for game names & streamer slang
        if "nova-3" in self.model_name:
            for term in keyterms[:50]:
                clean = term.strip()
                if clean:
                    params.append(("keyterm", clean))

        req_timeout = max(45.0, duration_sec * 0.40)

        async def _do_post() -> Tuple[Dict[str, Any], int]:
            t0 = time.perf_counter()
            resp = await self._client.post(
                self.base_url,
                params=params,
                headers={
                    "Authorization": f"Token {self.api_key}",
                    "Content-Type": content_type,
                },
                content=audio_bytes,
                timeout=httpx.Timeout(req_timeout, connect=15.0),
            )
            lat = int((time.perf_counter() - t0) * 1000)
            if resp.status_code >= 400:
                raise classify_http_error("Deepgram", resp)
            return resp.json(), lat

        raw, latency_ms = await execute_with_retry(
            _do_post,
            limiter=self.limiter,
            estimated_units=max(1.0, duration_sec),
        )
        billed_sec = float(raw.get("metadata", {}).get("duration") or duration_sec)
        uses_keyterms = any(k == "keyterm" for k, _ in params)
        cost = round((billed_sec / 60.0) * deepgram_usd_per_min(uses_keyterms), 6)
        return SttResult(
            provider=self.provider_name,
            model=self.model_name,
            words=parse_deepgram_words(raw),
            raw_response=raw,
            units_billed_sec=round(billed_sec, 3),
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
