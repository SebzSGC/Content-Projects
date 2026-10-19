"""FastAPI REST & SSE server for VidForge (/api/v1)."""

from __future__ import annotations

import asyncio
import json
import shutil
import uuid
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from vidforge.domain.models import (
    CanvasConfig,
    ProjectCreate,
    Rational,
    ScriptModel,
    TimelineModel,
    TranscriptModel,
)
from vidforge.infra.db import db, utc_now_iso
from vidforge.infra.hw import detect_hardware
from vidforge.infra.paths import (
    PROJECTS_DIR,
    TEMP_DIR,
    WEB_DIST_DIR,
    ensure_directories,
)
from vidforge.infra.secrets import secret_store
from vidforge.jobs.manager import CancelToken, job_manager
from vidforge.services.asr import export_ass, export_srt, export_vtt, transcribe_or_align
from vidforge.services.audio import (
    join_audio_files,
    normalize_audio_loudnorm,
    probe_media,
    synthesize_tts,
    trim_silence,
)
from vidforge.services.director import enrich_prompts_with_llm, segment_script_into_beats
from vidforge.services.export import export_capcut_draft, export_otio_json
from vidforge.services.media_gen import (
    create_thumbnail,
    generate_visual_image,
    generate_visual_video_clip,
)
from vidforge.services.planner import (
    build_auto_timeline,
    list_templates,
    validate_motion_semantics,
    validate_timeline_invariants,
)
from vidforge.services.render import (
    render_motion_scene_via_sidecar,
    render_timeline_to_mp4,
)

ensure_directories()

app = FastAPI(title="VidForge API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173", "http://127.0.0.1:8765"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _get_proj_or_404(project_id: str) -> tuple[dict[str, Any], Path]:
    found = db.get_project(project_id)
    if not found:
        raise HTTPException(status_code=404, detail=f"Project {project_id} not found")
    return found


def _save_project_files(proj_data: dict[str, Any], folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for sub in ("assets/images", "assets/videos", "assets/audio", "assets/motion", "renders", "exports", ".cache/thumbs"):
        (folder / sub).mkdir(parents=True, exist_ok=True)
    (folder / "project.json").write_text(json.dumps(proj_data, indent=2, ensure_ascii=False), encoding="utf-8")
    db.upsert_project(proj_data, folder)


@app.get("/api/v1/health")
def get_health() -> dict[str, Any]:
    return {"status": "ok", "service": "vidforge", "version": "1.0.0"}


@app.get("/api/v1/system/hardware")
def get_system_hardware() -> dict[str, Any]:
    return detect_hardware()


@app.post("/api/v1/system/cleanup-temp")
def cleanup_temp() -> dict[str, Any]:
    removed = 0
    if TEMP_DIR.exists():
        for item in TEMP_DIR.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(item, ignore_errors=True)
                else:
                    item.unlink(missing_ok=True)
                removed += 1
            except Exception:
                pass
    return {"cleaned_items": removed}


# --- Projects ---

@app.get("/api/v1/projects")
def list_all_projects() -> list[dict[str, Any]]:
    return db.list_projects()


@app.post("/api/v1/projects")
def create_project(req: ProjectCreate) -> dict[str, Any]:
    pid = str(uuid.uuid4())
    now = utc_now_iso()
    safe_slug = "".join(c if c.isalnum() else "_" for c in req.name)[:40]
    folder = PROJECTS_DIR / f"{safe_slug}_{pid[:8]}.vfproj"
    proj_data = {
        "schema_version": "project/1",
        "id": pid,
        "name": req.name,
        "created_at": now,
        "updated_at": now,
        "language": req.language,
        "canvas": {
            "width": req.width,
            "height": req.height,
            "fps": {"num": req.fps, "den": 1},
            "background": "#000000",
        },
        "style_guide": req.style_guide,
        "providers": {"llm": "local", "tts": "local", "image": "local", "video": "local"},
        "narration_asset_id": None,
        "active_transcript_id": None,
    }
    _save_project_files(proj_data, folder)

    # Initialize default script & timeline
    default_script = ScriptModel(
        text="En el último año el rendimiento creció un 87% gracias a la automatización local. @Elena explica cómo el flujo tradicional versus el nuevo motor reduce los tiempos a la mitad. Finalmente logramos calidad de estudio a 60 cuadros por segundo.",
        characters=[],
        beats=[],
    )
    default_script = segment_script_into_beats(default_script.text, req.style_guide)
    (folder / "script.json").write_text(default_script.model_dump_json(indent=2), encoding="utf-8")

    default_tl = TimelineModel(
        canvas=CanvasConfig(width=req.width, height=req.height, fps=Rational(num=req.fps, den=1)),
        duration_us=6_000_000,
        tracks=[],
    )
    (folder / "timeline.json").write_text(default_tl.model_dump_json(indent=2), encoding="utf-8")
    return proj_data


@app.get("/api/v1/projects/{project_id}")
def get_project_details(project_id: str) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    return {
        **proj,
        "folder_path": str(folder),
        "assets_count": len(db.list_assets(project_id)),
    }


@app.delete("/api/v1/projects/{project_id}")
def delete_project_endpoint(project_id: str) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    db.delete_project(project_id)
    shutil.rmtree(folder, ignore_errors=True)
    return {"deleted": project_id}


# --- Script & Director ---

@app.get("/api/v1/projects/{project_id}/script")
def get_project_script(project_id: str) -> dict[str, Any]:
    _, folder = _get_proj_or_404(project_id)
    sp = folder / "script.json"
    if not sp.exists():
        return ScriptModel().model_dump()
    return json.loads(sp.read_text(encoding="utf-8"))


@app.put("/api/v1/projects/{project_id}/script")
def save_project_script(project_id: str, script: ScriptModel) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    (folder / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")
    proj["updated_at"] = utc_now_iso()
    _save_project_files(proj, folder)
    return script.model_dump()


class SegmentRequest(BaseModel):
    text: str
    style_guide: str = "Cinematográfico, iluminación dramática, 4k"
    use_llm: bool = False


@app.post("/api/v1/projects/{project_id}/script/segment")
async def segment_project_script(project_id: str, req: SegmentRequest) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    existing_raw = get_project_script(project_id)
    existing_script = ScriptModel(**existing_raw)
    segmented = segment_script_into_beats(req.text, req.style_guide, existing_script.characters)
    if req.use_llm:
        segmented = await enrich_prompts_with_llm(segmented, req.style_guide)
    (folder / "script.json").write_text(segmented.model_dump_json(indent=2), encoding="utf-8")
    proj["style_guide"] = req.style_guide
    proj["updated_at"] = utc_now_iso()
    _save_project_files(proj, folder)
    return segmented.model_dump()


# --- Assets ---

@app.get("/api/v1/projects/{project_id}/assets")
def get_project_assets(project_id: str, kind: str | None = Query(default=None)) -> list[dict[str, Any]]:
    _get_proj_or_404(project_id)
    return db.list_assets(project_id, kind=kind)


@app.post("/api/v1/projects/{project_id}/assets/upload")
async def upload_project_asset(
    project_id: str,
    file: UploadFile = File(...),
    kind: str = Query(default="auto"),
) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    fname = file.filename or f"asset_{uuid.uuid4().hex[:6]}"
    ext = Path(fname).suffix.lower()
    if kind == "auto":
        if ext in (".wav", ".mp3", ".m4a", ".ogg", ".flac"):
            kind = "audio"
        elif ext in (".mp4", ".webm", ".mov", ".mkv"):
            kind = "video"
        else:
            kind = "image"

    subdir = "audio" if kind == "audio" else ("videos" if kind == "video" else "images")
    aid = str(uuid.uuid4())
    dst = folder / "assets" / subdir / f"{aid[:8]}_{fname}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    content = await file.read()
    dst.write_bytes(content)

    probe = probe_media(dst)
    thumb_path = None
    if kind in ("image", "video"):
        tp = folder / ".cache" / "thumbs" / f"{aid}.jpg"
        create_thumbnail(dst, tp)
        thumb_path = str(tp)

    asset_doc = {
        "id": aid,
        "project_id": project_id,
        "kind": kind,
        "name": fname,
        "file_path": str(dst.resolve()),
        "thumb_path": thumb_path,
        "duration_us": probe["duration_us"],
        "width": probe["width"],
        "height": probe["height"],
        "meta": {"has_alpha": probe["has_alpha"]},
        "created_at": utc_now_iso(),
    }
    db.insert_asset(asset_doc)
    if kind == "audio" and not proj.get("narration_asset_id"):
        proj["narration_asset_id"] = aid
        _save_project_files(proj, folder)
    return asset_doc


@app.get("/api/v1/assets/{asset_id}/file")
def serve_asset_file(asset_id: str):
    asset = db.get_asset(asset_id)
    if not asset or not Path(asset["file_path"]).exists():
        raise HTTPException(status_code=404, detail="Asset file not found")
    return FileResponse(asset["file_path"])


@app.get("/api/v1/assets/{asset_id}/thumbnail")
def serve_asset_thumbnail(asset_id: str):
    asset = db.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")
    tp = asset.get("thumb_path")
    if tp and Path(tp).exists():
        return FileResponse(tp)
    if Path(asset["file_path"]).exists():
        return FileResponse(asset["file_path"])
    raise HTTPException(status_code=404, detail="Thumbnail not found")


@app.delete("/api/v1/assets/{asset_id}")
def delete_single_asset(asset_id: str) -> dict[str, Any]:
    asset = db.get_asset(asset_id)
    if not asset:
        raise HTTPException(status_code=404, detail="Asset not found")

    fp = Path(asset["file_path"]) if asset.get("file_path") else None
    if fp and fp.exists():
        try:
            fp.unlink(missing_ok=True)
        except Exception:
            pass

    tp = Path(asset["thumb_path"]) if asset.get("thumb_path") else None
    if tp and tp.exists():
        try:
            tp.unlink(missing_ok=True)
        except Exception:
            pass

    proj_tuple = db.get_project(asset["project_id"])
    if proj_tuple:
        proj, folder = proj_tuple
        if proj.get("narration_asset_id") == asset_id:
            proj["narration_asset_id"] = None
            _save_project_files(proj, folder)

    db.delete_asset(asset_id)
    return {"deleted": asset_id}


class BatchDeleteAssetsRequest(BaseModel):
    asset_ids: list[str]


@app.post("/api/v1/assets/batch-delete")
def delete_assets_batch(req: BatchDeleteAssetsRequest) -> dict[str, Any]:
    deleted = []
    for aid in req.asset_ids:
        try:
            delete_single_asset(aid)
            deleted.append(aid)
        except Exception:
            pass
    return {"deleted_count": len(deleted), "deleted_ids": deleted}


# --- Generations (TTS, Image, Video, Batch) ---

class GenerationRequest(BaseModel):
    kind: str  # "tts" | "image" | "video" | "batch_beats"
    prompt: str = ""
    voice: str = "es-local"
    speed: float = 1.0
    beat_index: int = 0
    tags: list[str] = []
    duration_s: float = 4.0


@app.post("/api/v1/projects/{project_id}/generations")
async def submit_generation_job(project_id: str, req: GenerationRequest) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    width = int(proj["canvas"]["width"])
    height = int(proj["canvas"]["height"])

    async def _runner(job_id: str, token: CancelToken, report):
        if req.kind == "tts":
            report(0.15, "Sintetizando locución TTS local")
            aid = str(uuid.uuid4())
            out_wav = folder / "assets" / "audio" / f"tts_{aid[:8]}.wav"
            await asyncio.to_thread(synthesize_tts, req.prompt, out_wav, req.voice, req.speed)
            probe = await asyncio.to_thread(probe_media, out_wav)
            asset_doc = {
                "id": aid,
                "project_id": project_id,
                "kind": "audio",
                "name": f"Locución TTS ({aid[:6]}).wav",
                "file_path": str(out_wav.resolve()),
                "thumb_path": None,
                "duration_us": probe["duration_us"],
                "width": 0,
                "height": 0,
                "meta": {"voice": req.voice},
                "created_at": utc_now_iso(),
            }
            db.insert_asset(asset_doc)
            proj["narration_asset_id"] = aid
            _save_project_files(proj, folder)
            return {"asset": asset_doc}

        elif req.kind == "image":
            report(0.2, f"Generando imagen para escena #{req.beat_index + 1}")
            aid = str(uuid.uuid4())
            out_img = folder / "assets" / "images" / f"scene_{req.beat_index + 1:02d}_{aid[:6]}.png"
            await asyncio.to_thread(
                generate_visual_image, req.prompt, out_img, width, height, req.tags, req.beat_index
            )
            tp = folder / ".cache" / "thumbs" / f"{aid}.jpg"
            await asyncio.to_thread(create_thumbnail, out_img, tp)
            asset_doc = {
                "id": aid,
                "project_id": project_id,
                "kind": "image",
                "name": out_img.name,
                "file_path": str(out_img.resolve()),
                "thumb_path": str(tp.resolve()),
                "duration_us": 4_000_000,
                "width": width,
                "height": height,
                "meta": {"prompt": req.prompt, "beat_index": req.beat_index, "tags": req.tags},
                "created_at": utc_now_iso(),
            }
            db.insert_asset(asset_doc)
            return {"asset": asset_doc}

        elif req.kind == "video":
            report(0.2, f"Generando clip de vídeo #{req.beat_index + 1}")
            aid = str(uuid.uuid4())
            out_vid = folder / "assets" / "videos" / f"vclip_{req.beat_index + 1:02d}_{aid[:6]}.mp4"
            await asyncio.to_thread(
                generate_visual_video_clip, req.prompt, out_vid, req.duration_s, width, height, req.beat_index
            )
            probe = await asyncio.to_thread(probe_media, out_vid)
            tp = folder / ".cache" / "thumbs" / f"{aid}.jpg"
            await asyncio.to_thread(create_thumbnail, out_vid, tp)
            asset_doc = {
                "id": aid,
                "project_id": project_id,
                "kind": "video",
                "name": out_vid.name,
                "file_path": str(out_vid.resolve()),
                "thumb_path": str(tp.resolve()),
                "duration_us": probe["duration_us"],
                "width": width,
                "height": height,
                "meta": {"prompt": req.prompt, "beat_index": req.beat_index},
                "created_at": utc_now_iso(),
            }
            db.insert_asset(asset_doc)
            return {"asset": asset_doc}

        elif req.kind == "batch_beats":
            script_raw = get_project_script(project_id)
            script_obj = ScriptModel(**script_raw)
            beats = script_obj.beats
            created_assets = []
            for idx, b in enumerate(beats):
                if token.is_cancelled():
                    break
                report((idx + 0.1) / max(1, len(beats)), f"Generando activo {idx + 1}/{len(beats)}")
                aid = str(uuid.uuid4())
                out_img = folder / "assets" / "images" / f"beat_{idx + 1:02d}_{aid[:6]}.png"
                await asyncio.to_thread(
                    generate_visual_image, b.visual_prompt or b.text, out_img, width, height, b.tags, idx
                )
                tp = folder / ".cache" / "thumbs" / f"{aid}.jpg"
                await asyncio.to_thread(create_thumbnail, out_img, tp)
                asset_doc = {
                    "id": aid,
                    "project_id": project_id,
                    "kind": "image",
                    "name": out_img.name,
                    "file_path": str(out_img.resolve()),
                    "thumb_path": str(tp.resolve()),
                    "duration_us": 4_000_000,
                    "width": width,
                    "height": height,
                    "meta": {"beat_id": b.id, "beat_index": idx, "prompt": b.visual_prompt},
                    "created_at": utc_now_iso(),
                }
                db.insert_asset(asset_doc)
                created_assets.append(asset_doc)
            return {"assets": created_assets}

        raise ValueError(f"Unsupported generation kind: {req.kind}")

    return job_manager.submit(
        job_type="image_gen" if req.kind != "tts" else "tts",
        runner=_runner,
        project_id=project_id,
        params=req.model_dump(),
        pool="cpu",
    )


# --- AudioLab ---

class AudioLabRequest(BaseModel):
    operation: str  # "join" | "trim_silence" | "normalize"
    asset_ids: list[str]
    target_lufs: float = -14.0


@app.post("/api/v1/projects/{project_id}/audio/process")
async def process_audio_lab(project_id: str, req: AudioLabRequest) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)

    async def _runner(job_id: str, token: CancelToken, report):
        paths: list[Path] = []
        for aid in req.asset_ids:
            a = db.get_asset(aid)
            if a and Path(a["file_path"]).exists():
                paths.append(Path(a["file_path"]))
        if not paths:
            raise ValueError("No valid audio assets provided")

        new_id = str(uuid.uuid4())
        out_wav = folder / "assets" / "audio" / f"audiolab_{req.operation}_{new_id[:6]}.wav"
        report(0.3, f"Ejecutando AudioLab ({req.operation})")
        if req.operation == "join":
            await asyncio.to_thread(join_audio_files, paths, out_wav)
        elif req.operation == "trim_silence":
            await asyncio.to_thread(trim_silence, paths[0], out_wav)
        elif req.operation == "normalize":
            await asyncio.to_thread(normalize_audio_loudnorm, paths[0], out_wav, req.target_lufs)
        else:
            raise ValueError(f"Unknown operation: {req.operation}")

        probe = await asyncio.to_thread(probe_media, out_wav)
        asset_doc = {
            "id": new_id,
            "project_id": project_id,
            "kind": "audio",
            "name": out_wav.name,
            "file_path": str(out_wav.resolve()),
            "thumb_path": None,
            "duration_us": probe["duration_us"],
            "width": 0,
            "height": 0,
            "meta": {"operation": req.operation},
            "created_at": utc_now_iso(),
        }
        db.insert_asset(asset_doc)
        proj["narration_asset_id"] = new_id
        _save_project_files(proj, folder)
        return {"asset": asset_doc}

    return job_manager.submit("audio_process", _runner, project_id=project_id, params=req.model_dump())


# --- Transcripts & Alignment ---

class TranscribeRequest(BaseModel):
    audio_asset_id: str | None = None
    use_script_text: bool = True
    use_whisper: bool = False


@app.post("/api/v1/projects/{project_id}/transcripts")
async def create_project_transcript(project_id: str, req: TranscribeRequest) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    aid = req.audio_asset_id or proj.get("narration_asset_id")
    if not aid:
        raise HTTPException(status_code=400, detail="Project has no narration audio asset")
    asset = db.get_asset(aid)
    if not asset or not Path(asset["file_path"]).exists():
        raise HTTPException(status_code=404, detail="Audio asset file not found")

    script_raw = get_project_script(project_id)
    script_text = script_raw.get("text", "") if req.use_script_text else None

    async def _runner(job_id: str, token: CancelToken, report):
        report(0.25, "Alineando palabras con audio")
        tr = await asyncio.to_thread(
            transcribe_or_align,
            Path(asset["file_path"]),
            aid,
            script_text,
            proj.get("language", "es"),
            req.use_whisper,
        )
        tr_dict = tr.model_dump()
        db.save_transcript(tr_dict, project_id)
        tr_dir = folder / "transcripts"
        tr_dir.mkdir(parents=True, exist_ok=True)
        (tr_dir / f"{tr.id}.json").write_text(tr.model_dump_json(indent=2), encoding="utf-8")
        proj["active_transcript_id"] = tr.id
        _save_project_files(proj, folder)
        return tr_dict

    return job_manager.submit("asr", _runner, project_id=project_id, params=req.model_dump(), pool="gpu")


@app.get("/api/v1/transcripts/{transcript_id}")
def get_transcript_by_id(transcript_id: str) -> dict[str, Any]:
    tr = db.get_transcript(transcript_id)
    if not tr:
        raise HTTPException(status_code=404, detail="Transcript not found")
    return tr


@app.get("/api/v1/transcripts/{transcript_id}/export")
def export_transcript_format(transcript_id: str, format: str = Query(default="srt")):
    tr_raw = db.get_transcript(transcript_id)
    if not tr_raw:
        raise HTTPException(status_code=404, detail="Transcript not found")
    tr = TranscriptModel(**tr_raw)
    if format == "srt":
        return PlainTextResponse(export_srt(tr), media_type="text/plain; charset=utf-8")
    if format == "vtt":
        return PlainTextResponse(export_vtt(tr), media_type="text/vtt; charset=utf-8")
    if format == "ass":
        return PlainTextResponse(export_ass(tr), media_type="text/plain; charset=utf-8")
    return tr_raw


# --- Timeline & Auto-Planner ---

@app.get("/api/v1/projects/{project_id}/timeline")
def get_project_timeline(project_id: str) -> dict[str, Any]:
    _, folder = _get_proj_or_404(project_id)
    tp = folder / "timeline.json"
    if not tp.exists():
        return TimelineModel().model_dump()
    return json.loads(tp.read_text(encoding="utf-8"))


@app.put("/api/v1/projects/{project_id}/timeline")
def update_project_timeline(project_id: str, timeline: TimelineModel) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    timeline.revision += 1
    (folder / "timeline.json").write_text(timeline.model_dump_json(indent=2), encoding="utf-8")
    proj["updated_at"] = utc_now_iso()
    _save_project_files(proj, folder)
    return timeline.model_dump()


class AutoPlanRequest(BaseModel):
    transcript_id: str | None = None
    default_transition: str = "fade"
    transition_duration_us: int = 400_000
    include_motion_scenes: bool = True


@app.post("/api/v1/projects/{project_id}/timeline/autoplan")
def autoplan_project_timeline(project_id: str, req: AutoPlanRequest) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    tid = req.transcript_id or proj.get("active_transcript_id")
    if not tid:
        raise HTTPException(status_code=400, detail="Project has no active transcript. Run transcription/alignment first.")
    tr_raw = db.get_transcript(tid)
    if not tr_raw:
        raise HTTPException(status_code=404, detail="Transcript not found")
    tr = TranscriptModel(**tr_raw)

    visual_assets = [a for a in db.list_assets(project_id) if a["kind"] in ("image", "video")]
    script_raw = get_project_script(project_id)
    script = ScriptModel(**script_raw)

    tl = build_auto_timeline(
        transcript=tr,
        visual_assets=visual_assets,
        script=script,
        width=int(proj["canvas"]["width"]),
        height=int(proj["canvas"]["height"]),
        fps=int(proj["canvas"]["fps"]["num"]),
        default_transition=req.default_transition,
        transition_duration_us=req.transition_duration_us,
        include_motion_scenes=req.include_motion_scenes,
    )
    (folder / "timeline.json").write_text(tl.model_dump_json(indent=2), encoding="utf-8")
    return tl.model_dump()


@app.post("/api/v1/projects/{project_id}/timeline/validate")
def validate_project_timeline(project_id: str) -> dict[str, Any]:
    raw = get_project_timeline(project_id)
    tl = TimelineModel(**raw)
    issues = validate_timeline_invariants(tl)
    return {"valid": len(issues) == 0, "issues": issues}


# --- Templates & Sidecar Motion Scenes ---

@app.get("/api/v1/templates")
def get_templates_catalog() -> list[dict[str, Any]]:
    return list_templates()


class RenderMotionSceneRequest(BaseModel):
    template_id: str
    props: dict[str, Any]
    duration_us: int = 4_000_000
    spoken_text: str = ""
    alpha: bool = True


@app.post("/api/v1/projects/{project_id}/motion-scenes/render")
async def render_project_motion_scene(project_id: str, req: RenderMotionSceneRequest) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    catalog = {t["id"]: t for t in list_templates()}
    if req.template_id not in catalog:
        raise HTTPException(status_code=404, detail=f"Template {req.template_id} not found")

    if req.spoken_text:
        sem_errors = validate_motion_semantics(catalog[req.template_id], req.props, req.spoken_text)
        if sem_errors:
            raise HTTPException(status_code=422, detail="; ".join(sem_errors))

    async def _runner(job_id: str, token: CancelToken, report):
        report(0.15, f"Renderizando plantilla {req.template_id} en Chrome Headless")
        aid = str(uuid.uuid4())
        ext = "webm" if req.alpha else "mp4"
        out_path = folder / "assets" / "motion" / f"motion_{req.template_id}_{aid[:6]}.{ext}"
        await asyncio.to_thread(
            render_motion_scene_via_sidecar,
            req.template_id,
            req.props,
            req.duration_us,
            out_path,
            int(proj["canvas"]["width"]),
            int(proj["canvas"]["height"]),
            30,
            req.alpha,
            lambda p: report(0.15 + 0.80 * p, f"Capturando fotogramas ({int(p*100)}%)"),
        )
        probe = await asyncio.to_thread(probe_media, out_path)
        tp = folder / ".cache" / "thumbs" / f"{aid}.jpg"
        await asyncio.to_thread(create_thumbnail, out_path, tp)
        asset_doc = {
            "id": aid,
            "project_id": project_id,
            "kind": "motion",
            "name": out_path.name,
            "file_path": str(out_path.resolve()),
            "thumb_path": str(tp.resolve()),
            "duration_us": probe["duration_us"] or req.duration_us,
            "width": probe["width"],
            "height": probe["height"],
            "meta": {"template_id": req.template_id, "props": req.props, "has_alpha": probe["has_alpha"]},
            "created_at": utc_now_iso(),
        }
        db.insert_asset(asset_doc)
        return {"asset": asset_doc}

    return job_manager.submit("motion_render", _runner, project_id=project_id, params=req.model_dump(), pool="gpu")


# --- Full Render & Exports ---

class RenderProjectRequest(BaseModel):
    burn_subtitles: bool = True
    render_motion_overlays: bool = True


@app.post("/api/v1/projects/{project_id}/renders")
async def start_project_render(project_id: str, req: RenderProjectRequest) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    tl_raw = get_project_timeline(project_id)
    tl = TimelineModel(**tl_raw)
    tid = proj.get("active_transcript_id")
    tr = TranscriptModel(**db.get_transcript(tid)) if (tid and db.get_transcript(tid)) else None

    async def _runner(job_id: str, token: CancelToken, report):
        rid = str(uuid.uuid4())
        out_mp4 = folder / "renders" / f"render_{rid[:8]}.mp4"
        await asyncio.to_thread(
            render_timeline_to_mp4,
            tl,
            out_mp4,
            tr,
            req.burn_subtitles,
            req.render_motion_overlays,
            report,
        )
        probe = await asyncio.to_thread(probe_media, out_mp4)
        tp = folder / ".cache" / "thumbs" / f"{rid}.jpg"
        await asyncio.to_thread(create_thumbnail, out_mp4, tp)
        asset_doc = {
            "id": rid,
            "project_id": project_id,
            "kind": "render",
            "name": out_mp4.name,
            "file_path": str(out_mp4.resolve()),
            "thumb_path": str(tp.resolve()),
            "duration_us": probe["duration_us"],
            "width": probe["width"],
            "height": probe["height"],
            "meta": {"burn_subtitles": req.burn_subtitles},
            "created_at": utc_now_iso(),
        }
        db.insert_asset(asset_doc)
        return {"render_asset": asset_doc}

    return job_manager.submit("render", _runner, project_id=project_id, params=req.model_dump(), pool="gpu")


class ExportProjectRequest(BaseModel):
    target: str = "capcut"  # "capcut" | "otio" | "srt" | "ass"
    draft_name: str | None = None
    draft_root: str | None = None
    copy_media: bool = True


@app.post("/api/v1/projects/{project_id}/exports")
def export_project_endpoint(project_id: str, req: ExportProjectRequest) -> dict[str, Any]:
    proj, folder = _get_proj_or_404(project_id)
    tl = TimelineModel(**get_project_timeline(project_id))
    exports_dir = folder / "exports"
    exports_dir.mkdir(parents=True, exist_ok=True)

    if req.target == "capcut":
        root_dir = Path(req.draft_root) if req.draft_root else exports_dir
        name = req.draft_name or f"{proj['name']}_CapCut"
        res = export_capcut_draft(tl, root_dir, name, copy_media=req.copy_media, check_process_lock=False)
        return {"target": "capcut", **res}

    elif req.target == "otio":
        out_file = exports_dir / f"{proj['name']}.otio"
        export_otio_json(tl, out_file)
        return {"target": "otio", "path": str(out_file.resolve())}

    elif req.target in ("srt", "ass"):
        tid = proj.get("active_transcript_id")
        if not tid or not db.get_transcript(tid):
            raise HTTPException(status_code=400, detail="No active transcript to export")
        tr = TranscriptModel(**db.get_transcript(tid))
        out_file = exports_dir / f"{proj['name']}.{req.target}"
        txt = export_srt(tr) if req.target == "srt" else export_ass(tr)
        out_file.write_text(txt, encoding="utf-8")
        return {"target": req.target, "path": str(out_file.resolve())}

    raise HTTPException(status_code=400, detail=f"Unknown export target: {req.target}")


# --- One-Click Autopilot Pipeline ---

@app.post("/api/v1/projects/{project_id}/autopilot")
async def run_autopilot_pipeline(project_id: str) -> dict[str, Any]:
    """Executes the entire creation pipeline: Beat segmentation -> TTS -> Alignment -> Scene images -> Auto-Timeline."""
    proj, folder = _get_proj_or_404(project_id)
    width = int(proj["canvas"]["width"])
    height = int(proj["canvas"]["height"])
    fps = int(proj["canvas"]["fps"]["num"])

    async def _runner(job_id: str, token: CancelToken, report):
        report(0.10, "1/4 Segmentando guion y extrayendo @tags")
        script_raw = get_project_script(project_id)
        script = segment_script_into_beats(script_raw.get("text", ""), proj.get("style_guide", ""))
        (folder / "script.json").write_text(script.model_dump_json(indent=2), encoding="utf-8")

        report(0.30, "2/4 Generando locución TTS local")
        aid_audio = str(uuid.uuid4())
        out_wav = folder / "assets" / "audio" / f"narration_{aid_audio[:6]}.wav"
        await asyncio.to_thread(synthesize_tts, script.text, out_wav, "es-local", 1.0)
        probe_a = await asyncio.to_thread(probe_media, out_wav)
        audio_doc = {
            "id": aid_audio,
            "project_id": project_id,
            "kind": "audio",
            "name": "Locución Maestra.wav",
            "file_path": str(out_wav.resolve()),
            "thumb_path": None,
            "duration_us": probe_a["duration_us"],
            "width": 0,
            "height": 0,
            "meta": {"autopilot": True},
            "created_at": utc_now_iso(),
        }
        db.insert_asset(audio_doc)
        proj["narration_asset_id"] = aid_audio

        report(0.55, "3/4 Alineando palabras y generando escenas visuales")
        tr = await asyncio.to_thread(transcribe_or_align, out_wav, aid_audio, script.text, "es", False)
        db.save_transcript(tr.model_dump(), project_id)
        proj["active_transcript_id"] = tr.id

        visual_assets = []
        for idx, b in enumerate(script.beats):
            aid_img = str(uuid.uuid4())
            out_img = folder / "assets" / "images" / f"scene_{idx + 1:02d}_{aid_img[:6]}.png"
            await asyncio.to_thread(
                generate_visual_image, b.visual_prompt or b.text, out_img, width, height, b.tags, idx
            )
            tp = folder / ".cache" / "thumbs" / f"{aid_img}.jpg"
            await asyncio.to_thread(create_thumbnail, out_img, tp)
            img_doc = {
                "id": aid_img,
                "project_id": project_id,
                "kind": "image",
                "name": out_img.name,
                "file_path": str(out_img.resolve()),
                "thumb_path": str(tp.resolve()),
                "duration_us": 4_000_000,
                "width": width,
                "height": height,
                "meta": {"beat_id": b.id, "beat_index": idx, "prompt": b.visual_prompt},
                "created_at": utc_now_iso(),
            }
            db.insert_asset(img_doc)
            visual_assets.append(img_doc)

        report(0.85, "4/4 Construyendo línea de tiempo sincronizada")
        tl = build_auto_timeline(
            transcript=tr,
            visual_assets=visual_assets,
            script=script,
            width=width,
            height=height,
            fps=fps,
        )
        (folder / "timeline.json").write_text(tl.model_dump_json(indent=2), encoding="utf-8")
        _save_project_files(proj, folder)
        return {
            "audio_asset": audio_doc,
            "transcript_id": tr.id,
            "visual_assets_count": len(visual_assets),
            "timeline_duration_us": tl.duration_us,
        }

    return job_manager.submit("autoplan", _runner, project_id=project_id, pool="cpu")


# --- Jobs, Events, Settings & Secrets ---

@app.get("/api/v1/jobs")
def get_jobs_list(project_id: str | None = Query(default=None)) -> list[dict[str, Any]]:
    return db.list_jobs(project_id=project_id)


@app.get("/api/v1/jobs/{job_id}")
def get_single_job(job_id: str) -> dict[str, Any]:
    j = db.get_job(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return j


@app.post("/api/v1/jobs/{job_id}/cancel")
def cancel_single_job(job_id: str) -> dict[str, Any]:
    j = job_manager.cancel(job_id)
    if not j:
        raise HTTPException(status_code=404, detail="Job not found")
    return j


@app.get("/api/v1/events")
async def sse_events():
    async def _gen():
        async for ev in job_manager.broker.subscribe():
            yield {
                "id": str(ev["seq"]),
                "event": ev["type"],
                "data": json.dumps(ev),
            }

    return EventSourceResponse(_gen())


@app.get("/api/v1/settings")
def get_app_settings() -> dict[str, Any]:
    return db.get_settings()


@app.patch("/api/v1/settings")
def patch_app_settings(patch: dict[str, Any]) -> dict[str, Any]:
    return db.update_settings(patch)


@app.get("/api/v1/providers")
def get_providers_status() -> list[dict[str, Any]]:
    return secret_store.list_status()


class SecretInput(BaseModel):
    secret: str


@app.put("/api/v1/providers/{provider}/secret")
def set_provider_secret(provider: str, body: SecretInput) -> dict[str, Any]:
    secret_store.set_secret(provider, body.secret)
    return {"provider": provider, "configured": True, "last4": body.secret[-4:] if len(body.secret) >= 4 else "****"}


@app.delete("/api/v1/providers/{provider}/secret")
def remove_provider_secret(provider: str) -> dict[str, Any]:
    secret_store.delete_secret(provider)
    return {"provider": provider, "configured": False, "last4": None}


if WEB_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=str(WEB_DIST_DIR), html=True), name="spa")
