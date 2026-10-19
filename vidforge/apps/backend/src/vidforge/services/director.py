"""Director Studio service: script beat segmentation, @tag extraction, and visual prompt generation."""

from __future__ import annotations

import re
import uuid
from typing import Any

import httpx

from vidforge.domain.models import BeatModel, CharacterModel, ScriptModel
from vidforge.infra.db import db
from vidforge.infra.secrets import secret_store

TAG_REGEX = re.compile(r"@[A-Za-z0-9_\u00C0-\u017F]{1,40}")


def extract_character_tags(text: str) -> list[str]:
    seen: list[str] = []
    for m in TAG_REGEX.finditer(text):
        tag = m.group(0)
        if tag not in seen:
            seen.append(tag)
    return seen


def segment_script_into_beats(
    script_text: str,
    style_guide: str = "Cinematográfico, iluminación dramática, 4k",
    existing_characters: list[CharacterModel] | None = None,
) -> ScriptModel:
    text = script_text.strip()
    tags_found = extract_character_tags(text)
    char_map: dict[str, CharacterModel] = {c.tag: c for c in (existing_characters or [])}
    for t in tags_found:
        if t not in char_map:
            clean_name = t.lstrip("@").replace("_", " ").title()
            char_map[t] = CharacterModel(
                tag=t,
                name=clean_name,
                description=f"Personaje {clean_name}, apariencia consistente en todas las tomas",
            )

    # Split into sentences/clauses while tracking character ranges
    sentence_pattern = re.compile(r"[^.!?\n]+[.!?]*", re.MULTILINE)
    beats: list[BeatModel] = []
    idx = 0
    for match in sentence_pattern.finditer(text):
        raw_seg = match.group(0).strip()
        if not raw_seg:
            continue
        start_c, end_c = match.span()
        beat_tags = extract_character_tags(raw_seg)
        char_desc = "; ".join(
            f"{char_map[t].name}: {char_map[t].description}" for t in beat_tags if t in char_map
        )
        has_numbers = bool(re.search(r"\b\d+(?:[.,]\d+)?%?\b", raw_seg))
        has_vs = bool(re.search(r"\b(vs\.?|versus|contra|comparado)\b", raw_seg, re.IGNORECASE))
        media_kind = "motion" if (has_numbers or has_vs) else "image"

        clean_visual = TAG_REGEX.sub(lambda m: m.group(0).lstrip("@"), raw_seg)
        prompt_parts = [f"Escena visual para: '{clean_visual}'"]
        if char_desc:
            prompt_parts.append(f"Personajes en escena ({char_desc})")
        if style_guide:
            prompt_parts.append(f"Estilo visual: {style_guide}")

        beats.append(
            BeatModel(
                id=f"beat_{idx + 1:03d}_{uuid.uuid4().hex[:6]}",
                index=idx,
                text=raw_seg,
                char_range=[start_c, end_c],
                tags=beat_tags,
                visual_prompt=". ".join(prompt_parts),
                media_kind=media_kind,  # type: ignore[arg-type]
                time_range_us=None,
            )
        )
        idx += 1

    return ScriptModel(
        text=text,
        characters=list(char_map.values()),
        beats=beats,
    )


async def enrich_prompts_with_llm(script: ScriptModel, style_guide: str) -> ScriptModel:
    """Optionally enriches visual prompts via local Ollama or OpenAI-compatible API; falls back gracefully."""
    settings = db.get_settings()
    ollama_url = settings.get("ollama_url", "http://127.0.0.1:11434")
    openai_key = secret_store.get_secret("openai")

    async with httpx.AsyncClient(timeout=6.0) as client:
        for beat in script.beats:
            if openai_key:
                try:
                    r = await client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {openai_key}"},
                        json={
                            "model": "gpt-4o-mini",
                            "messages": [
                                {"role": "system", "content": "Genera un prompt visual cinematográfico breve en español."},
                                {"role": "user", "content": f"Frase: {beat.text}\nEstilo: {style_guide}"},
                            ],
                        },
                    )
                    if r.status_code == 200:
                        beat.visual_prompt = r.json()["choices"][0]["message"]["content"].strip()
                        continue
                except Exception:
                    pass
            try:
                r = await client.post(
                    f"{ollama_url.rstrip('/')}/api/generate",
                    json={
                        "model": settings.get("ollama_model", "qwen2.5:3b"),
                        "prompt": f"Describe una toma visual cinematográfica para: {beat.text}. Estilo: {style_guide}",
                        "stream": False,
                    },
                )
                if r.status_code == 200 and r.json().get("response"):
                    beat.visual_prompt = r.json()["response"].strip()
            except Exception:
                pass
    return script
