"""Execute the complete end-to-end video creation pipeline on the user's real collage image."""

import json
import shutil
import uuid
from pathlib import Path

from vidforge.domain.models import (
    CanvasConfig,
    ClipModel,
    KenBurnsEffect,
    MotionSpec,
    ProjectCreate,
    Rational,
    SubtitleClipSpec,
    TimelineModel,
    TrackModel,
    TransitionSpec,
)
from vidforge.infra.db import db, utc_now_iso
from vidforge.infra.paths import PROJECTS_DIR, ensure_directories
from vidforge.services.asr import export_ass, export_srt, transcribe_or_align
from vidforge.services.audio import normalize_audio_loudnorm, probe_media, synthesize_tts
from vidforge.services.director import segment_script_into_beats
from vidforge.services.export import export_capcut_draft, export_otio_json
from vidforge.services.media_gen import create_thumbnail
from vidforge.services.render import render_timeline_to_mp4


def main():
    ensure_directories()
    script_text = (
        "Hoy probamos el nuevo motor local VidForge. "
        "Gracias a la aceleración por hardware de NVIDIA, el rendimiento aumentó un 90%. "
        "@Alex nos muestra cómo exportar directamente a CapCut en segundos."
    )

    print("1. Creando proyecto en VidForge...")
    pid = str(uuid.uuid4())
    proj_name = "Prueba_VidForge_Collage"
    proj_folder = PROJECTS_DIR / f"{proj_name}_{pid[:8]}.vfproj"
    proj_folder.mkdir(parents=True, exist_ok=True)
    for sub in ("assets/images", "assets/videos", "assets/audio", "assets/motion", "renders", "exports", ".cache/thumbs"):
        (proj_folder / sub).mkdir(parents=True, exist_ok=True)

    proj_data = {
        "schema_version": "project/1",
        "id": pid,
        "name": "Prueba VidForge con Collage Real",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "language": "es",
        "canvas": {
            "width": 1920,
            "height": 1080,
            "fps": {"num": 60, "den": 1},
            "background": "#000000",
        },
        "style_guide": "Cinematográfico, 4k",
        "providers": {"llm": "local", "tts": "local", "image": "local", "video": "local"},
        "narration_asset_id": None,
        "active_transcript_id": None,
    }
    db.upsert_project(proj_data, proj_folder)

    # 2. Segment script into beats
    print("2. Segmentando guion en beats y extrayendo @Alex...")
    script_obj = segment_script_into_beats(script_text, "Cinematográfico")
    (proj_folder / "script.json").write_text(script_obj.model_dump_json(indent=2), encoding="utf-8")

    # 3. Import collage quadrant images as assets
    print("3. Importando cuadrantes recortados del collage...")
    quad_dir = Path(r"D:\rea-projects\projects\quadrants")
    image_files = sorted(quad_dir.glob("*.jpg"))
    # Also add full collage
    full_collage = Path(r"D:\rea-projects\projects\Gemini_Generated_Image_emisslemisslemis.jpg")
    image_files.append(full_collage)

    registered_assets = []
    for idx, fpath in enumerate(image_files):
        aid = str(uuid.uuid4())
        dst = proj_folder / "assets" / "images" / f"{aid[:8]}_{fpath.name}"
        shutil.copy2(fpath, dst)
        tp = proj_folder / ".cache" / "thumbs" / f"{aid}.jpg"
        create_thumbnail(dst, tp)
        probe = probe_media(dst)
        asset_doc = {
            "id": aid,
            "project_id": pid,
            "kind": "image",
            "name": fpath.stem.replace("_", " ").title(),
            "file_path": str(dst.resolve()),
            "thumb_path": str(tp.resolve()),
            "duration_us": 4_000_000,
            "width": probe["width"],
            "height": probe["height"],
            "meta": {"quadrant_index": idx},
            "created_at": utc_now_iso(),
        }
        db.insert_asset(asset_doc)
        registered_assets.append(asset_doc)
    print(f"   -> {len(registered_assets)} activos de imagen registrados.")

    # 4. Synthesize TTS speech
    print("4. Sintetizando locución en español...")
    tts_wav = proj_folder / "assets" / "audio" / "locucion_maestra.wav"
    synthesize_tts(script_text, tts_wav, speed=1.0)
    # Loudnorm normalize
    norm_wav = proj_folder / "assets" / "audio" / "locucion_norm.wav"
    normalize_audio_loudnorm(tts_wav, norm_wav)

    probe_audio = probe_media(norm_wav)
    audio_dur_us = probe_audio["duration_us"]
    audio_aid = str(uuid.uuid4())
    audio_doc = {
        "id": audio_aid,
        "project_id": pid,
        "kind": "audio",
        "name": "Locución Maestra (Normalizada).wav",
        "file_path": str(norm_wav.resolve()),
        "thumb_path": None,
        "duration_us": audio_dur_us,
        "width": 0,
        "height": 0,
        "meta": {"loudnorm": True},
        "created_at": utc_now_iso(),
    }
    db.insert_asset(audio_doc)
    proj_data["narration_asset_id"] = audio_aid
    print(f"   -> Locución lista (Duración: {audio_dur_us / 1_000_000:.2f} s).")

    # 5. Transcribe & force word-level alignment
    print("5. Alineando palabras palabra por palabra (RapidFuzz + VAD)...")
    tr = transcribe_or_align(norm_wav, audio_aid, script_text=script_text, language="es", use_whisper_if_available=False)
    db.save_transcript(tr.model_dump(), pid)
    proj_data["active_transcript_id"] = tr.id
    (proj_folder / "transcripts" / f"{tr.id}.json").parent.mkdir(parents=True, exist_ok=True)
    (proj_folder / "transcripts" / f"{tr.id}.json").write_text(tr.model_dump_json(indent=2), encoding="utf-8")
    print(f"   -> {len(tr.words)} palabras y {len(tr.segments)} segmentos alineados.")

    # 6. Build Multi-track Timeline with Ken Burns and xfade transitions
    print("6. Construyendo línea de tiempo sincronizada...")
    # Map clips to the duration of the audio
    num_clips = len(registered_assets)
    slot_dur = audio_dur_us // num_clips
    video_clips = []
    pan_modes = ["none", "left_right", "top_bottom", "right_left", "bottom_top"]

    for i in range(num_clips):
        c_start = i * slot_dur
        c_dur = slot_dur if i < num_clips - 1 else (audio_dur_us - c_start)
        t_spec = TransitionSpec(kind="cut", name="cut", duration_us=0) if i == 0 else TransitionSpec(
            kind="xfade", name="fade" if i % 2 == 0 else "wipeleft", duration_us=400_000
        )
        video_clips.append(
            ClipModel(
                id=f"vclip_{i+1:02d}",
                asset_id=registered_assets[i]["id"],
                start_us=c_start,
                duration_us=c_dur,
                effects=[
                    KenBurnsEffect(
                        zoom_from=1.02 if i % 2 == 0 else 1.08,
                        zoom_to=1.09 if i % 2 == 0 else 1.03,
                        pan=pan_modes[i % len(pan_modes)],
                    )
                ],
                transition_in=t_spec,
            )
        )

    # Subtitles track
    sub_clips = []
    for s_idx, seg in enumerate(tr.segments):
        sub_clips.append(
            ClipModel(
                id=f"sub_{s_idx+1:02d}",
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

    # Motion graphics track: overlay the 90% stat card during the second sentence!
    # Find sentence 2 in segments or mid-point
    seg_mid = tr.segments[1] if len(tr.segments) > 1 else tr.segments[0]
    motion_clips = [
        ClipModel(
            id="motion_stat_90",
            start_us=seg_mid.start_us,
            duration_us=min(3_500_000, max(1_500_000, seg_mid.end_us - seg_mid.start_us)),
            motion=MotionSpec(
                template_id="stat-highlight",
                props={
                    "value": "90%",
                    "label": "Aceleración NVIDIA",
                    "sublabel": "Turing NVENC a 60 FPS",
                    "accent_color": "#22c55e",
                },
                fullscreen=False,
            ),
        )
    ]

    audio_clips = [
        ClipModel(
            id="narration_track",
            asset_id=audio_aid,
            start_us=0,
            duration_us=audio_dur_us,
            volume_db=0.0,
        )
    ]

    tl = TimelineModel(
        revision=1,
        canvas=CanvasConfig(width=1920, height=1080, fps=Rational(num=60, den=1)),
        duration_us=audio_dur_us,
        tracks=[
            TrackModel(id="track_video", kind="video", name="Tomas del Collage (Ken Burns)", clips=video_clips),
            TrackModel(id="track_motion", kind="motion", name="Gráfico Animado (90% NVENC)", clips=motion_clips),
            TrackModel(id="track_subs", kind="subtitle", name="Subtítulos Karaoke ASS", clips=sub_clips),
            TrackModel(id="track_audio", kind="audio", name="Locución en Español", clips=audio_clips),
        ],
    )
    (proj_folder / "timeline.json").write_text(tl.model_dump_json(indent=2), encoding="utf-8")
    db.upsert_project(proj_data, proj_folder)

    # 7. Render final MP4 with NVENC, WebM alpha overlay and ASS subtitles
    print("7. Renderizando vídeo MP4 final con NVIDIA NVENC a 60 FPS...")
    final_mp4 = proj_folder / "renders" / "video_final_collage_nvenc.mp4"
    def progress_callback(p, stage):
        print(f"   [{int(p*100):02d}%] {stage}")

    render_timeline_to_mp4(
        timeline=tl,
        output_path=final_mp4,
        transcript=tr,
        burn_subtitles=True,
        render_motion_overlays=True,
        on_progress=progress_callback,
    )

    probe_final = probe_media(final_mp4)
    print(f"\n¡VÍDEO MP4 RENDERIZADO CON ÉXITO!")
    print(f"Archivo: {final_mp4}")
    print(f"Resolución: {probe_final['width']}x{probe_final['height']}")
    print(f"Duración: {probe_final['duration_us'] / 1_000_000:.2f} s")
    print(f"Tamaño: {final_mp4.stat().st_size / (1024*1024):.2f} MB")

    # 8. Export CapCut draft and OpenTimelineIO
    print("\n8. Exportando proyecto a CapCut Desktop y OpenTimelineIO...")
    capcut_export = export_capcut_draft(
        timeline=tl,
        draft_root=proj_folder / "exports",
        draft_name="Borrador_CapCut_VidForge",
        copy_media=True,
        check_process_lock=False,
    )
    otio_file = proj_folder / "exports" / "proyecto.otio"
    export_otio_json(tl, otio_file)

    print(f"   -> Borrador CapCut: {capcut_export['draft_dir']}")
    print(f"   -> Archivo OTIO: {otio_file}")
    print("\nPROCESO COMPLETADO AL 100%.")

if __name__ == "__main__":
    main()
