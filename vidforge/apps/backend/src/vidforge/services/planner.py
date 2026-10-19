"""Timeline Auto-Planner, motion-graphics template catalog, and semantic rule validator."""

from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any

from rapidfuzz import fuzz

from vidforge.domain.models import (
    ClipModel,
    KenBurnsEffect,
    MotionSpec,
    ScriptModel,
    SubtitleClipSpec,
    TimelineModel,
    TrackModel,
    TranscriptModel,
    TransitionSpec,
)
from vidforge.infra.paths import TEMPLATES_DIR


def list_templates() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if not TEMPLATES_DIR.exists():
        return out
    for mf in sorted(TEMPLATES_DIR.glob("*/manifest.json")):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
            data["template_dir"] = str(mf.parent)
            out.append(data)
        except Exception:
            pass
    return out


def validate_motion_semantics(template_manifest: dict[str, Any], props: dict[str, Any], spoken_text: str) -> list[str]:
    """Fail-closed semantic validation ensuring motion graphics props respect the spoken script."""
    errors: list[str] = []
    spoken_lower = spoken_text.lower()
    for rule_obj in template_manifest.get("semantic_rules", []):
        rule = rule_obj.get("rule")
        field = rule_obj.get("field", "")
        val = str(props.get(field, "")).strip()
        if rule == "numbers_must_appear_in_speech":
            nums_in_prop = re.findall(r"\d+(?:[.,]\d+)?", val)
            nums_in_speech = re.findall(r"\d+(?:[.,]\d+)?", spoken_lower)
            if nums_in_prop and not any(n in nums_in_speech for n in nums_in_prop):
                errors.append(
                    f"La cifra '{val}' en '{field}' no aparece en el texto hablado ('{spoken_text}')."
                )
        elif rule == "text_must_be_substring_fuzzy":
            threshold = float(rule_obj.get("threshold", 0.5)) * 100.0
            ratio = fuzz.partial_ratio(val.lower(), spoken_lower)
            if ratio < threshold:
                errors.append(
                    f"El texto '{val}' no guarda suficiente similitud ({ratio:.0f}% < {threshold:.0f}%) con el guion."
                )
        elif rule == "requires_two_entities":
            if not props.get("left_title") or not props.get("right_title"):
                errors.append("La comparativa requiere dos entidades definidas (left_title y right_title).")
    return errors


def build_auto_timeline(
    transcript: TranscriptModel,
    visual_assets: list[dict[str, Any]],
    script: ScriptModel | None = None,
    width: int = 1920,
    height: int = 1080,
    fps: int = 60,
    default_transition: str = "fade",
    transition_duration_us: int = 400_000,
    include_motion_scenes: bool = True,
) -> TimelineModel:
    """Builds a gapless multi-track timeline aligned to word/segment timestamps."""
    total_dur_us = max(1_000_000, transcript.duration_us)
    segments = transcript.segments

    video_clips: list[ClipModel] = []
    motion_clips: list[ClipModel] = []
    subtitle_clips: list[ClipModel] = []

    pan_Cycle = ["none", "left_right", "right_left", "top_bottom", "bottom_top"]
    xfade_cycle = [default_transition, "wipeleft", "smoothleft", "fadeblack"]

    n_segs = len(segments)
    for idx, seg in enumerate(segments):
        # Compute gapless slot bounds [slot_start, slot_end]
        slot_start = 0 if idx == 0 else segments[idx - 1].end_us
        slot_end = total_dur_us if idx == n_segs - 1 else seg.end_us
        if slot_end <= slot_start:
            slot_end = slot_start + 500_000
        slot_dur = slot_end - slot_start

        asset = visual_assets[idx % len(visual_assets)] if visual_assets else None
        trans = (
            TransitionSpec(kind="cut", name="cut", duration_us=0)
            if idx == 0
            else TransitionSpec(
                kind="xfade",
                name=xfade_cycle[idx % len(xfade_cycle)],
                duration_us=min(transition_duration_us, slot_dur // 3),
            )
        )

        video_clips.append(
            ClipModel(
                id=f"vclip_{idx + 1:03d}",
                asset_id=asset["id"] if asset else None,
                start_us=slot_start,
                duration_us=slot_dur,
                effects=[
                    KenBurnsEffect(
                        zoom_from=1.03,
                        zoom_to=1.10,
                        pan=pan_Cycle[idx % len(pan_Cycle)],  # type: ignore[arg-type]
                    )
                ],
                transition_in=trans,
            )
        )

        # Subtitle clip per segment
        subtitle_clips.append(
            ClipModel(
                id=f"sclip_{idx + 1:03d}",
                start_us=seg.start_us,
                duration_us=max(200_000, seg.end_us - seg.start_us),
                subtitle=SubtitleClipSpec(
                    text=seg.text,
                    style_id="default",
                    word_range=seg.word_range,
                    mode="karaoke",
                ),
            )
        )

        # Auto-plan motion graphics overlay if segment contains numbers or comparisons
        if include_motion_scenes and slot_dur >= 1_500_000:
            num_match = re.search(r"\b(\d+(?:[.,]\d+)?%?)\b", seg.text)
            if num_match:
                num_str = num_match.group(1)
                motion_clips.append(
                    ClipModel(
                        id=f"mclip_{idx + 1:03d}",
                        start_us=slot_start + 100_000,
                        duration_us=min(4_000_000, slot_dur - 150_000),
                        motion=MotionSpec(
                            template_id="stat-highlight",
                            props={
                                "value": num_str,
                                "label": seg.text[:42],
                                "sublabel": "Dato clave del segmento",
                            },
                            fullscreen=False,
                        ),
                    )
                )
            elif idx == 0 and slot_dur >= 1_800_000:
                motion_clips.append(
                    ClipModel(
                        id=f"mclip_{idx + 1:03d}",
                        start_us=slot_start + 100_000,
                        duration_us=min(3_500_000, slot_dur - 150_000),
                        motion=MotionSpec(
                            template_id="lower-third",
                            props={
                                "heading": seg.text[:36],
                                "subheading": "Introducción",
                            },
                            fullscreen=False,
                        ),
                    )
                )

    audio_clips = [
        ClipModel(
            id="aclip_narration",
            asset_id=transcript.audio_asset_id,
            start_us=0,
            duration_us=total_dur_us,
            volume_db=0.0,
        )
    ]

    tracks = [
        TrackModel(id="track_video", kind="video", name="Pista Visual Principal", clips=video_clips),
        TrackModel(id="track_motion", kind="motion", name="Escenas Animadas (HTML/SVG)", clips=motion_clips),
        TrackModel(id="track_subs", kind="subtitle", name="Subtítulos ASS Dinámicos", clips=subtitle_clips),
        TrackModel(id="track_audio", kind="audio", name="Locución Maestro", clips=audio_clips),
    ]

    from vidforge.domain.models import CanvasConfig, Rational

    return TimelineModel(
        revision=1,
        canvas=CanvasConfig(width=width, height=height, fps=Rational(num=fps, den=1)),
        duration_us=total_dur_us,
        tracks=tracks,
    )


def validate_timeline_invariants(timeline: TimelineModel) -> list[str]:
    """Validates structural invariants of a timeline."""
    issues: list[str] = []
    if timeline.duration_us <= 0:
        issues.append("La duración del timeline debe ser mayor a 0 us.")
    for tr in timeline.tracks:
        last_end = 0
        for idx, c in enumerate(tr.clips):
            if c.duration_us <= 0:
                issues.append(f"Clip {c.id} en pista {tr.id} tiene duración inválida ({c.duration_us}).")
            if tr.kind == "video" and c.start_us < last_end:
                issues.append(f"Solape no permitido en pista de vídeo principal: clip {c.id}.")
            if c.start_us + c.duration_us > timeline.duration_us + 50_000:
                issues.append(f"Clip {c.id} excede la duración total del timeline.")
            last_end = c.start_us + c.duration_us
    return issues
