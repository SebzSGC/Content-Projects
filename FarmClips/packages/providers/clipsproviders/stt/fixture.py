"""Recorded API fixture adapter for offline testing without spending API credits."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Sequence

from .base import SttAdapter, SttResult
from .deepgram import parse_deepgram_words
from .groq import parse_groq_words


class RecordedSttFixtureAdapter(SttAdapter):
    provider_name = "fixture_stt"
    model_name = "recorded-nova-3"
    accepts_speech_only_audio = False

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    async def transcribe_chunk(
        self,
        audio_path: Path,
        duration_sec: float,
        language: str = "es",
        keyterms: Sequence[str] = (),
    ) -> SttResult:
        raw = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        words = parse_deepgram_words(raw) or parse_groq_words(raw)
        # Filter words to chunk duration if chunk is shorter than fixture
        clipped = [w for w in words if w.start < duration_sec + 0.5]
        return SttResult(
            provider=self.provider_name,
            model=self.model_name,
            words=clipped,
            raw_response=raw,
            units_billed_sec=round(duration_sec, 3),
            cost_usd=0.0,
            latency_ms=5,
        )
