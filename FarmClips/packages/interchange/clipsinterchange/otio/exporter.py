"""Exportador universal OpenTimelineIO (.otio) como fallback para DaVinci / Premiere."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List

from clipseditplan import EditPlan

from ..base import ExportContext, ExportResult, FidelityWarning

EXPORTER_VERSION = "0.1.0"


class OtioExporter:
    """Exporta el EditPlan v2 a formato estándar OpenTimelineIO (.otio)."""

    name: str = "otio"
    version: str = EXPORTER_VERSION

    def export(self, plan: EditPlan, ctx: ExportContext, out_dir: Path) -> ExportResult:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        warnings: List[FidelityWarning] = []

        fps = float(ctx.source_fps or 60.0)
        if callable(getattr(plan, "plan_hash", None)):
            plan_hash = plan.plan_hash()
        else:
            plan_hash = str(getattr(plan, "plan_hash", "") or "default_hash")
        clip_name = getattr(plan, "clip_id", None) or ctx.clip_id or "Clip"

        warnings.append(
            FidelityWarning(
                field="effects",
                message="OTIO almacena pistas y cortes; los keyframes de encuadre deben aplicarse en el NLE receptor",
                severity="info",
            )
        )

        v1_children: List[Dict[str, Any]] = []
        v2_children: List[Dict[str, Any]] = []
        a1_children: List[Dict[str, Any]] = []
        a2_children: List[Dict[str, Any]] = []

        ranges = plan.source.ranges if plan.source and plan.source.ranges else [(0.0, 10.0)]
        timeline_acc_s = 0.0

        for idx, (r_start, r_end) in enumerate(ranges):
            dur_s = max(0.01, r_end - r_start)
            dur_frames = round(dur_s * fps)
            in_frames_game = round(r_start * fps)
            in_frames_cam = round(max(0.0, r_start + ctx.camera_offset_s) * fps)

            # Clip Gameplay
            v1_children.append({
                "OTIO_SCHEMA": "Clip.2",
                "name": f"Gameplay_{idx + 1}",
                "source_range": {
                    "OTIO_SCHEMA": "TimeRange.1",
                    "start_time": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": in_frames_game},
                    "duration": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": dur_frames},
                },
                "media_reference": {
                    "OTIO_SCHEMA": "ExternalReference.1",
                    "target_url": ctx.gameplay_path.as_uri(),
                },
            })

            # Clip Cámara
            v2_children.append({
                "OTIO_SCHEMA": "Clip.2",
                "name": f"Camara_{idx + 1}",
                "source_range": {
                    "OTIO_SCHEMA": "TimeRange.1",
                    "start_time": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": in_frames_cam},
                    "duration": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": dur_frames},
                },
                "media_reference": {
                    "OTIO_SCHEMA": "ExternalReference.1",
                    "target_url": ctx.camera_path.as_uri(),
                },
            })

            # Audio Mic
            a1_children.append({
                "OTIO_SCHEMA": "Clip.2",
                "name": f"Mic_{idx + 1}",
                "source_range": {
                    "OTIO_SCHEMA": "TimeRange.1",
                    "start_time": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": in_frames_cam},
                    "duration": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": dur_frames},
                },
                "media_reference": {
                    "OTIO_SCHEMA": "ExternalReference.1",
                    "target_url": ctx.camera_path.as_uri(),
                },
            })

            # Audio Juego
            a2_children.append({
                "OTIO_SCHEMA": "Clip.2",
                "name": f"Juego_{idx + 1}",
                "source_range": {
                    "OTIO_SCHEMA": "TimeRange.1",
                    "start_time": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": in_frames_game},
                    "duration": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": dur_frames},
                },
                "media_reference": {
                    "OTIO_SCHEMA": "ExternalReference.1",
                    "target_url": ctx.gameplay_path.as_uri(),
                },
            })

            timeline_acc_s += dur_s

        markers: List[Dict[str, Any]] = []
        if plan.captions and plan.captions.groups:
            for g_idx, group in enumerate(plan.captions.groups):
                words = getattr(group, "words", [])
                text = " ".join(getattr(w, "w", getattr(w, "text", "")) for w in words)
                if not text:
                    text = f"Caption {g_idx + 1}"
                g_start = float(words[0].s) if words else float(getattr(group, "start", 0.0))
                g_end = float(words[-1].e) if words else float(getattr(group, "end", g_start + 1.0))
                markers.append({
                    "OTIO_SCHEMA": "Marker.2",
                    "name": text[:30],
                    "marked_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "start_time": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": round(g_start * fps)},
                        "duration": {"OTIO_SCHEMA": "RationalTime.1", "rate": fps, "value": round(max(0.05, g_end - g_start) * fps)},
                    },
                    "color": "GREEN",
                    "comment": text,
                })

        otio_doc: Dict[str, Any] = {
            "OTIO_SCHEMA": "Timeline.1",
            "name": clip_name,
            "metadata": {
                "farmclips": {
                    "clip_id": ctx.clip_id,
                    "session_id": ctx.session_id,
                    "plan_hash": plan_hash,
                }
            },
            "tracks": {
                "OTIO_SCHEMA": "Stack.1",
                "children": [
                    {"OTIO_SCHEMA": "Track.1", "name": "V1 Gameplay", "kind": "Video", "children": v1_children},
                    {"OTIO_SCHEMA": "Track.1", "name": "V2 Camara", "kind": "Video", "children": v2_children},
                    {"OTIO_SCHEMA": "Track.1", "name": "A1 Mic", "kind": "Audio", "children": a1_children},
                    {"OTIO_SCHEMA": "Track.1", "name": "A2 Juego", "kind": "Audio", "children": a2_children},
                ],
            },
            "markers": markers,
        }

        project_file = out_dir / "clip.otio"
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(otio_doc, f, indent=2, ensure_ascii=False)

        return ExportResult(
            project_path=project_file,
            exporter=self.name,
            exporter_version=self.version,
            plan_hash=plan_hash,
            duration_s=round(timeline_acc_s, 3),
            warnings=warnings,
        )
