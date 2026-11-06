"""Google Gemini REST adapter over async httpx (defaults to gemini-3.5-flash-lite; also supports gemini-3.8-flash)."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, Optional, Tuple

import httpx

from ..http import FatalApiError, ProviderRateLimiter, classify_http_error, execute_with_retry
from .base import LlmAdapter, RawLlmCallOutput

# Pricing per 1M tokens (USD) — verified table in architecture spec
GEMINI_PRICING_PER_1M: Dict[str, Tuple[float, float]] = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.50, 3.00),
}
DEFAULT_GEMINI_MODEL = "gemini-3.5-flash-lite"


def normalize_gemini_model(model: Optional[str]) -> str:
    m = (model or "").strip()
    if not m or m.startswith("gemini-1.5") or m.startswith("gemini-2."):
        # Spec: 1.5 Flash retired; 2.5 legacy; default to 3.5-flash-lite
        return DEFAULT_GEMINI_MODEL
    return m


class GeminiAdapter(LlmAdapter):
    provider_name = "gemini"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        limiter: Optional[ProviderRateLimiter] = None,
        api_base: str = "https://generativelanguage.googleapis.com/v1beta",
    ) -> None:
        self.api_key = api_key or os.environ.get("GEMINI_API_KEY", "").strip()
        self.model_name = normalize_gemini_model(model)
        self.api_base = api_base.rstrip("/")
        self.limiter = limiter or ProviderRateLimiter(
            max_concurrency=6,
            requests_per_minute=30.0,
            max_units_per_window=1_000_000.0,
            unit_window_sec=60.0,
        )
        self._client = httpx.AsyncClient()

    async def generate_raw(
        self,
        system_prompt: str,
        user_text: str,
        json_schema: Dict[str, Any],
        max_output_tokens: int = 8192,
    ) -> RawLlmCallOutput:
        if not self.api_key:
            raise FatalApiError("Falta GEMINI_API_KEY para usar Gemini.", status_code=401)

        url = f"{self.api_base}/models/{self.model_name}:generateContent"
        # Clean out additionalProperties if strict OpenAPI subset is required by endpoint, while keeping properties/required
        body = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_text}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseJsonSchema": json_schema,
                "maxOutputTokens": max_output_tokens,
                "temperature": 0.25,
            },
        }
        est_tokens = max(500.0, len(user_text) / 3.8)

        async def _do_post() -> Tuple[Dict[str, Any], int]:
            t0 = time.perf_counter()
            resp = await self._client.post(
                url,
                params={"key": self.api_key},
                json=body,
                timeout=httpx.Timeout(180.0, connect=15.0),
            )
            lat = int((time.perf_counter() - t0) * 1000)
            if resp.status_code >= 400:
                raise classify_http_error("Gemini", resp)
            return resp.json(), lat

        payload, latency_ms = await execute_with_retry(
            _do_post,
            limiter=self.limiter,
            estimated_units=est_tokens,
        )
        candidates = payload.get("candidates") or []
        raw_text = ""
        if candidates:
            parts = candidates[0].get("content", {}).get("parts") or []
            raw_text = "".join(str(p.get("text", "")) for p in parts)
        if not raw_text:
            raise FatalApiError(f"Gemini no devolvió contenido en candidates: {str(payload)[:300]}")

        usage = payload.get("usageMetadata") or {}
        in_tok = int(usage.get("promptTokenCount") or int(est_tokens))
        out_tok = int(usage.get("candidatesTokenCount") or max(1, len(raw_text) // 4))
        in_rate, out_rate = GEMINI_PRICING_PER_1M.get(self.model_name, (0.30, 2.50))
        cost = round((in_tok / 1_000_000.0) * in_rate + (out_tok / 1_000_000.0) * out_rate, 6)

        return RawLlmCallOutput(
            provider=self.provider_name,
            model=self.model_name,
            raw_text=raw_text,
            raw_payload=payload,
            input_tokens=in_tok,
            output_tokens=out_tok,
            cost_usd=cost,
            latency_ms=latency_ms,
        )

    async def aclose(self) -> None:
        await self._client.aclose()
