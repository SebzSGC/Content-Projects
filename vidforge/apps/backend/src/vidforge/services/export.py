"""Exporters for CapCut Desktop (draft_content.json + draft_meta_info.json), OpenTimelineIO (.otio) and FCPXML."""

from __future__ import annotations

import json
import os
import shutil
import time
import uuid
from pathlib import Path
from typing import Any

import jsonschema
import psutil

from vidforge.domain.models import TimelineModel, TranscriptModel
from vidforge.infra.db import db
from vidforge.infra.paths import CONTRACTS_DIR


def is_capcut_running() -> bool:
    for p in psutil.process_iter(["name"]):
        try:
            name = (p.info.get("name") or "").lower()
            if name in ("capcut.exe", "vegas.exe"):
                return True
        except Exception:
            continue
    return False


def get_capcut_subset_schema() -> dict[str, Any]:
    schema_path = CONTRACTS_DIR / "capcut-draft-subset.v1.json"
    return json.loads(schema_path.read_text(encoding="utf-8"))


def validate_capcut_draft(draft: dict[str, Any]) -> list[str]:
    """Validates draft_content.json against JSON Schema and structural invariants."""
    errors: list[str] = []
    schema = get_capcut_subset_schema()
    try:
        jsonschema.validate(instance=draft, schema=schema)
    except jsonschema.ValidationError as exc:
        errors.append(f"Schema error: {exc.message}")
        return errors

    # Check referential integrity & non-overlapping target_timeranges
    mat = draft["materials"]
    known_ids: set[str] = set()
    for group in ("videos", "audios", "texts", "transitions", "animations"):
        for item in mat.get(group, []):
            if "id" in item:
                known_ids.add(item["id"])

    total_dur = int(draft["duration"])
    for tr in draft["tracks"]:
        last_end = 0
        for seg in tr["segments"]:
            mid = seg["material_id"]
            if mid not in known_ids:
                errors.append(f"Segment {seg['id']} references unknown material_id {mid}")
            trange = seg["target_timerange"]
            s_us = int(trange["start"])
            d_us = int(trange["duration"])
            if s_us < last_end:
                errors.append(f"Overlap in CapCut track {tr['id']} at segment {seg['id']}")
            if s_us + d_us > total_dur:
                errors.append(f"Segment {seg['id']} exceeds draft duration ({s_us + d_us} > {total_dur})")
            for ref_id in seg.get("extra_material_refs", []):
                if ref_id not in known_ids:
                    errors.append(f"Segment {seg['id']} references unknown extra_material_ref {ref_id}")
            last_end = s_us + d_us

    return errors


def export_capcut_draft(
    timeline: TimelineModel,
    draft_root: Path,
    draft_name: str,
    copy_media: bool = True,
    check_process_lock: bool = True,
) -> dict[str, Any]:
    """Generates a complete, schema-validated CapCut Desktop project folder."""
    if check_process_lock and is_capcut_running():
        raise RuntimeError("CapCut está abierto. Ciérralo antes de exportar para evitar corrupción del borrador.")

    safe_name = "".join(c for c in draft_name if c not in '<>:"/\\|?*').strip() or "VidForge_Draft"
    draft_dir = draft_root / safe_name
    media_dir = draft_dir / "Resources"
    media_dir.mkdir(parents=True, exist_ok=True)

    width = timeline.canvas.width
    height = timeline.canvas.height
    fps = round(timeline.canvas.fps.float_val, 2)
    ratio = "16:9" if width >= height else "9:16"

    videos_mat: list[dict[str, Any]] = []
    audios_mat: list[dict[str, Any]] = []
    texts_mat: list[dict[str, Any]] = []
    transitions_mat: list[dict[str, Any]] = []
    tracks_out: list[dict[str, Any]] = []

    max_end_us = max(1_000_000, int(timeline.duration_us))

    for tr in timeline.tracks:
        if tr.muted or not tr.clips:
            continue

        if tr.kind in ("video", "motion", "overlay"):
            segs: list[dict[str, Any]] = []
            for clip in tr.clips:
                asset = db.get_asset(clip.asset_id) if clip.asset_id else None
                src_path = Path(asset["file_path"]) if (asset and Path(asset["file_path"]).exists()) else None
                if src_path and copy_media:
                    dst = media_dir / f"{clip.id}_{src_path.name}"
                    if not dst.exists():
                        shutil.copy2(src_path, dst)
                    final_path = str(dst.resolve())
                elif src_path:
                    final_path = str(src_path.resolve())
                else:
                    final_path = str((media_dir / f"{clip.id}.png").resolve())

                is_photo = final_path.lower().endswith((".png", ".jpg", ".jpeg", ".webp"))
                mat_id = f"mat_v_{uuid.uuid4().hex[:10]}"
                videos_mat.append(
                    {
                        "id": mat_id,
                        "path": final_path,
                        "type": "photo" if is_photo else "video",
                        "duration": int(clip.duration_us),
                        "width": width,
                        "height": height,
                    }
                )

                extra_refs: list[str] = []
                if clip.transition_in and clip.transition_in.kind != "cut" and clip.transition_in.duration_us > 0:
                    tid = f"mat_tr_{uuid.uuid4().hex[:10]}"
                    transitions_mat.append(
                        {
                            "id": tid,
                            "name": clip.transition_in.name,
                            "duration": int(clip.transition_in.duration_us),
                            "type": "transition",
                        }
                    )
                    extra_refs.append(tid)

                end_us = clip.start_us + clip.duration_us
                max_end_us = max(max_end_us, end_us)
                segs.append(
                    {
                        "id": f"seg_{uuid.uuid4().hex[:10]}",
                        "material_id": mat_id,
                        "target_timerange": {
                            "start": int(clip.start_us),
                            "duration": int(clip.duration_us),
                        },
                        "source_timerange": {
                            "start": int(clip.source_in_us),
                            "duration": int(clip.duration_us),
                        },
                        "volume": 1.0,
                        "extra_material_refs": extra_refs,
                    }
                )
            tracks_out.append({"id": f"trk_{tr.id}", "type": "video", "segments": segs})

        elif tr.kind == "audio":
            segs = []
            for clip in tr.clips:
                asset = db.get_asset(clip.asset_id) if clip.asset_id else None
                src_path = Path(asset["file_path"]) if (asset and Path(asset["file_path"]).exists()) else None
                if src_path and copy_media:
                    dst = media_dir / f"{clip.id}_{src_path.name}"
                    if not dst.exists():
                        shutil.copy2(src_path, dst)
                    final_path = str(dst.resolve())
                else:
                    final_path = str(src_path.resolve()) if src_path else ""

                mat_id = f"mat_a_{uuid.uuid4().hex[:10]}"
                audios_mat.append(
                    {
                        "id": mat_id,
                        "path": final_path,
                        "duration": int(clip.duration_us),
                        "type": "extract_music",
                        "name": asset["name"] if asset else "Narration",
                    }
                )
                end_us = clip.start_us + clip.duration_us
                max_end_us = max(max_end_us, end_us)
                segs.append(
                    {
                        "id": f"seg_{uuid.uuid4().hex[:10]}",
                        "material_id": mat_id,
                        "target_timerange": {
                            "start": int(clip.start_us),
                            "duration": int(clip.duration_us),
                        },
                        "source_timerange": {
                            "start": 0,
                            "duration": int(clip.duration_us),
                        },
                        "volume": 1.0,
                        "extra_material_refs": [],
                    }
                )
            tracks_out.append({"id": f"trk_{tr.id}", "type": "audio", "segments": segs})

        elif tr.kind == "subtitle":
            segs = []
            for clip in tr.clips:
                txt_val = clip.subtitle.text if clip.subtitle else ""
                mat_id = f"mat_t_{uuid.uuid4().hex[:10]}"
                texts_mat.append(
                    {
                        "id": mat_id,
                        "content": txt_val,
                        "type": "subtitle",
                        "font_size": 15.0,
                        "text_color": "#FFFFFF",
                    }
                )
                end_us = clip.start_us + clip.duration_us
                max_end_us = max(max_end_us, end_us)
                segs.append(
                    {
                        "id": f"seg_{uuid.uuid4().hex[:10]}",
                        "material_id": mat_id,
                        "target_timerange": {
                            "start": int(clip.start_us),
                            "duration": int(clip.duration_us),
                        },
                        "source_timerange": None,
                        "extra_material_refs": [],
                    }
                )
            tracks_out.append({"id": f"trk_{tr.id}", "type": "text", "segments": segs})

    draft_content = {
        "id": str(uuid.uuid4()).upper(),
        "name": safe_name,
        "duration": max_end_us,
        "fps": float(fps),
        "canvas_config": {
            "width": width,
            "height": height,
            "ratio": ratio,
        },
        "materials": {
            "videos": videos_mat,
            "audios": audios_mat,
            "texts": texts_mat,
            "transitions": transitions_mat,
            "animations": [],
        },
        "tracks": tracks_out,
    }

    validation_errors = validate_capcut_draft(draft_content)
    if validation_errors:
        raise ValueError(f"Invalid CapCut draft generated: {'; '.join(validation_errors)}")

    now_us = int(time.time() * 1_000_000)
    draft_meta = {
        "draft_id": draft_content["id"],
        "draft_name": safe_name,
        "draft_fold_path": str(draft_dir.resolve()),
        "tm_draft_create": now_us,
        "tm_draft_modified": now_us,
        "tm_duration": max_end_us,
    }

    content_file = draft_dir / "draft_content.json"
    meta_file = draft_dir / "draft_meta_info.json"

    tmp_c = content_file.with_suffix(".tmp")
    tmp_c.write_text(json.dumps(draft_content, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_c, content_file)

    tmp_m = meta_file.with_suffix(".tmp")
    tmp_m.write_text(json.dumps(draft_meta, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_m, meta_file)

    return {
        "draft_dir": str(draft_dir.resolve()),
        "draft_content_path": str(content_file.resolve()),
        "draft_meta_path": str(meta_file.resolve()),
        "duration_us": max_end_us,
        "tracks_count": len(tracks_out),
    }


def export_otio_json(timeline: TimelineModel, output_path: Path) -> Path:
    """Exports an OpenTimelineIO (.otio) JSON representation for NLE interoperability."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fps = timeline.canvas.fps.float_val
    otio_tracks = []
    for tr in timeline.tracks:
        children = []
        for clip in tr.clips:
            dur_frames = int(round((clip.duration_us / 1_000_000.0) * fps))
            start_frames = int(round((clip.source_in_us / 1_000_000.0) * fps))
            children.append(
                {
                    "OTIO_SCHEMA": "Clip.2",
                    "name": clip.id,
                    "source_range": {
                        "OTIO_SCHEMA": "TimeRange.1",
                        "start_time": {"OTIO_SCHEMA": "RationalTime.1", "value": start_frames, "rate": fps},
                        "duration": {"OTIO_SCHEMA": "RationalTime.1", "value": dur_frames, "rate": fps},
                    },
                    "media_reference": {
                        "OTIO_SCHEMA": "ExternalReference.1",
                        "target_url": clip.asset_id or "",
                    },
                }
            )
        otio_tracks.append(
            {
                "OTIO_SCHEMA": "Track.1",
                "name": tr.name,
                "kind": "Audio" if tr.kind == "audio" else "Video",
                "children": children,
            }
        )

    doc = {
        "OTIO_SCHEMA": "Timeline.1",
        "name": "VidForge Timeline",
        "tracks": {
            "OTIO_SCHEMA": "Stack.1",
            "name": "tracks",
            "children": otio_tracks,
        },
    }
    output_path.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return output_path
