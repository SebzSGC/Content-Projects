"""OpenAI & OpenAI-compatible (Groq, OpenRouter, Ollama) async HTTP adapter; upgrades retired gpt-4o-mini to gpt-6-luna."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, Optional, Tuple

import httpx

from ..http import FatalApiError, ProviderRateLimiter, classify_http_error, execute_with_retry
from .base import LlmAdapter, RawLlmCallOutput

DEFAULT_OPENAI_MODEL = "gpt-6-luna"

OPENAI_PRICING_PER_1M: Dict[str, Tuple[float, float]] = {
    "gpt-6-luna": (0.25, 2.00),
    "llama-3.3-70b-versatile": (0.59, 0.79),
}


def normalize_openai_model(model: Optional[str]) -> str:
    m = (model or "").strip()
    if not m or m == "gpt-4o-mini":
        # Spec: gpt-4o-mini retires Jan 14, 2027 -> replaced by gpt-6-luna
        return DEFAULT_OPENAI_MODEL
    return m


class OpenAICompatibleAdapter(LlmAdapter):
    provider_name = "openai_compat"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        base_url: str = "https://api.openai.com/v1",
        limiter: Optional[ProviderRateLimiter] = None,
    ) -> None:
        self.api_key = (
            api_key
            or os.environ.get("OPENAI_API_KEY", "").strip()
            or os.environ.get("GROQ_API_KEY", "").strip()
        )
        self.model_name = normalize_openai_model(model)
        self.base_url = base_url.rstrip("/")
        self.limiter = limiter or ProviderRateLimiter(
            max_concurrency=5,
            requests_per_minute=30.0,
            max_units_per_window=800_000.0,
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
        is_local = any(h in self.base_url for h in ("localhost", "127.0.0.1"))
        if not self.api_key and not is_local:
            raise FatalApiError("Falta API key para el proveedor OpenAI/compatible de respaldo.", status_code=401)

        url = f"{self.base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        est_tokens = max(500.0, len(user_text) / 3.8)

        async def _post_with_format(use_strict_schema: bool) -> Tuple[Dict[str, Any], int]:
            sys_content = (
                system_prompt
                if use_strict_schema
                else f"{system_prompt}\n\nResponde SOLO con JSON que cumpla este esquema:\n{json.dumps(json_schema, ensure_ascii=False)}"
            )
            resp_fmt: Dict[str, Any] = (
                {"type": "json_schema", "json_schema": {"name": "curation_result", "schema": json_schema, "strict": True}}
                if use_strict_schema
                else {"type": "json_object"}
            )
            body = {
                "model": self.model_name,
                "messages": [
                    {"role": "system", "content": sys_content},
                    {"role": "user", "content": user_text},
                ],
                "response_format": resp_fmt,
                "max_completion_tokens": max_output_tokens,
                "temperature": 0.25,
            }
            t0 = time.perf_counter()
            resp = await self._client.post(url, headers=headers, json=body, timeout=httpx.Timeout(180.0, connect=15.0))
            lat = int((time.perf_counter() - t0) * 1000)
            if resp.status_code == 400 and use_strict_schema:
                return await _post_with_format(False)
            if resp.status_code >= 400:
                raise classify_http_error("OpenAI-compat", resp)
            return resp.json(), lat

        payload, latency_ms = await execute_with_retry(
            lambda: _post_with_format(True),
            limiter=self.limiter,
            estimated_units=est_tokens,
        )
        choices = payload.get("choices") or []
        raw_text = str(choices[0].get("message", {}).get("content") or "") if choices else ""
        if not raw_text:
            raise FatalApiError("El proveedor compatible con OpenAI devolvió respuesta vacía.")

        usage = payload.get("usage") or {}
        in_tok = int(usage.get("prompt_tokens") or int(est_tokens))
        out_tok = int(usage.get("completion_tokens") or max(1, len(raw_text) // 4))
        in_rate, out_rate = OPENAI_PRICING_PER_1M.get(self.model_name, (0.30, 2.00))
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
