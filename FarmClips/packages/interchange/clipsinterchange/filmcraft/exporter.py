"""Exportador de EditPlan v2 a proyecto nativo FilmCraft (.fcproj)."""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from clipseditplan import CropKeyframe, EditPlan

from ..audio import generate_ducking_keyframes
from ..base import ExportContext, ExportResult, FidelityWarning
from ..geometry import compute_motion_transform, get_layout_regions
from ..timebase import TICKS_PER_SECOND, seconds_to_ticks, ticks_to_seconds

EXPORTER_VERSION = "0.1.0"
FILMCRAFT_SCHEMA_VERSION = 17
FILMCRAFT_GENERATOR = "FilmCraft 0.20.1"


class FilmCraftExporter:
    """Convierte deterministamente un EditPlan v2 en un proyecto FilmCraft (.fcproj)."""

    name: str = "filmcraft"
    version: str = EXPORTER_VERSION

    def export(self, plan: EditPlan, ctx: ExportContext, out_dir: Path) -> ExportResult:
        """Exporta el EditPlan a un archivo .fcproj en out_dir."""
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

        warnings: List[FidelityWarning] = []
        fps = ctx.source_fps or Fraction(60, 1)
        if callable(getattr(plan, "plan_hash", None)):
            plan_hash = plan.plan_hash()
        else:
            plan_hash = str(getattr(plan, "plan_hash", "") or "default_hash")
        clip_name = getattr(plan, "clip_id", None) or ctx.clip_id or "Clip"
        project_name = f"{clip_name}_{plan_hash[:8]}" if plan_hash else clip_name

        # IDs incrementales para los elementos del proyecto
        next_id = 1

        def alloc_id() -> int:
            nonlocal next_id
            curr = next_id
            next_id += 1
            return curr

        # 1. Registro de archivos de medios (Footage)
        gameplay_id = alloc_id()
        camera_id = alloc_id()

        gameplay_abs = str(ctx.gameplay_path.resolve())
        camera_abs = str(ctx.camera_path.resolve())

        # Duración estimada de las fuentes (p. ej. 4 horas en ticks si no se especifica)
        default_footage_dur_ticks = 4 * 3600 * TICKS_PER_SECOND

        items: Dict[str, Any] = {
            str(gameplay_id): {
                "id": gameplay_id,
                "name": ctx.gameplay_path.name,
                "label": "Iris",
                "kind": {
                    "Media": {
                        "media": {"File": {"path": gameplay_abs}},
                        "info": {
                            "name": ctx.gameplay_path.name,
                            "kind": "Movie",
                            "duration": default_footage_dur_ticks,
                            "video": {
                                "width": 1920,
                                "height": 1080,
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
                "created": gameplay_id,
            },
            str(camera_id): {
                "id": camera_id,
                "name": ctx.camera_path.name,
                "label": "Iris",
                "kind": {
                    "Media": {
                        "media": {"File": {"path": camera_abs}},
                        "info": {
                            "name": ctx.camera_path.name,
                            "kind": "Movie",
                            "duration": default_footage_dur_ticks,
                            "video": {
                                "width": 1920,
                                "height": 1080,
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
                "created": camera_id,
            },
        }

        # 2. Construcción de pistas y clips para la secuencia
        v1_items: List[Dict[str, Any]] = []
        v2_items: List[Dict[str, Any]] = []
        a1_items: List[Dict[str, Any]] = []
        a2_items: List[Dict[str, Any]] = []
        a3_items: List[Dict[str, Any]] = []

        timeline_acc_s = 0.0
        ranges = plan.source.ranges if plan.source and plan.source.ranges else [(0.0, 10.0)]
        
        # Extraer layout base
        base_layout = plan.layout[0] if getattr(plan, "layout", None) else None
        layout_name = getattr(base_layout, "kind", "split") if base_layout else "split"
        camera_ratio = float(getattr(base_layout, "camera_ratio", 0.40) or 0.40)
        regions = get_layout_regions(layout_name, camera_ratio=camera_ratio, canvas_w=1080, canvas_h=1920)

        # Ganancias de audio
        mic_gain_db = float(plan.audio.mic_gain_db) if plan.audio and plan.audio.mic_gain_db is not None else 0.0
        duck_game_db = float(plan.audio.duck_game_db) if plan.audio and plan.audio.duck_game_db is not None else -18.0

        # Keyframes de ducking precomputados
        duck_kfs = generate_ducking_keyframes(
            voice_spans=ctx.voice_spans,
            duck_gain_db=duck_game_db,
            base_gain_db=0.0,
            fps=fps,
        )

        for seg_idx, (r_start, r_end) in enumerate(ranges):
            dur_s = max(0.01, r_end - r_start)
            clip_start_ticks = seconds_to_ticks(timeline_acc_s, fps=fps)
            clip_dur_ticks = seconds_to_ticks(dur_s, fps=fps)

            # In-points de origen
            gameplay_in_ticks = seconds_to_ticks(r_start, fps=fps)
            camera_in_s = max(0.0, r_start + ctx.camera_offset_s)
            camera_in_ticks = seconds_to_ticks(camera_in_s, fps=fps)

            # Efectos de geometría para Gameplay (V1)
            game_xform = compute_motion_transform(
                source_w=1920,
                source_h=1080,
                region=regions.gameplay,
                cx=0.5,
                cy=0.5,
                zoom=1.0,
            )
            v1_motion = {
                "effect": "motion",
                "enabled": True,
                "params": {
                    "anchor": {"value": {"Vec2": {"x": game_xform.anchor_x, "y": game_xform.anchor_y}}},
                    "anti_flicker": {"value": {"Float": 0.0}},
                    "position": {"value": {"Vec2": {"x": game_xform.position_x, "y": game_xform.position_y}}},
                    "rotation": {"value": {"Float": 0.0}},
                    "scale": {"value": {"Float": game_xform.scale_pct}},
                    "scale_width": {"value": {"Float": 100.0}},
                    "uniform_scale": {"value": {"Bool": True}},
                },
            }
            v1_opacity = {
                "effect": "opacity",
                "enabled": True,
                "params": {
                    "blend": {"value": {"Choice": 0}},
                    "opacity": {"value": {"Float": game_xform.opacity_pct}},
                },
            }
            v1_clip_id = alloc_id()
            v1_items.append({
                "id": v1_clip_id,
                "item": gameplay_id,
                "name": f"Gameplay_seg{seg_idx + 1}",
                "label": "Iris",
                "start": clip_start_ticks,
                "duration": clip_dur_ticks,
                "source_in": gameplay_in_ticks,
                "speed": 1.0,
                "reverse": False,
                "enabled": True,
                "link": None,
                "group": None,
                "effects": [v1_motion, v1_opacity, {"effect": "time_remap", "enabled": True, "params": {"speed": {"value": {"Float": 100.0}}}}],
                "markers": [],
                "gain_db": 0.0,
                "frame_hold": None,
                "scale_to_frame": False,
            })

            # Efectos de geometría para Cámara (V2) con keyframes
            cam_kfs: List[CropKeyframe] = []
            if plan.camera_crop:
                # Filtrar keyframes que caigan dentro del rango de tiempo de este segmento en el timeline
                seg_clip_start = timeline_acc_s
                seg_clip_end = timeline_acc_s + dur_s
                cam_kfs = [k for k in plan.camera_crop if seg_clip_start <= k.t <= seg_clip_end]

            cam_xform = compute_motion_transform(
                source_w=1920,
                source_h=1080,
                region=regions.camera,
                cx=0.5,
                cy=0.5,
                zoom=1.0,
                anchor_y=0.44,
            )

            # Construir keyframes de motion si existen
            pos_param: Dict[str, Any] = {"value": {"Vec2": {"x": cam_xform.position_x, "y": cam_xform.position_y}}}
            scale_param: Dict[str, Any] = {"value": {"Float": cam_xform.scale_pct}}

            if cam_kfs:
                pos_keyframes: List[Dict[str, Any]] = []
                scale_keyframes: List[Dict[str, Any]] = []
                for k in cam_kfs:
                    k_rel_s = max(0.0, k.t - timeline_acc_s)
                    k_ticks = seconds_to_ticks(k_rel_s, fps=fps)
                    kf_xform = compute_motion_transform(
                        source_w=1920,
                        source_h=1080,
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
                        "time": k_ticks,
                        "value": {"Vec2": {"x": kf_xform.position_x, "y": kf_xform.position_y}},
                        "interp": interp_mode,
                        "out_influence": 0.3333333333333333,
                        "in_influence": 0.3333333333333333,
                    })
                    scale_keyframes.append({
                        "time": k_ticks,
                        "value": {"Float": kf_xform.scale_pct},
                        "interp": interp_mode,
                        "out_influence": 0.3333333333333333,
                        "in_influence": 0.3333333333333333,
                    })
                pos_param["keyframes"] = pos_keyframes
                scale_param["keyframes"] = scale_keyframes

            v2_motion = {
                "effect": "motion",
                "enabled": True,
                "params": {
                    "anchor": {"value": {"Vec2": {"x": cam_xform.anchor_x, "y": cam_xform.anchor_y}}},
                    "anti_flicker": {"value": {"Float": 0.0}},
                    "position": pos_param,
                    "rotation": {"value": {"Float": 0.0}},
                    "scale": scale_param,
                    "scale_width": {"value": {"Float": 100.0}},
                    "uniform_scale": {"value": {"Bool": True}},
                },
            }
            v2_opacity = {
                "effect": "opacity",
                "enabled": True,
                "params": {
                    "blend": {"value": {"Choice": 0}},
                    "opacity": {"value": {"Float": cam_xform.opacity_pct}},
                },
            }
            v2_clip_id = alloc_id()
            v2_items.append({
                "id": v2_clip_id,
                "item": camera_id,
                "name": f"Camara_seg{seg_idx + 1}",
                "label": "Iris",
                "start": clip_start_ticks,
                "duration": clip_dur_ticks,
                "source_in": camera_in_ticks,
                "speed": 1.0,
                "reverse": False,
                "enabled": True,
                "link": None,
                "group": None,
                "effects": [v2_motion, v2_opacity, {"effect": "time_remap", "enabled": True, "params": {"speed": {"value": {"Float": 100.0}}}}],
                "markers": [],
                "gain_db": 0.0,
                "frame_hold": None,
                "scale_to_frame": False,
            })

            # Audio A1: Micrófono (cámara)
            a1_clip_id = alloc_id()
            a1_items.append({
                "id": a1_clip_id,
                "item": camera_id,
                "name": f"Mic_seg{seg_idx + 1}",
                "label": "Caribbean",
                "start": clip_start_ticks,
                "duration": clip_dur_ticks,
                "source_in": camera_in_ticks,
                "speed": 1.0,
                "reverse": False,
                "enabled": True,
                "link": None,
                "group": None,
                "effects": [
                    {
                        "effect": "volume",
                        "enabled": True,
                        "params": {
                            "bypass": {"value": {"Bool": False}},
                            "level": {"value": {"Float": mic_gain_db}},
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
                ],
                "markers": [],
                "gain_db": 0.0,
                "frame_hold": None,
                "scale_to_frame": False,
            })

            # Audio A2: Juego (gameplay) con keyframes de ducking
            seg_start_ticks = clip_start_ticks
            seg_end_ticks = clip_start_ticks + clip_dur_ticks
            clip_duck_kfs = [
                {
                    "time": k.time_ticks - seg_start_ticks,
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

            a2_clip_id = alloc_id()
            a2_items.append({
                "id": a2_clip_id,
                "item": gameplay_id,
                "name": f"Juego_seg{seg_idx + 1}",
                "label": "Iris",
                "start": clip_start_ticks,
                "duration": clip_dur_ticks,
                "source_in": gameplay_in_ticks,
                "speed": 1.0,
                "reverse": False,
                "enabled": True,
                "link": None,
                "group": None,
                "effects": [
                    {
                        "effect": "volume",
                        "enabled": True,
                        "params": {
                            "bypass": {"value": {"Bool": False}},
                            "level": a2_level_param,
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
                ],
                "markers": [],
                "gain_db": 0.0,
                "frame_hold": None,
                "scale_to_frame": False,
            })

            timeline_acc_s += dur_s

        # 3. Marcadores de captions para navegación y edición rápida
        markers: List[Dict[str, Any]] = []
        if plan.captions and plan.captions.groups:
            for g_idx, group in enumerate(plan.captions.groups):
                words = getattr(group, "words", [])
                text = " ".join(getattr(w, "w", getattr(w, "text", "")) for w in words)
                if not text:
                    text = f"Caption {g_idx + 1}"
                g_start = float(words[0].s) if words else float(getattr(group, "start", 0.0))
                g_end = float(words[-1].e) if words else float(getattr(group, "end", g_start + 1.0))
                m_start_ticks = seconds_to_ticks(g_start, fps=fps)
                m_dur_ticks = seconds_to_ticks(max(0.05, g_end - g_start), fps=fps)

                markers.append({
                    "id": 800000 + g_idx,
                    "start": m_start_ticks,
                    "duration": m_dur_ticks,
                    "name": text[:30],
                    "comment": text,
                    "kind": "Comment",
                    "color": "Green",
                })

        # 4. Secuencia principal (Item de tipo Sequence)
        seq_id = alloc_id()
        items[str(seq_id)] = {
            "id": seq_id,
            "name": clip_name,
            "label": "Forest",
            "kind": {
                "Sequence": {
                    "settings": {
                        "width": 1080,
                        "height": 1920,
                        "frame_rate": {"num": int(fps.numerator), "den": int(fps.denominator)},
                        "par": [1, 1],
                        "sample_rate": 48000,
                        "drop_frame": False,
                        "display": "Timecode",
                        "preset": "Vertical 1080x1920 60fps",
                        "audio_master": "Stereo",
                        "preview_codec": "ProRes 422",
                        "max_bit_depth": False,
                        "max_render_quality": False,
                        "working_space": "Rec. 709",
                        "color": {"working": "Rec709", "wide_gamut": False, "auto_tone_map": True},
                    },
                    "video_tracks": [
                        {
                            "id": 101,
                            "kind": "Video",
                            "name": "V1 Gameplay",
                            "items": v1_items,
                            "transitions": [],
                            "locked": False,
                            "sync_lock": True,
                            "enabled": True,
                            "muted": False,
                            "solo": False,
                            "channels": "Stereo",
                            "volume_db": 0.0,
                            "pan": 0.0,
                            "effects": [],
                            "mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
                        },
                        {
                            "id": 102,
                            "kind": "Video",
                            "name": "V2 Cámara",
                            "items": v2_items,
                            "transitions": [],
                            "locked": False,
                            "sync_lock": True,
                            "enabled": True,
                            "muted": False,
                            "solo": False,
                            "channels": "Stereo",
                            "volume_db": 0.0,
                            "pan": 0.0,
                            "effects": [],
                            "mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
                        },
                        {
                            "id": 103,
                            "kind": "Video",
                            "name": "V3 Overlays",
                            "items": [],
                            "transitions": [],
                            "locked": False,
                            "sync_lock": True,
                            "enabled": True,
                            "muted": False,
                            "solo": False,
                            "channels": "Stereo",
                            "volume_db": 0.0,
                            "pan": 0.0,
                            "effects": [],
                            "mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
                        },
                    ],
                    "audio_tracks": [
                        {
                            "id": 201,
                            "kind": "Audio",
                            "name": "A1 Mic",
                            "items": a1_items,
                            "transitions": [],
                            "locked": False,
                            "sync_lock": True,
                            "enabled": True,
                            "muted": False,
                            "solo": False,
                            "channels": "Stereo",
                            "volume_db": 0.0,
                            "pan": 0.0,
                            "effects": [],
                            "mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
                        },
                        {
                            "id": 202,
                            "kind": "Audio",
                            "name": "A2 Juego",
                            "items": a2_items,
                            "transitions": [],
                            "locked": False,
                            "sync_lock": True,
                            "enabled": True,
                            "muted": False,
                            "solo": False,
                            "channels": "Stereo",
                            "volume_db": 0.0,
                            "pan": 0.0,
                            "effects": [],
                            "mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
                        },
                        {
                            "id": 203,
                            "kind": "Audio",
                            "name": "A3 SFX",
                            "items": a3_items,
                            "transitions": [],
                            "locked": False,
                            "sync_lock": True,
                            "enabled": True,
                            "muted": False,
                            "solo": False,
                            "channels": "Stereo",
                            "volume_db": 0.0,
                            "pan": 0.0,
                            "effects": [],
                            "mixer": {"mode": "Read", "output": None, "record_arm": False, "solo_safe": False, "input_map": "Stereo"},
                        },
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
                    "caption_tracks": [],
                }
            },
            "metadata": {
                "farmclips": json.dumps({
                    "clip_id": ctx.clip_id,
                    "session_id": ctx.session_id,
                    "plan_hash": plan_hash,
                    "exporter_version": EXPORTER_VERSION,
                }, ensure_ascii=False)
            },
            "created": seq_id,
        }

        # 5. Ensamblado del documento final .fcproj
        project_dict: Dict[str, Any] = {
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
                    "children": [
                        {"Bin": {"id": 1, "name": "Footage", "children": [{"Item": gameplay_id}, {"Item": camera_id}]}},
                        {"Bin": {"id": 2, "name": "Audio", "children": []}},
                        {"Bin": {"id": 3, "name": "Graphics", "children": []}},
                        {"Bin": {"id": 4, "name": "Sequences", "children": [{"Item": seq_id}]}},
                    ],
                },
                "items": items,
                "next_id": next_id + 100,
            },
            "view": {
                "open_sequences": [seq_id],
                "active_sequence": seq_id,
                "sequences": {},
                "playheads": {str(seq_id): 0},
            },
        }

        project_file = out_dir / "clip.fcproj"
        with open(project_file, "w", encoding="utf-8") as f:
            json.dump(project_dict, f, indent=2, ensure_ascii=False)

        return ExportResult(
            project_path=project_file,
            exporter=self.name,
            exporter_version=self.version,
            plan_hash=plan_hash,
            duration_s=round(timeline_acc_s, 3),
            warnings=warnings,
        )
