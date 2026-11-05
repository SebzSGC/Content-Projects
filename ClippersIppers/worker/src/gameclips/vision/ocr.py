"""Read the game's own on-screen dialogue (PaddleOCR).

Many games print what their characters say (the reference Short shows
"¡Dile que se abroche el cinturón!"). Those lines are GAME speech without
relying on audio, which lets ``speakers.py`` label overlapping voices.
Only runs when the session defines ``game_subtitles_region``.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any, Callable, List, Optional

import numpy as np

from ..domain import OcrLine, Rect


def _ocr_engine(lang: str):
    from paddleocr import PaddleOCR

    try:  # PaddleOCR 3.x
        return PaddleOCR(lang=lang, use_doc_orientation_classify=False, use_doc_unwarping=False, use_textline_orientation=False)
    except TypeError:  # PaddleOCR 2.x
        return PaddleOCR(lang=lang, use_angle_cls=False, show_log=False)


def _read_text(engine: Any, image: np.ndarray) -> str:
    if hasattr(engine, "predict"):
        texts: List[str] = []
        for res in engine.predict(image):
            data = res.json.get("res", res.json) if hasattr(res, "json") else res
            texts += [t for t, sc in zip(data.get("rec_texts", []), data.get("rec_scores", [])) if sc >= 0.6]
        return " ".join(texts).strip()
    result = engine.ocr(image, cls=False) or []
    lines = result[0] if result and isinstance(result[0], list) else result
    return " ".join(item[1][0] for item in (lines or []) if item and item[1][1] >= 0.6).strip()


def similar(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def read_game_dialogue(
    gameplay_proxy: str,
    region: Rect,
    language: Optional[str],
    progress: Callable[[float, str], None],
    sample_hz: float = 2.0,
) -> List[OcrLine]:
    import cv2

    engine = _ocr_engine("es" if (language or "es").startswith("es") else "en")
    cap = cv2.VideoCapture(gameplay_proxy)
    fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    step = max(1, int(round(fps / sample_hz)))
    lines: List[OcrLine] = []
    prev_crop: Optional[np.ndarray] = None
    prev_text = ""
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        if i % step == 0:
            t = i / fps
            h, w = frame.shape[:2]
            px = region.to_pixels(w, h)
            crop = frame[px.y : px.y + px.h, px.x : px.x + px.w]
            changed = prev_crop is None or float(np.mean(cv2.absdiff(crop, prev_crop))) > 4.0
            text = _read_text(engine, crop) if changed else prev_text
            prev_crop = crop
            if text and lines and similar(lines[-1].text, text) > 0.85 and t - lines[-1].end <= 1.5:
                lines[-1].end = t + 1.0 / sample_hz
            elif text:
                lines.append(OcrLine(start=t, end=t + 1.0 / sample_hz, text=text))
            prev_text = text
        i += 1
        if i % 1000 == 0:
            progress(min(1.0, i / total), "Leyendo diálogos del juego")
    cap.release()
    return [l for l in lines if len(l.text) >= 3]
