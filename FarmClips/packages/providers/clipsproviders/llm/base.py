"""Common LLM adapter contract, JSON Schema, Pydantic validation with error-feedback retry, and prompt templates."""

from __future__ import annotations

import json
from abc import ABC, abstractmethod
from typing import Any, Callable, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from ..http import ProviderError

CURATION_PROMPT_VERSION = "v2.0"


class LlmEmojiItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    word: str
    emoji: str


class LlmClipProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    start_id: str = Field(description="ID de la frase inicial, p.ej. 'u0012'")
    end_id: str = Field(description="ID de la frase final, p.ej. 'u0028'")
    hook: str = Field(description="Frase inicial o gancho de los primeros 3 segundos")
    overlay_title: str = Field(description="Título quemado en pantalla (3 a 7 palabras, ortografía impecable)")
    post_title: str = Field(description="Título de publicación en MAYÚSCULAS con emoji al final")
    hashtags: List[str] = Field(default_factory=list, description="3 a 5 hashtags en minúsculas sin #")
    emphasis_words: List[str] = Field(default_factory=list, description="Palabras exactas clave para resaltar en verde")
    emojis: List[LlmEmojiItem] = Field(default_factory=list, description="Emojis sugeridos asociados a palabras de énfasis")
    score: int = Field(ge=0, le=100, description="Puntuación de viralidad de 0 a 100")
    reason: str = Field(description="Explicación breve de por qué funciona de forma autónoma")


class CurationEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clips: List[LlmClipProposal] = Field(default_factory=list)


CURATION_JSON_SCHEMA: Dict[str, Any] = {
    "type": "object",
    "properties": {
        "clips": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start_id": {"type": "string"},
                    "end_id": {"type": "string"},
                    "hook": {"type": "string"},
                    "overlay_title": {"type": "string"},
                    "post_title": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "emphasis_words": {"type": "array", "items": {"type": "string"}},
                    "emojis": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "word": {"type": "string"},
                                "emoji": {"type": "string"},
                            },
                            "required": ["word", "emoji"],
                            "additionalProperties": False,
                        },
                    },
                    "score": {"type": "integer"},
                    "reason": {"type": "string"},
                },
                "required": [
                    "start_id",
                    "end_id",
                    "hook",
                    "overlay_title",
                    "post_title",
                    "hashtags",
                    "emphasis_words",
                    "emojis",
                    "score",
                    "reason",
                ],
                "additionalProperties": False,
            },
        }
    },
    "required": ["clips"],
    "additionalProperties": False,
}

CURATION_SYSTEM_PROMPT = """Eres director y editor senior de Shorts verticales de gaming en español (estilo Hormozi Gaming).
Recibes la línea de tiempo compacta del VOD completo con:
- Una línea por frase del streamer: `u0412 [1:02:03] texto`
- Marcas de picos acústicos y de juego: `>>> PICO [1:02:05] (score=... mic=... juego=...)`

REGLAS CRÍTICAS:
1. Devuelve IDs de frase exactos (`start_id` y `end_id`, como `"u0004"` y `"u0015"`), NUNCA inventes tiempos en segundos.
2. Cada clip debe contar una micro-historia autónoma con arco completo: preparación/situación → evento en el juego o giro → reacción/remate del streamer.
3. Duración objetivo entre {min_len:.0f} y {max_len:.0f} segundos (guíate por las marcas `[h:mm:ss]`).
4. Evita charla de relleno, agradecimientos de suscripciones o momentos que no se entienden solos.
5. Para cada clip entrega:
   - `start_id` y `end_id`: IDs de frase inicial y final.
   - `hook`: qué engancha en los primeros 3 segundos.
   - `overlay_title`: 3 a 7 palabras, tildes correctas, para mostrar en la unión cámara/juego (máx 2 líneas).
   - `post_title`: MAYÚSCULAS, primera persona, gancho + 1 emoji al final.
   - `hashtags`: 3 a 5 etiquetas en minúscula sin `#`.
   - `emphasis_words`: 2 a 6 palabras clave exactas dichas por el streamer donde habrá énfasis verde y zoom de impacto.
   - `emojis`: pares `{{"word": "palabra_enfasis", "emoji": "1f631"}}` usando códigos hex Unicode de emoji (ej. `1f631`, `1f480`, `1f525`, `1f602`, `1f92f`) asociados solo a palabras de énfasis.
   - `score`: entero 0 a 100 (solo >60 pasan a render automático).
   - `reason`: 1 frase concisa.

Contexto de la grabación: "{title}". Elige hasta {max_clips} mejores clips."""


class RawLlmCallOutput(BaseModel):
    provider: str
    model: str
    raw_text: str
    raw_payload: Dict[str, Any] = Field(default_factory=dict)
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    latency_ms: int = 0


class LlmCurationResult(BaseModel):
    provider: str
    model: str
    envelope: CurationEnvelope
    calls: List[RawLlmCallOutput] = Field(default_factory=list)

    @property
    def total_cost_usd(self) -> float:
        return round(sum(c.cost_usd for c in self.calls), 6)

    @property
    def total_input_tokens(self) -> int:
        return sum(c.input_tokens for c in self.calls)

    @property
    def total_output_tokens(self) -> int:
        return sum(c.output_tokens for c in self.calls)


def extract_json_dict(raw_text: str) -> Dict[str, Any]:
    cleaned = raw_text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        brace = cleaned.find("{")
        if brace != -1:
            cleaned = cleaned[brace:]
    last_brace = cleaned.rfind("}")
    if last_brace != -1:
        cleaned = cleaned[: last_brace + 1]
    return json.loads(cleaned)


class LlmAdapter(ABC):
    provider_name: str = "base"
    model_name: str = "base"

    @abstractmethod
    async def generate_raw(
        self,
        system_prompt: str,
        user_text: str,
        json_schema: Dict[str, Any],
        max_output_tokens: int = 8192,
    ) -> RawLlmCallOutput:
        """Execute HTTP LLM call returning raw text & usage BEFORE Pydantic validation."""

    async def curate_timeline(
        self,
        timeline_text: str,
        title: str = "Stream de gaming",
        min_len: float = 20.0,
        max_len: float = 60.0,
        max_clips: int = 12,
        on_raw_call: Optional[Callable[[RawLlmCallOutput], None]] = None,
    ) -> LlmCurationResult:
        """Curate timeline with JSON Schema + Pydantic validation; retries once with validation error before failing over."""
        sys_prompt = CURATION_SYSTEM_PROMPT.format(
            min_len=min_len,
            max_len=max_len,
            title=title or "Stream de gaming",
            max_clips=max_clips,
        )
        calls: List[RawLlmCallOutput] = []
        first = await self.generate_raw(sys_prompt, timeline_text, CURATION_JSON_SCHEMA)
        calls.append(first)
        if on_raw_call:
            on_raw_call(first)

        try:
            parsed = CurationEnvelope.model_validate(extract_json_dict(first.raw_text))
            return LlmCurationResult(provider=self.provider_name, model=self.model_name, envelope=parsed, calls=calls)
        except (json.JSONDecodeError, ValidationError) as err1:
            repair_prompt = (
                f"{timeline_text}\n\n"
                f"[CORRECCIÓN DE ESQUEMA REQUERIDA]\n"
                f"Tu respuesta anterior no cumplió el JSON Schema exacto:\n{err1}\n"
                f"Devuelve ÚNICAMENTE el objeto JSON corregido que cumpla estrictamente el esquema."
            )
            second = await self.generate_raw(sys_prompt, repair_prompt, CURATION_JSON_SCHEMA)
            calls.append(second)
            if on_raw_call:
                on_raw_call(second)
            try:
                parsed2 = CurationEnvelope.model_validate(extract_json_dict(second.raw_text))
                return LlmCurationResult(provider=self.provider_name, model=self.model_name, envelope=parsed2, calls=calls)
            except (json.JSONDecodeError, ValidationError) as err2:
                raise ProviderError(
                    f"{self.provider_name}/{self.model_name} devolvió JSON inválido tras reintento de validación: {err2}"
                ) from err2

    async def aclose(self) -> None:
        return None
