"""Recorded LLM fixture adapter for offline golden pipeline testing."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict

from .base import LlmAdapter, RawLlmCallOutput


class RecordedLlmFixtureAdapter(LlmAdapter):
    provider_name = "fixture_llm"
    model_name = "recorded-gemini-3.5-flash-lite"

    def __init__(self, fixture_path: Path) -> None:
        self.fixture_path = fixture_path

    async def generate_raw(
        self,
        system_prompt: str,
        user_text: str,
        json_schema: Dict[str, Any],
        max_output_tokens: int = 8192,
    ) -> RawLlmCallOutput:
        raw_payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        if "candidates" in raw_payload:
            text = raw_payload["candidates"][0]["content"]["parts"][0]["text"]
        elif "clips" in raw_payload:
            text = json.dumps(raw_payload, ensure_ascii=False)
        else:
            text = json.dumps({"clips": []})
        return RawLlmCallOutput(
            provider=self.provider_name,
            model=self.model_name,
            raw_text=text,
            raw_payload=raw_payload,
            input_tokens=len(user_text) // 4,
            output_tokens=len(text) // 4,
            cost_usd=0.0,
            latency_ms=8,
        )
