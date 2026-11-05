"""Interchangeable LLM providers for the two AI passes (story selection and
clip verification). Pick one with ``CLIPS_LLM_PROVIDER``:

* ``anthropic``         — Claude (Anthropic SDK)
* ``openai``            — OpenAI (OpenAI SDK)
* ``openai_compatible`` — any OpenAI-compatible endpoint via ``CLIPS_LLM_BASE_URL``
                          (Groq, OpenRouter, DeepSeek, Ollama, LM Studio, vLLM…)
* ``gemini``            — Google Gemini (google-genai SDK)

Every provider implements ``generate_json``: system prompt + user text +
optional JPEG images → dict validated against a JSON schema. SDKs are imported
lazily, so only the one in use has to be installed. Keys stay on the server.
"""

from __future__ import annotations

import base64
import json
import os
from functools import lru_cache
from typing import Any, Dict, List, Optional

from ..config import get_settings


class LlmError(RuntimeError):
    pass


def _parse(text: Optional[str]) -> Dict[str, Any]:
    if not text:
        raise LlmError("El modelo no devolvió texto.")
    cleaned = text.strip()
    if cleaned.startswith("```"):  # some compatible servers wrap JSON in fences
        cleaned = cleaned.strip("`")
        cleaned = cleaned[cleaned.find("{") :]
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LlmError("El modelo devolvió JSON inválido.") from exc


def _schema_hint(schema: Dict[str, Any]) -> str:
    return "\n\nResponde SOLO con un objeto JSON que cumpla este JSON Schema:\n" + json.dumps(schema, ensure_ascii=False)


class Provider:
    name = "base"

    def __init__(self, model: str, api_key: Optional[str], base_url: Optional[str]):
        self.model, self.api_key, self.base_url = model, api_key, base_url

    def generate_json(
        self, system: str, text: str, images_b64: List[str], schema: Dict[str, Any], effort: str, max_tokens: int
    ) -> Dict[str, Any]:
        raise NotImplementedError


class AnthropicProvider(Provider):
    name = "anthropic"
    # Models that accept the server-side refusal fallback (``fallbacks: "default"``).
    FALLBACK_MODELS = {"claude-opus-5-5", "claude-opus-5", "claude-fable-5-1", "claude-sonnet-5-5"}
    FALLBACK_BETA = "server-side-fallback-2026-07-01"

    @lru_cache(maxsize=1)
    def _client(self):
        import anthropic

        kwargs: Dict[str, Any] = {"max_retries": 4}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return anthropic.Anthropic(**kwargs)

    def generate_json(self, system, text, images_b64, schema, effort, max_tokens):
        import anthropic

        content: List[Dict[str, Any]] = [
            {"type": "image", "source": {"type": "base64", "media_type": "image/jpeg", "data": img}} for img in images_b64
        ]
        content.append({"type": "text", "text": text})
        params: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens,
            "system": system,
            "messages": [{"role": "user", "content": content}],
            "output_config": {"effort": effort, "format": {"type": "json_schema", "schema": schema}},
        }
        try:
            if self.model in self.FALLBACK_MODELS:
                with self._client().beta.messages.stream(**params, betas=[self.FALLBACK_BETA], fallbacks="default") as stream:
                    message = stream.get_final_message()
            else:
                with self._client().messages.stream(**params) as stream:
                    message = stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            raise LlmError("Credenciales de Anthropic inválidas o ausentes.") from exc
        except anthropic.RateLimitError as exc:
            raise LlmError("Límite de uso de la API de Claude alcanzado; reintenta en unos minutos.") from exc
        except anthropic.APIStatusError as exc:
            raise LlmError(f"Error de la API de Claude ({exc.status_code}): {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LlmError("No se pudo conectar con la API de Claude.") from exc

        if message.stop_reason == "refusal":
            category = getattr(message.stop_details, "category", None) if message.stop_details else None
            raise LlmError(f"Claude rechazó la solicitud (categoría: {category}).")
        if message.stop_reason == "max_tokens":
            raise LlmError("La respuesta se cortó por max_tokens.")
        return _parse(next((b.text for b in message.content if b.type == "text"), None))


class OpenAIProvider(Provider):
    """OpenAI and every OpenAI-compatible server (Chat Completions API)."""

    name = "openai"

    @lru_cache(maxsize=1)
    def _client(self):
        from openai import OpenAI

        kwargs: Dict[str, Any] = {"max_retries": 4}
        if self.api_key:
            kwargs["api_key"] = self.api_key
        elif self.base_url:
            kwargs["api_key"] = "not-needed"  # local servers (Ollama, LM Studio) ignore it
        if self.base_url:
            kwargs["base_url"] = self.base_url
        return OpenAI(**kwargs)

    def _create(self, messages, response_format, max_tokens):
        return self._client().chat.completions.create(
            model=self.model, messages=messages, response_format=response_format, max_completion_tokens=max_tokens
        )

    def generate_json(self, system, text, images_b64, schema, effort, max_tokens):
        import openai

        user: List[Dict[str, Any]] = [
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{img}"}} for img in images_b64
        ]
        user.append({"type": "text", "text": text})
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        strict = {"type": "json_schema", "json_schema": {"name": "result", "schema": schema, "strict": True}}
        try:
            try:
                res = self._create(messages, strict, max_tokens)
            except openai.BadRequestError:
                # Servers without json_schema support: plain JSON mode + schema in the prompt.
                messages[0] = {"role": "system", "content": system + _schema_hint(schema)}
                res = self._create(messages, {"type": "json_object"}, max_tokens)
        except openai.AuthenticationError as exc:
            raise LlmError("API key inválida o ausente para el proveedor OpenAI/compatible.") from exc
        except openai.RateLimitError as exc:
            raise LlmError("Límite de uso del proveedor alcanzado; reintenta en unos minutos.") from exc
        except openai.APIStatusError as exc:
            raise LlmError(f"Error del proveedor ({exc.status_code}): {exc.message}") from exc
        except openai.APIConnectionError as exc:
            raise LlmError("No se pudo conectar con el proveedor de IA.") from exc

        choice = res.choices[0]
        if choice.finish_reason == "length":
            raise LlmError("La respuesta se cortó por longitud.")
        if getattr(choice.message, "refusal", None):
            raise LlmError(f"El modelo rechazó la solicitud: {choice.message.refusal}")
        return _parse(choice.message.content)


class GeminiProvider(Provider):
    name = "gemini"

    @lru_cache(maxsize=1)
    def _client(self):
        from google import genai

        return genai.Client(api_key=self.api_key) if self.api_key else genai.Client()

    def generate_json(self, system, text, images_b64, schema, effort, max_tokens):
        from google.genai import errors, types

        parts: List[Any] = [types.Part.from_bytes(data=base64.b64decode(img), mime_type="image/jpeg") for img in images_b64]
        parts.append(text)
        try:
            try:
                config = types.GenerateContentConfig(
                    system_instruction=system,
                    response_mime_type="application/json",
                    response_json_schema=schema,
                    max_output_tokens=max_tokens,
                )
            except (TypeError, ValueError):  # older google-genai without response_json_schema
                config = types.GenerateContentConfig(
                    system_instruction=system + _schema_hint(schema),
                    response_mime_type="application/json",
                    max_output_tokens=max_tokens,
                )
            res = self._client().models.generate_content(model=self.model, contents=parts, config=config)
        except errors.APIError as exc:
            raise LlmError(f"Error de la API de Gemini ({exc.code}): {exc.message}") from exc
        return _parse(res.text)


PROVIDERS = {
    "anthropic": AnthropicProvider,
    "claude": AnthropicProvider,
    "openai": OpenAIProvider,
    "openai_compatible": OpenAIProvider,
    "gemini": GeminiProvider,
}

# Used only when CLIPS_LLM_MODEL is empty; change them freely.
DEFAULT_MODELS = {
    "anthropic": "claude-opus-5-5",
    "claude": "claude-opus-5-5",
    "openai": "gpt-4.1",
    "gemini": "gemini-2.5-flash",
}

KEY_ENV = {
    "anthropic": "ANTHROPIC_API_KEY",
    "claude": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


@lru_cache(maxsize=1)
def get_provider() -> Provider:
    s = get_settings()
    name = s.llm_provider
    if name not in PROVIDERS:
        raise LlmError(f"Proveedor de IA desconocido: {name}. Opciones: {', '.join(sorted(PROVIDERS))}")
    model = s.llm_model or DEFAULT_MODELS.get(name)
    if not model:
        raise LlmError("Define CLIPS_LLM_MODEL con el modelo a usar en tu servidor compatible.")
    if name == "openai_compatible" and not s.llm_base_url:
        raise LlmError("Define CLIPS_LLM_BASE_URL para usar un proveedor compatible con OpenAI.")
    api_key = s.llm_api_key or os.environ.get(KEY_ENV.get(name, ""), "") or None
    return PROVIDERS[name](model=model, api_key=api_key, base_url=s.llm_base_url)
