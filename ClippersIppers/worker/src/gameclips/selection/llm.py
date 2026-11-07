"""The two AI passes, independent of the provider configured in providers.py:
story selection over transcript windows and verification of the best clips
(keyframes + transcript when the model accepts images)."""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from ..config import get_settings
from .prompts import SELECT_SCHEMA, SELECT_SYSTEM, VERIFY_SCHEMA, VERIFY_SYSTEM
from .providers import LlmError, get_provider

__all__ = ["LlmError", "select_stories", "verify_candidate"]


def select_stories(window_text: str, title: str, max_stories: int = 6) -> List[Dict[str, Any]]:
    s = get_settings()
    system = SELECT_SYSTEM.format(min_len=s.min_clip_sec, max_len=s.max_clip_sec, max_stories=max_stories, title=title or "stream")
    data = get_provider().generate_json(system, window_text, [], SELECT_SCHEMA, effort=s.llm_effort, max_tokens=32000)
    return list(data.get("stories", []))


def verify_candidate(images_jpeg_b64: List[str], transcript: str, proposal: Dict[str, Any], effort: Optional[str] = None) -> Dict[str, Any]:
    s = get_settings()
    images = images_jpeg_b64 if s.llm_vision else []
    system = VERIFY_SYSTEM if images else VERIFY_SYSTEM + "\n\n(No hay fotogramas disponibles: evalúa solo con la transcripción.)"
    text = f"Transcripción del tramo:\n{transcript}\n\nPropuesta:\n{json.dumps(proposal, ensure_ascii=False, indent=1)}"
    return get_provider().generate_json(system, text, images, VERIFY_SCHEMA, effort=effort or "medium", max_tokens=16000)
