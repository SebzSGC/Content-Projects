"""Exportador de EditPlan v2 a proyecto nativo FilmCraft (.fcproj)."""

from __future__ import annotations

import hashlib
import json
import subprocess
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from clipseditplan import CropKeyframe, EditPlan

from ..audio import generate_ducking_keyframes
from ..base import ExportContext, ExportResult, FidelityWarning, SessionClipSpec
from ..geometry import compute_motion_transform, get_layout_regions
from ..timebase import TICKS_PER_SECOND, seconds_to_ticks

EXPORTER_VERSION = "0.3.0"
FILMCRAFT_SCHEMA_VERSION = 17
FILMCRAFT_GENERATOR = "FilmCraft 0.20.1"


def generate_srt(plan: EditPlan) -> str:
    """Genera subtítulos en formato SubRip (.srt) a partir de los grupos de captions del EditPlan."""
    lines = []
    if not plan.captions or not plan.captions.groups:
        return ""
    for idx, group in enumerate(plan.captions.groups, start=1):
        words = getattr(group, "words", [])
        if not words:
            continue
        g_start = float(words[0].s)
        g_end = float(words[-1].e)
        text = " ".join(getattr(w, "w", getattr(w, "text", "")) for w in words).strip()
        if not text:
            continue

        def srt_time(s: float) -> str:
            ms = int(round(max(0.0, s) * 1000))
            h, rem = divmod(ms, 3600000)
            m, rem = divmod(rem, 60000)
            sec, mill = divmod(rem, 1000)
            return f"{h:02d}:{m:02d}:{sec:02d},{mill:03d}"

        lines.append(f"{idx}\n{srt_time(g_start)} --> {srt_time(g_end)}\n{text}\n")
    return "\n".join(lines)


def _make_video_track(track_id: int, name: str, items: List[Dict[str, Any]], enabled: bool = True) -> Dict[str, Any]:
    return {
        "id": track_id,
        "kind": "Video",
        "name": name,
        "items": items,
        "transitions": [],
        "locked": False,
        "sync_lock": True,
        "enabled": enabled,
        "muted": False,
        "solo": False,
        "channels": "Stereo",
        "volume_db": 0.0,
        "pan": 0.0,
        "effects": [],
        "mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
    }


def _make_audio_track(track_id: int, name: str, items: List[Dict[str, Any]], enabled: bool = True) -> Dict[str, Any]:
    return {
        "id": track_id,
        "kind": "Audio",
        "name": name,
        "items": items,
        "transitions": [],
        "locked": False,
        "sync_lock": True,
        "enabled": enabled,
        "muted": False,
        "solo": False,
        "channels": "Stereo",
        "volume_db": 0.0,
        "pan": 0.0,
        "effects": [],
        "mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
    }


def _make_motion_effects(
    anchor_x: float,
    anchor_y: float,
    pos_x: float,
    pos_y: float,
    scale_pct: float,
    opacity_pct: float = 100.0,
    pos_keyframes: Optional[List[Dict[str, Any]]] = None,
    scale_keyframes: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    pos_param: Dict[str, Any] = {"value": {"Vec2": {"x": pos_x, "y": pos_y}}}
    scale_param: Dict[str, Any] = {"value": {"Float": scale_pct}}
    if pos_keyframes:
        pos_param["keyframes"] = pos_keyframes
    if scale_keyframes:
        scale_param["keyframes"] = scale_keyframes
    return [
        {
            "effect": "motion",
            "enabled": True,
            "params": {
                "anchor": {"value": {"Vec2": {"x": anchor_x, "y": anchor_y}}},
                "anti_flicker": {"value": {"Float": 0.0}},
                "position": pos_param,
                "rotation": {"value": {"Float": 0.0}},
                "scale": scale_param,
                "scale_width": {"value": {"Float": 100.0}},
                "uniform_scale": {"value": {"Bool": True}},
            },
        },
        {
            "effect": "opacity",
            "enabled": True,
            "params": {
                "blend": {"value": {"Choice": 0}},
                "opacity": {"value": {"Float": opacity_pct}},
            },
        },
        {"effect": "time_remap", "enabled": True, "params": {"speed": {"value": {"Float": 100.0}}}},
    ]


def _make_audio_effects(level_param: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        {
            "effect": "volume",
            "enabled": True,
            "params": {
                "bypass": {"value": {"Bool": False}},
                "level": level_param,
            },
        },
        {
            "effect": "channel_volume",
            "enabled": True,
            "params": {
                "bypass": {"value": {"Bool": False}},
                "left": {"value": {"Float": 0.0}},
                "right": {"value": {"Float": 0.0}},
            },
        },
        {"effect": "panner", "enabled": True, "params": {"balance": {"value": {"Float": 0.0}}}},
    ]


def _make_track_item(
    item_id: int,
    media_or_seq_id: int,
    name: str,
    label: str,
    start_ticks: int,
    duration_ticks: int,
    source_in_ticks: int,
    effects: List[Dict[str, Any]],
    enabled: bool = True,
) -> Dict[str, Any]:
    return {
        "id": item_id,
        "item": media_or_seq_id,
        "name": name,
        "label": label,
        "start": start_ticks,
        "duration": duration_ticks,
        "source_in": source_in_ticks,
        "speed": 1.0,
        "reverse": False,
        "enabled": enabled,
        "link": None,
        "group": None,
        "effects": effects,
        "markers": [],
        "gain_db": 0.0,
        "frame_hold": None,
        "scale_to_frame": False,
    }


def _make_sequence_settings(width: int, height: int, fps: Fraction, preset: str) -> Dict[str, Any]:
    return {
        "width": width,
        "height": height,
        "frame_rate": {"num": int(fps.numerator), "den": int(fps.denominator)},
        "par": [1, 1],
        "sample_rate": 48000,
        "drop_frame": False,
        "display": "Timecode",
        "preset": preset,
        "audio_master": "Stereo",
        "preview_codec": "ProRes 422",
        "max_bit_depth": False,
        "max_render_quality": False,
        "working_space": "Rec. 709",
        "color": {"working": "Rec709", "wide_gamut": False, "auto_tone_map": True},
    }


def _make_media_item(
    item_id: int,
    file_path: Path,
    width: int,
    height: int,
    fps: Fraction,
    duration_ticks: int,
    label: str = "Iris",
) -> Dict[str, Any]:
    return {
        "id": item_id,
        "name": file_path.name,
        "label": label,
        "kind": {
            "Media": {
                "media": {"File": {"path": str(file_path.resolve())}},
                "info": {
                    "name": file_path.name,
                    "kind": "Movie",
                    "duration": duration_ticks,
                    "video": {
                        "width": width,
                        "height": height,
                        "frame_rate": {"num": int(fps.numerator), "den": int(fps.denominator)},
                        "par": [1, 1],
                        "codec": "H.264",
                        "pixel_format": "YUV 4:2:0 8-bit",
                        "color": {"matrix": "Bt709", "transfer": "Bt709", "primaries": "Bt709", "range": "Limited"},
                        "has_alpha": False,
                        "bitrate": None,
                    },
                    "audio_streams": [
                        {"sample_rate": 48000, "channels": 2, "codec": "AAC", "bits_per_sample": None}
                    ],
                    "container": "MPEG-4",
                    "start_timecode": None,
                    "file_size": None,
                },
                "interpret": {"frame_rate": None, "par": None, "ignore_alpha": False, "invert_alpha": False},
                "mark_in": None,
                "mark_out": None,
                "markers": [],
                "offline": False,
                "proxy": None,
            }
        },
        "metadata": {},
        "created": item_id,
    }


class FilmCraftExporter:
    """Convierte deterministamente EditPlan v2 (individual o sesión completa) en proyectos FilmCraft (.fcproj)."""

    name: str = "filmcraft"
    version: str = EXPORTER_VERSION

    def _build_clip_sequence(
        self,
        *,
        plan: EditPlan,
        ctx: ExportContext,
        voice_spans: List[Tuple[float, float]],
        seq_name: str,
        clip_id: str,
        gameplay_id: int,
        camera_id: int,
        fps: Fraction,
        overlay_dir: Path,
        items: Dict[str, Any],
        alloc_id: Any,
        warnings: List[FidelityWarning],
    ) -> Tuple[int, float, Optional[int], str]:
        """Construye una secuencia vertical 1080x1920 para un clip y la registra en items."""
        if callable(getattr(plan, "plan_hash", None)):
            plan_hash = plan.plan_hash()
        else:
            plan_hash = str(getattr(plan, "plan_hash", "") or "default_hash")

        v1_items: List[Dict[str, Any]] = []
        v2_items: List[Dict[str, Any]] = []
        v3_items: List[Dict[str, Any]] = []
        a1_items: List[Dict[str, Any]] = []
        a2_items: List[Dict[str, Any]] = []
        a3_items: List[Dict[str, Any]] = []

        timeline_acc_s = 0.0
        ranges = plan.source.ranges if plan.source and plan.source.ranges else [(0.0, 10.0)]

        base_layout = plan.layout[0] if getattr(plan, "layout", None) else None
        layout_name = getattr(base_layout, "kind", "split") if base_layout else "split"
        camera_ratio = float(getattr(base_layout, "camera_ratio", 0.40) or 0.40)
        regions = get_layout_regions(layout_name, camera_ratio=camera_ratio, canvas_w=1080, canvas_h=1920)

        mic_gain_db = float(plan.audio.mic_gain_db) if plan.audio and plan.audio.mic_gain_db is not None else 0.0
        duck_game_db = float(plan.audio.duck_game_db) if plan.audio and plan.audio.duck_game_db is not None else -18.0

        duck_kfs = generate_ducking_keyframes(
            voice_spans=voice_spans,
            duck_gain_db=duck_game_db,
            base_gain_db=0.0,
            fps=fps,
        )

        cam_w = ctx.camera_width or 1920
        cam_h = ctx.camera_height or 1080
        game_w = ctx.gameplay_width or 1920
        game_h = ctx.gameplay_height or 1080

        for seg_idx, (r_start, r_end) in enumerate(ranges):
            dur_s = max(0.01, r_end - r_start)
            clip_start_ticks = seconds_to_ticks(timeline_acc_s, fps=fps)
            clip_dur_ticks = seconds_to_ticks(dur_s, fps=fps)

            gameplay_in_ticks = seconds_to_ticks(r_start, fps=fps)
            camera_in_s = max(0.0, r_start + ctx.camera_offset_s)
            camera_in_ticks = seconds_to_ticks(camera_in_s, fps=fps)

            # --- PISTA V1: CÁMARA ---
            cam_kfs: List[CropKeyframe] = []
            if plan.camera_crop:
                seg_clip_start = timeline_acc_s
                seg_clip_end = timeline_acc_s + dur_s
                cam_kfs = [k for k in plan.camera_crop if seg_clip_start <= k.t <= seg_clip_end]

            cam_xform = compute_motion_transform(
                source_w=cam_w,
                source_h=cam_h,
                region=regions.camera,
                cx=0.5,
                cy=0.5,
                zoom=1.0,
                anchor_y=0.44,
            )

            pos_keyframes: Optional[List[Dict[str, Any]]] = None
            scale_keyframes: Optional[List[Dict[str, Any]]] = None
            if cam_kfs:
                pos_keyframes = []
                scale_keyframes = []
                for k in cam_kfs:
                    k_rel_s = max(0.0, k.t - timeline_acc_s)
                    k_media_ticks = camera_in_ticks + seconds_to_ticks(k_rel_s, fps=fps)
                    kf_xform = compute_motion_transform(
                        source_w=cam_w,
                        source_h=cam_h,
                        region=regions.camera,
                        cx=float(k.cx),
                        cy=float(k.cy),
                        zoom=float(k.zoom),
                        anchor_y=0.44,
                    )
                    interp_mode = "Linear"
                    if getattr(k, "ease", None) in ("inOutSine", "outCubic", "outBack"):
                        interp_mode = "Bezier"
                        warnings.append(
                            FidelityWarning(
                                field="camera_crop.ease",
                                message=f"Easing '{k.ease}' aproximado a Bezier en t={k.t:.2f}s",
                            )
                        )
                    pos_keyframes.append({
                        "time": k_media_ticks,
                        "value": {"Vec2": {"x": kf_xform.position_x, "y": kf_xform.position_y}},
                        "interp": interp_mode,
                        "out_influence": 0.3333333333333333,
                        "in_influence": 0.3333333333333333,
                    })
                    scale_keyframes.append({
                        "time": k_media_ticks,
                        "value": {"Float": kf_xform.scale_pct},
                        "interp": interp_mode,
                        "out_influence": 0.3333333333333333,
                        "in_influence": 0.3333333333333333,
                    })

            v1_items.append(
                _make_track_item(
                    item_id=alloc_id(),
                    media_or_seq_id=camera_id,
                    name=f"Camara_seg{seg_idx + 1}",
                    label="Iris",
                    start_ticks=clip_start_ticks,
                    duration_ticks=clip_dur_ticks,
                    source_in_ticks=camera_in_ticks,
                    effects=_make_motion_effects(
                        cam_xform.anchor_x,
                        cam_xform.anchor_y,
                        cam_xform.position_x,
                        cam_xform.position_y,
                        cam_xform.scale_pct,
                        cam_xform.opacity_pct,
                        pos_keyframes=pos_keyframes,
                        scale_keyframes=scale_keyframes,
                    ),
                )
            )

            # --- PISTA V2: GAMEPLAY ---
            game_kfs: List[Any] = []
            if getattr(plan, "gameplay_crop", None):
                seg_clip_start = timeline_acc_s
                seg_clip_end = timeline_acc_s + dur_s
                game_kfs = [k for k in plan.gameplay_crop if seg_clip_start <= k.t <= seg_clip_end]

            game_xform = compute_motion_transform(
                source_w=game_w,
                source_h=game_h,
                region=regions.gameplay,
                cx=0.5,
                cy=0.5,
                zoom=1.0,
            )

            g_pos_keyframes: Optional[List[Dict[str, Any]]] = None
            g_scale_keyframes: Optional[List[Dict[str, Any]]] = None
            if game_kfs:
                g_pos_keyframes = []
                g_scale_keyframes = []
                for k in game_kfs:
                    k_rel_s = max(0.0, k.t - timeline_acc_s)
                    k_media_ticks = gameplay_in_ticks + seconds_to_ticks(k_rel_s, fps=fps)
                    kf_g_xform = compute_motion_transform(
                        source_w=game_w,
                        source_h=game_h,
                        region=regions.gameplay,
                        cx=float(k.cx),
                        cy=float(k.cy),
                        zoom=float(k.zoom),
                    )
                    g_pos_keyframes.append({
                        "time": k_media_ticks,
                        "value": {"Vec2": {"x": kf_g_xform.position_x, "y": kf_g_xform.position_y}},
                        "interp": "Linear",
                        "out_influence": 0.3333333333333333,
                        "in_influence": 0.3333333333333333,
                    })
                    g_scale_keyframes.append({
                        "time": k_media_ticks,
                        "value": {"Float": kf_g_xform.scale_pct},
                        "interp": "Linear",
                        "out_influence": 0.3333333333333333,
                        "in_influence": 0.3333333333333333,
                    })

            v2_items.append(
                _make_track_item(
                    item_id=alloc_id(),
                    media_or_seq_id=gameplay_id,
                    name=f"Gameplay_seg{seg_idx + 1}",
                    label="Iris",
                    start_ticks=clip_start_ticks,
                    duration_ticks=clip_dur_ticks,
                    source_in_ticks=gameplay_in_ticks,
                    effects=_make_motion_effects(
                        game_xform.anchor_x,
                        game_xform.anchor_y,
                        game_xform.position_x,
                        game_xform.position_y,
                        game_xform.scale_pct,
                        game_xform.opacity_pct,
                        pos_keyframes=g_pos_keyframes,
                        scale_keyframes=g_scale_keyframes,
                    ),
                )
            )

            # Audio A1: Micrófono (cámara)
            a1_items.append(
                _make_track_item(
                    item_id=alloc_id(),
                    media_or_seq_id=camera_id,
                    name=f"Mic_seg{seg_idx + 1}",
                    label="Caribbean",
                    start_ticks=clip_start_ticks,
                    duration_ticks=clip_dur_ticks,
                    source_in_ticks=camera_in_ticks,
                    effects=_make_audio_effects({"value": {"Float": mic_gain_db}}),
                )
            )

            # Audio A2: Juego (gameplay) con keyframes de ducking
            seg_start_ticks = clip_start_ticks
            seg_end_ticks = clip_start_ticks + clip_dur_ticks
            clip_duck_kfs = [
                {
                    "time": gameplay_in_ticks + (k.time_ticks - seg_start_ticks),
                    "value": {"Float": k.level_db},
                    "interp": k.interp,
                    "out_influence": 0.3333333333333333,
                    "in_influence": 0.3333333333333333,
                }
                for k in duck_kfs
                if seg_start_ticks <= k.time_ticks <= seg_end_ticks
            ]
            a2_level_param: Dict[str, Any] = {"value": {"Float": 0.0}}
            if clip_duck_kfs:
                a2_level_param["keyframes"] = clip_duck_kfs

            a2_items.append(
                _make_track_item(
                    item_id=alloc_id(),
                    media_or_seq_id=gameplay_id,
                    name=f"Juego_seg{seg_idx + 1}",
                    label="Iris",
                    start_ticks=clip_start_ticks,
                    duration_ticks=clip_dur_ticks,
                    source_in_ticks=gameplay_in_ticks,
                    effects=_make_audio_effects(a2_level_param),
                )
            )

            timeline_acc_s += dur_s

        # 3. Capa de overlays y subtítulos
        overlay_id: Optional[int] = None
        has_overlays_or_caps = bool(
            (plan.captions and plan.captions.groups) or getattr(plan, "overlays", None)
        )
        if has_overlays_or_caps:
            try:
                from clipsrender.ass_compiler import compile_ass
                from clipsstyles import load_preset

                overlay_dir.mkdir(parents=True, exist_ok=True)
                preset = ctx.style if getattr(ctx, "style", None) else load_preset("hormozi-gaming")
                ass_content = compile_ass(plan, preset, 1080, 1920)
                ass_file = overlay_dir / "captions.ass"
                ass_file.write_text(ass_content, encoding="utf-8")

                srt_content = generate_srt(plan)
                if srt_content:
                    (overlay_dir / "captions.srt").write_text(srt_content, encoding="utf-8")

                overlay_mov = overlay_dir / "captions_overlay.mov"
                total_dur_s = timeline_acc_s
                if not overlay_mov.is_file() or overlay_mov.stat().st_size == 0:
                    escaped_ass = str(ass_file.resolve()).replace("\\", "/").replace(":", r"\:")
                    cmd = [
                        "ffmpeg", "-y",
                        "-f", "lavfi", "-i", f"color=c=black@0.0:s=1080x1920:r=60:d={total_dur_s:.3f},format=yuva444p10le",
                        "-vf", f"ass='{escaped_ass}':alpha=1",
                        "-c:v", "prores_ks", "-profile:v", "4444",
                        "-pix_fmt", "yuva444p10le",
                        str(overlay_mov),
                    ]
                    subprocess.run(cmd, check=True, capture_output=True, timeout=120)

                if overlay_mov.is_file() and overlay_mov.stat().st_size > 0:
                    overlay_id = alloc_id()
                    total_dur_ticks = seconds_to_ticks(total_dur_s, fps=fps)
                    items[str(overlay_id)] = {
                        "id": overlay_id,
                        "name": f"captions_{clip_id}.mov" if clip_id else "captions_overlay.mov",
                        "label": "Lavender",
                        "kind": {
                            "Media": {
                                "media": {"File": {"path": str(overlay_mov.resolve())}},
                                "info": {
                                    "name": "captions_overlay.mov",
                                    "kind": "Movie",
                                    "duration": total_dur_ticks,
                                    "video": {
                                        "width": 1080,
                                        "height": 1920,
                                        "frame_rate": {"num": int(fps.numerator), "den": int(fps.denominator)},
                                        "par": [1, 1],
                                        "codec": "Apple ProRes 4444",
                                        "pixel_format": "YUVA 4:4:4 12-bit",
                                        "color": {"matrix": "Bt709", "transfer": "Bt709", "primaries": "Bt709", "range": "Limited"},
                                        "has_alpha": True,
                                        "bitrate": None,
                                    },
                                    "audio_streams": [],
                                    "container": "QuickTime",
                                    "start_timecode": None,
                                    "file_size": overlay_mov.stat().st_size,
                                },
                                "interpret": {"frame_rate": None, "par": None, "ignore_alpha": False, "invert_alpha": False},
                                "mark_in": None,
                                "mark_out": None,
                                "markers": [],
                                "offline": False,
                                "proxy": None,
                            }
                        },
                        "metadata": {},
                        "created": overlay_id,
                    }
                    v3_items.append(
                        _make_track_item(
                            item_id=alloc_id(),
                            media_or_seq_id=overlay_id,
                            name="Captions & Overlays (Hormozi)",
                            label="Lavender",
                            start_ticks=0,
                            duration_ticks=total_dur_ticks,
                            source_in_ticks=0,
                            effects=_make_motion_effects(540.0, 960.0, 540.0, 960.0, 100.0, 100.0),
                            enabled=False,
                        )
                    )
            except Exception as exc:
                warnings.append(
                    FidelityWarning(
                        field="captions.overlay",
                        message=f"No se pudo renderizar la capa con canal alfa: {exc}",
                        severity="warning",
                    )
                )

        # 4. Marcadores y pista nativa de subtítulos interactivos (C1)
        markers: List[Dict[str, Any]] = []
        native_captions_list: List[Dict[str, Any]] = []

        if plan.captions and plan.captions.groups:
            for group in plan.captions.groups:
                words = getattr(group, "words", [])
                text = " ".join(getattr(w, "w", getattr(w, "text", "")) for w in words)
                if not text:
                    continue
                g_start = float(words[0].s) if words else float(getattr(group, "start", 0.0))
                g_end = float(words[-1].e) if words else float(getattr(group, "end", g_start + 1.0))
                m_start_ticks = seconds_to_ticks(g_start, fps=fps)
                m_dur_ticks = seconds_to_ticks(max(0.05, g_end - g_start), fps=fps)

                markers.append({
                    "id": alloc_id(),
                    "start": m_start_ticks,
                    "duration": m_dur_ticks,
                    "name": text[:30],
                    "comment": text,
                    "kind": "Comment",
                    "color": "Green",
                })
                native_captions_list.append({
                    "id": alloc_id(),
                    "start": m_start_ticks,
                    "duration": m_dur_ticks,
                    "text": text,
                    "speaker": None,
                    "cue_id": None,
                    "settings": "",
                })

        caption_tracks: List[Dict[str, Any]] = []
        if native_captions_list:
            caption_tracks.append({
                "id": alloc_id(),
                "name": "Subtitles",
                "format": "Subtitle",
                "language": "es",
                "style": {
                    "font": "Montserrat",
                    "font_style": "ExtraBold",
                    "size": 80.0,
                    "color": [255, 212, 0, 255],
                    "background": False,
                    "background_color": [0, 0, 0, 0],
                    "align": "Center",
                    "anchor": "Middle",
                    "margin": 0.032,
                    "line_spacing": 1.2,
                    "outline": 8.0,
                    "outline_color": [0, 0, 0, 255],
                },
                "enabled": True,
                "locked": False,
                "sync_lock": True,
                "captions": native_captions_list,
                "vtt_blocks": [],
            })

        # 5. Secuencia del clip (Item de tipo Sequence)
        seq_id = alloc_id()
        items[str(seq_id)] = {
            "id": seq_id,
            "name": seq_name,
            "label": "Forest",
            "kind": {
                "Sequence": {
                    "settings": _make_sequence_settings(1080, 1920, fps, "Vertical 1080x1920 60fps"),
                    "video_tracks": [
                        _make_video_track(alloc_id(), "V1 Cámara", v1_items),
                        _make_video_track(alloc_id(), "V2 Gameplay", v2_items),
                        _make_video_track(alloc_id(), "V3 Overlays", v3_items),
                    ],
                    "audio_tracks": [
                        _make_audio_track(alloc_id(), "A1 Mic", a1_items),
                        _make_audio_track(alloc_id(), "A2 Juego", a2_items),
                        _make_audio_track(alloc_id(), "A3 SFX", a3_items),
                    ],
                    "markers": markers,
                    "mark_in": None,
                    "mark_out": None,
                    "work_area": None,
                    "start_timecode": 0,
                    "master_volume_db": 0.0,
                    "master_effects": [],
                    "master_mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
                    "submix_tracks": [],
                    "caption_tracks": caption_tracks,
                }
            },
            "metadata": {
                "farmclips": json.dumps({
                    "clip_id": clip_id,
                    "session_id": ctx.session_id,
                    "plan_hash": plan_hash,
                    "exporter_version": EXPORTER_VERSION,
                }, ensure_ascii=False)
            },
            "created": seq_id,
        }
        return seq_id, timeline_acc_s, overlay_id, plan_hash

    @staticmethod
    def _assemble_project_dict(
        *,
        project_name: str,
        root_children: List[Dict[str, Any]],
        items: Dict[str, Any],
        next_id: int,
        open_sequences: List[int],
        active_sequence: int,
    ) -> Dict[str, Any]:
        return {
            "format": "filmcraft.project",
            "schema_version": FILMCRAFT_SCHEMA_VERSION,
            "generator": FILMCRAFT_GENERATOR,
            "project": {
                "name": project_name,
                "settings": {
                    "renderer": "FilmCraft GPU Acceleration (wgpu)",
                    "video_display": "Timecode",
                    "audio_display_samples": True,
                    "default_still_duration": 1270080000000,
                    "default_transition_duration_frames": 24,
                    "default_audio_transition_duration": 254016000000,
                    "ingest": {"enabled": False, "action": "createProxies", "destination": None, "preset": ""},
                    "title_safe": [20.0, 20.0],
                    "action_safe": [10.0, 10.0],
                    "capture_format": "DV",
                    "scratch": {"captured": None, "videoPreviews": None, "audioPreviews": None, "autoSave": None},
                },
                "root": {
                    "id": 0,
                    "name": project_name,
                    "children": root_children,
                },
                "items": items,
                "next_id": next_id + 100,
            },
            "view": {
                "open_sequences": open_sequences,
                "active_sequence": active_sequence,
                "sequences": {},
                "playheads": {str(sid): 0 for sid in open_sequences},
            },
        }

    def export(self, plan: EditPlan, ctx: ExportContext, out_dir: Path) -> ExportResult:
        """Exporta el EditPlan de un clip individual a un archivo clip.fcproj en out_dir."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        warnings: List[FidelityWarning] = []
        fps = ctx.source_fps or Fraction(60, 1)

        # Reserva IDs 0..4 para root y bins estándar
        next_id = 10

        def alloc_id() -> int:
            nonlocal next_id
            curr = next_id
            next_id += 1
            return curr

        gameplay_id = alloc_id()
        camera_id = alloc_id()
        default_dur_s = max(ctx.gameplay_duration_s or 0.0, 4 * 3600.0)
        cam_dur_s = max(ctx.camera_duration_s or 0.0, 4 * 3600.0)

        items: Dict[str, Any] = {
            str(gameplay_id): _make_media_item(
                gameplay_id,
                ctx.gameplay_path,
                ctx.gameplay_width or 1920,
                ctx.gameplay_height or 1080,
                fps,
                seconds_to_ticks(default_dur_s, fps=fps),
            ),
            str(camera_id): _make_media_item(
                camera_id,
                ctx.camera_path,
                ctx.camera_width or 1920,
                ctx.camera_height or 1080,
                fps,
                seconds_to_ticks(cam_dur_s, fps=fps),
            ),
        }

        clip_name = getattr(plan, "clip_id", None) or ctx.clip_id or "Clip"
        seq_id, duration_s, _, plan_hash = self._build_clip_sequence(
            plan=plan,
            ctx=ctx,
            voice_spans=ctx.voice_spans,
            seq_name=clip_name,
            clip_id=ctx.clip_id or clip_name,
            gameplay_id=gameplay_id,
            camera_id=camera_id,
            fps=fps,
            overlay_dir=out_dir,
            items=items,
            alloc_id=alloc_id,
            warnings=warnings,
        )

        project_name = f"{clip_name}_{plan_hash[:8]}" if plan_hash else clip_name
        root_children = [
            {"Bin": {"id": 1, "name": "Footage", "children": [{"Item": gameplay_id}, {"Item": camera_id}]}},
            {"Bin": {"id": 2, "name": "Audio", "children": []}},
            {"Bin": {"id": 3, "name": "Graphics", "children": []}},
            {"Bin": {"id": 4, "name": "Sequences", "children": [{"Item": seq_id}]}},
        ]

        project_dict = self._assemble_project_dict(
            project_name=project_name,
            root_children=root_children,
            items=items,
            next_id=next_id,
            open_sequences=[seq_id],
            active_sequence=seq_id,
        )

        project_file = out_dir / "clip.fcproj"
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(project_dict, f, indent=2, ensure_ascii=False)

        return ExportResult(
            project_path=project_file,
            exporter=self.name,
            exporter_version=self.version,
            plan_hash=plan_hash,
            duration_s=round(duration_s, 3),
            warnings=warnings,
        )

    def export_session(
        self,
        clips: List[SessionClipSpec],
        ctx: ExportContext,
        out_dir: Path,
    ) -> ExportResult:
        """Exporta la sesión completa con secuencia Master del VOD y sub-secuencias anidadas por clip."""
        if not clips:
            raise ValueError("Se requiere al menos un clip para exportar la sesión a FilmCraft.")

        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        warnings: List[FidelityWarning] = []
        fps = ctx.source_fps or Fraction(60, 1)

        next_id = 20

        def alloc_id() -> int:
            nonlocal next_id
            curr = next_id
            next_id += 1
            return curr

        # Calcular duración real o estimada del VOD
        max_clip_end = max(
            [c.end_s for c in clips]
            + [float(r[1]) for c in clips for r in (c.plan.source.ranges if c.plan.source else [])]
            + [60.0]
        )
        vod_dur_s = float(ctx.gameplay_duration_s) if (ctx.gameplay_duration_s and ctx.gameplay_duration_s > 0) else max_clip_end
        vod_dur_s = max(vod_dur_s, max_clip_end)
        cam_dur_s = float(ctx.camera_duration_s) if (ctx.camera_duration_s and ctx.camera_duration_s > 0) else vod_dur_s

        master_w = ctx.gameplay_width or 1920
        master_h = ctx.gameplay_height or 1080
        cam_w = ctx.camera_width or 1920
        cam_h = ctx.camera_height or 1080

        gameplay_id = alloc_id()
        camera_id = alloc_id()

        items: Dict[str, Any] = {
            str(gameplay_id): _make_media_item(
                gameplay_id,
                ctx.gameplay_path,
                master_w,
                master_h,
                fps,
                seconds_to_ticks(vod_dur_s, fps=fps),
            ),
            str(camera_id): _make_media_item(
                camera_id,
                ctx.camera_path,
                cam_w,
                cam_h,
                fps,
                seconds_to_ticks(cam_dur_s, fps=fps),
            ),
        }

        # 1. Crear una sub-secuencia 9:16 por cada clip seleccionado
        subseq_records: List[Tuple[SessionClipSpec, int, float]] = []
        graphics_children: List[Dict[str, Any]] = []
        hasher = hashlib.sha256()

        for spec in clips:
            rank_prefix = f"#{spec.rank_order} " if spec.rank_order > 0 else ""
            raw_title = spec.title or spec.clip_id
            subseq_name = f"{rank_prefix}{raw_title}"[:60]

            clip_overlay_dir = out_dir / "clips" / spec.clip_id
            sub_id, sub_dur_s, overlay_id, sub_hash = self._build_clip_sequence(
                plan=spec.plan,
                ctx=ctx,
                voice_spans=spec.voice_spans,
                seq_name=subseq_name,
                clip_id=spec.clip_id,
                gameplay_id=gameplay_id,
                camera_id=camera_id,
                fps=fps,
                overlay_dir=clip_overlay_dir,
                items=items,
                alloc_id=alloc_id,
                warnings=warnings,
            )
            if overlay_id is not None:
                graphics_children.append({"Item": overlay_id})
            subseq_records.append((spec, sub_id, sub_dur_s))
            hasher.update(f"{spec.clip_id}:{sub_hash};".encode("utf-8"))

        combo_hash = hasher.hexdigest()[:16]

        # 2. Construir la Secuencia Master (VOD completo + sub-secuencias anidadas en marcas de tiempo)
        vod_dur_ticks = seconds_to_ticks(vod_dur_s, fps=fps)

        # Pista V1: VOD Gameplay completo
        v1_master_items = [
            _make_track_item(
                item_id=alloc_id(),
                media_or_seq_id=gameplay_id,
                name="VOD Gameplay (Completo)",
                label="Iris",
                start_ticks=0,
                duration_ticks=vod_dur_ticks,
                source_in_ticks=0,
                effects=_make_motion_effects(
                    master_w / 2.0,
                    master_h / 2.0,
                    master_w / 2.0,
                    master_h / 2.0,
                    100.0,
                ),
            )
        ]

        # Pista V2: VOD Cámara completa (referencia PiP desactivada por defecto para no tapar el juego)
        cam_offset = float(ctx.camera_offset_s or 0.0)
        if cam_offset >= 0:
            cam_track_start_s = 0.0
            cam_src_in_s = cam_offset
            cam_play_dur_s = max(0.01, min(vod_dur_s, cam_dur_s - cam_offset))
        else:
            cam_track_start_s = -cam_offset
            cam_src_in_s = 0.0
            cam_play_dur_s = max(0.01, min(vod_dur_s + cam_offset, cam_dur_s))

        v2_master_items = [
            _make_track_item(
                item_id=alloc_id(),
                media_or_seq_id=camera_id,
                name="VOD Cámara (Ref PiP)",
                label="Iris",
                start_ticks=seconds_to_ticks(cam_track_start_s, fps=fps),
                duration_ticks=seconds_to_ticks(cam_play_dur_s, fps=fps),
                source_in_ticks=seconds_to_ticks(cam_src_in_s, fps=fps),
                effects=_make_motion_effects(
                    cam_w / 2.0,
                    cam_h / 2.0,
                    master_w * 0.84,
                    master_h * 0.20,
                    28.0,
                ),
                enabled=False,
            )
        ]

        # Pistas V3+ : Sub-secuencias 9:16 anidadas colocadas en sus marcas de tiempo exactas del VOD
        clip_lanes: List[List[Dict[str, Any]]] = [[]]
        lane_end_ticks: List[int] = [0]
        master_markers: List[Dict[str, Any]] = []
        fit_scale_pct = round((master_h / 1920.0) * 100.0, 4)

        # Ordenar cronológicamente por inicio en el VOD para un empaquetado limpio
        sorted_records = sorted(
            subseq_records,
            key=lambda rec: (
                rec[0].plan.source.ranges[0][0]
                if rec[0].plan.source and rec[0].plan.source.ranges
                else rec[0].start_s
            ),
        )

        for spec, sub_id, _sub_dur_s in sorted_records:
            ranges = (
                spec.plan.source.ranges
                if spec.plan.source and spec.plan.source.ranges
                else [(spec.start_s, spec.end_s)]
            )
            first_start_ticks = seconds_to_ticks(float(ranges[0][0]), fps=fps)
            last_end_ticks = seconds_to_ticks(float(ranges[-1][1]), fps=fps)

            # Elegir carril donde no colisione con otro clip
            target_lane = -1
            for idx, end_t in enumerate(lane_end_ticks):
                if first_start_ticks >= end_t:
                    target_lane = idx
                    break
            if target_lane < 0:
                target_lane = len(clip_lanes)
                clip_lanes.append([])
                lane_end_ticks.append(0)

            rank_prefix = f"#{spec.rank_order} " if spec.rank_order > 0 else ""
            base_label = f"{rank_prefix}{spec.title or spec.clip_id}"

            sub_acc_s = 0.0
            for seg_idx, (r_start, r_end) in enumerate(ranges):
                r_dur_s = max(0.01, float(r_end) - float(r_start))
                slice_name = base_label if len(ranges) == 1 else f"{base_label} ({seg_idx + 1}/{len(ranges)})"
                clip_lanes[target_lane].append(
                    _make_track_item(
                        item_id=alloc_id(),
                        media_or_seq_id=sub_id,
                        name=slice_name[:60],
                        label="Forest",
                        start_ticks=seconds_to_ticks(float(r_start), fps=fps),
                        duration_ticks=seconds_to_ticks(r_dur_s, fps=fps),
                        source_in_ticks=seconds_to_ticks(sub_acc_s, fps=fps),
                        effects=_make_motion_effects(
                            540.0,
                            960.0,
                            master_w / 2.0,
                            master_h / 2.0,
                            fit_scale_pct,
                        ),
                    )
                )
                sub_acc_s += r_dur_s

            lane_end_ticks[target_lane] = max(lane_end_ticks[target_lane], last_end_ticks)

            # Marcador de timeline en la secuencia Master
            m_start_s = float(ranges[0][0])
            m_end_s = float(ranges[-1][1])
            m_dur_s = max(0.1, m_end_s - m_start_s)
            score_txt = f"Score {spec.score:.0f} | " if spec.score > 0 else ""
            comment_txt = f"{score_txt}{spec.reason}".strip()
            master_markers.append({
                "id": alloc_id(),
                "start": seconds_to_ticks(m_start_s, fps=fps),
                "duration": seconds_to_ticks(m_dur_s, fps=fps),
                "name": base_label[:40],
                "comment": comment_txt,
                "kind": "Comment",
                "color": "Green",
            })

        video_tracks = [
            _make_video_track(alloc_id(), "V1 VOD Gameplay", v1_master_items, enabled=True),
            _make_video_track(alloc_id(), "V2 VOD Cámara (Ref)", v2_master_items, enabled=False),
        ]
        for lane_idx, lane_items in enumerate(clip_lanes):
            track_name = "V3 Clips (Sub-secuencias)" if lane_idx == 0 else f"V{3 + lane_idx} Clips #{lane_idx + 1}"
            video_tracks.append(_make_video_track(alloc_id(), track_name, lane_items, enabled=True))

        # Pistas de audio del VOD completo (sincronizadas)
        a1_master_items = [
            _make_track_item(
                item_id=alloc_id(),
                media_or_seq_id=camera_id,
                name="A1 Mic (VOD Completo)",
                label="Caribbean",
                start_ticks=seconds_to_ticks(cam_track_start_s, fps=fps),
                duration_ticks=seconds_to_ticks(cam_play_dur_s, fps=fps),
                source_in_ticks=seconds_to_ticks(cam_src_in_s, fps=fps),
                effects=_make_audio_effects({"value": {"Float": 0.0}}),
            )
        ]
        a2_master_items = [
            _make_track_item(
                item_id=alloc_id(),
                media_or_seq_id=gameplay_id,
                name="A2 Juego (VOD Completo)",
                label="Iris",
                start_ticks=0,
                duration_ticks=vod_dur_ticks,
                source_in_ticks=0,
                effects=_make_audio_effects({"value": {"Float": 0.0}}),
            )
        ]

        seq_master_id = alloc_id()
        master_title = ctx.session_title or ctx.session_id or "Sesión"
        items[str(seq_master_id)] = {
            "id": seq_master_id,
            "name": f"Master · {master_title}"[:64],
            "label": "Mango",
            "kind": {
                "Sequence": {
                    "settings": _make_sequence_settings(master_w, master_h, fps, f"HD {master_w}x{master_h} 60fps"),
                    "video_tracks": video_tracks,
                    "audio_tracks": [
                        _make_audio_track(alloc_id(), "A1 Mic (VOD)", a1_master_items),
                        _make_audio_track(alloc_id(), "A2 Juego (VOD)", a2_master_items),
                    ],
                    "markers": master_markers,
                    "mark_in": None,
                    "mark_out": None,
                    "work_area": None,
                    "start_timecode": 0,
                    "master_volume_db": 0.0,
                    "master_effects": [],
                    "master_mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
                    "submix_tracks": [],
                    "caption_tracks": [],
                }
            },
            "metadata": {
                "farmclips": json.dumps({
                    "session_id": ctx.session_id,
                    "clip_ids": [c.clip_id for c in clips],
                    "plan_hash": combo_hash,
                    "exporter_version": EXPORTER_VERSION,
                    "mode": "session_master",
                }, ensure_ascii=False)
            },
            "created": seq_master_id,
        }

        subseq_ids = [sid for _, sid, _ in subseq_records]
        clips_bin_id = alloc_id()
        project_name = f"{master_title}_{combo_hash[:8]}"[:64]

        root_children = [
            {"Bin": {"id": 1, "name": "Footage", "children": [{"Item": gameplay_id}, {"Item": camera_id}]}},
            {"Bin": {"id": 2, "name": "Audio", "children": []}},
            {"Bin": {"id": 3, "name": "Graphics", "children": graphics_children}},
            {
                "Bin": {
                    "id": 4,
                    "name": "Sequences",
                    "children": [
                        {"Item": seq_master_id},
                        {
                            "Bin": {
                                "id": clips_bin_id,
                                "name": "Clips (9:16)",
                                "children": [{"Item": sid} for sid in subseq_ids],
                            }
                        },
                    ],
                }
            },
        ]

        open_sequences = [seq_master_id, *subseq_ids]
        project_dict = self._assemble_project_dict(
            project_name=project_name,
            root_children=root_children,
            items=items,
            next_id=next_id,
            open_sequences=open_sequences,
            active_sequence=seq_master_id,
        )

        project_file = out_dir / "session.fcproj"
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(project_dict, f, indent=2, ensure_ascii=False)

        return ExportResult(
            project_path=project_file,
            exporter=self.name,
            exporter_version=self.version,
            plan_hash=combo_hash,
            duration_s=round(vod_dur_s, 3),
            warnings=warnings,
        )
