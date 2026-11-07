"""HTTP API consumed by the Next.js app (through its /api/worker proxy).

Long work is always a job: create → poll ``GET /jobs/{id}`` → read results.
"""

from __future__ import annotations

import re
import shutil
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from . import ffmpeg, pipeline
from .config import get_settings
from .domain import LayoutPreset, Rect, RenderOptions, SessionSpec, SourceMode, SyncResult, new_id, to_dict
from .ingest.adapter import SourceError, validate_spec
from .jobs import get_job_manager
from .storage import SessionStore, read_json

app = FastAPI(title="ClippersIppers worker", version="0.1.0")

ID_RE = re.compile(r"^[a-z]+_[0-9a-f]{12}$")
SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class RectIn(BaseModel):
    x: float = Field(ge=0, le=1)
    y: float = Field(ge=0, le=1)
    w: float = Field(gt=0, le=1)
    h: float = Field(gt=0, le=1)

    def to_rect(self) -> Rect:
        return Rect(self.x, self.y, self.w, self.h)


class LayoutIn(BaseModel):
    camera: RectIn
    gameplay: RectIn

    def to_layout(self) -> LayoutPreset:
        return LayoutPreset(camera=self.camera.to_rect(), gameplay=self.gameplay.to_rect())


class CreateSessionIn(BaseModel):
    mode: Literal["split", "composite"]
    title: str = ""
    gameplay_path: Optional[str] = None
    camera_path: Optional[str] = None
    kick_url: Optional[str] = None
    layout: Optional[LayoutIn] = None
    game_subtitles_region: Optional[RectIn] = None
    language: Optional[str] = "es"
    voiceprint: Optional[str] = None


class UpdateSessionIn(BaseModel):
    title: Optional[str] = None
    layout: Optional[LayoutIn] = None
    game_subtitles_region: Optional[RectIn] = None
    clear_game_subtitles_region: bool = False
    language: Optional[str] = None
    voiceprint: Optional[str] = None


class SyncIn(BaseModel):
    shift_sec: float
    scale: float = Field(default=1.0, gt=0.99, lt=1.01)


class AnalyzeIn(BaseModel):
    force: bool = False


class RenderIn(BaseModel):
    candidate_id: str
    start: Optional[float] = None
    end: Optional[float] = None
    overlay_title: Optional[str] = None
    captions: Literal["streamer", "all", "none"] = "streamer"
    title_duration_sec: float = Field(default=25.0, ge=0, le=120)
    camera_ratio: float = Field(default=0.4, ge=0.25, le=0.6)
    gameplay_focus_x: float = Field(default=0.5, ge=0, le=1)
    punch_in: bool = True
    voice_boost: bool = True


def _store(session_id: str) -> SessionStore:
    if not ID_RE.match(session_id):
        raise HTTPException(400, "Id de sesión inválido")
    store = SessionStore(session_id)
    if not store.has("session.json"):
        raise HTTPException(404, "Sesión no encontrada")
    return store


def _summary(store: SessionStore) -> Dict[str, Any]:
    spec = store.spec()
    jobs = get_job_manager().list(store.id)
    return {
        "session": to_dict(spec),
        "manifest": to_dict(store.manifest()),
        "sync": to_dict(store.sync()) if store.has("sync.json") else None,
        "source": read_json(store.path("source.json")) if store.has("source.json") else {},
        "has_candidates": store.has("candidates.json"),
        "candidates": len(store.candidates()),
        "clips": len(store.clips()),
        "jobs": [to_dict(j) for j in jobs[:10]],
    }


def _submit_ingest(store: SessionStore):
    return get_job_manager().submit("ingest", store.id, lambda report: pipeline.ingest(store.id, report))


@app.get("/health")
def health() -> Dict[str, Any]:
    from .selection.providers import DEFAULT_MODELS

    s = get_settings()
    return {
        "ok": True,
        "data_dir": str(s.data_dir),
        "llm_provider": s.llm_provider,
        "llm_model": s.llm_model or DEFAULT_MODELS.get(s.llm_provider, ""),
        "llm_vision": s.llm_vision,
        "face_model": bool(s.face_landmarker_model and s.face_landmarker_model.exists()),
        "ffmpeg": shutil.which(s.ffmpeg) is not None,
    }


# Uploads ------------------------------------------------------------------


@app.post("/uploads")
async def upload(request: Request, filename: str = Query(...)) -> Dict[str, Any]:
    """Streams the request body to disk; returns the path to use in a session."""
    s = get_settings()
    target_dir = s.data_dir / "uploads"
    target_dir.mkdir(parents=True, exist_ok=True)
    safe = SAFE_NAME_RE.sub("_", Path(filename).name)[-120:] or "video.mp4"
    target = target_dir / f"{new_id('up')}_{safe}"
    size = 0
    with target.open("wb") as fh:
        async for chunk in request.stream():
            fh.write(chunk)
            size += len(chunk)
    if size == 0:
        target.unlink(missing_ok=True)
        raise HTTPException(400, "Archivo vacío")
    return {"path": str(target), "size": size}


# Sessions -----------------------------------------------------------------


@app.get("/sessions")
def list_sessions() -> List[Dict[str, Any]]:
    out = []
    for sid in SessionStore.list_ids():
        try:
            out.append(_summary(SessionStore(sid)))
        except (FileNotFoundError, ValueError, KeyError):
            continue
    return sorted(out, key=lambda x: x["session"]["created_at"], reverse=True)


@app.post("/sessions")
def create_session(body: CreateSessionIn) -> Dict[str, Any]:
    spec = SessionSpec(
        id=new_id("ses"),
        mode=SourceMode(body.mode),
        title=body.title.strip(),
        gameplay_path=body.gameplay_path.strip() if body.gameplay_path else None,
        camera_path=body.camera_path.strip() if body.camera_path else None,
        kick_url=body.kick_url.strip() if body.kick_url else None,
        layout=body.layout.to_layout() if body.layout else None,
        game_subtitles_region=body.game_subtitles_region.to_rect() if body.game_subtitles_region else None,
        language=body.language or None,
        voiceprint=body.voiceprint or None,
    )
    try:
        validate_spec(spec, require_layout=False)
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    store = SessionStore(spec.id).ensure()
    store.save("session.json", spec)
    job = _submit_ingest(store)
    return {"session": to_dict(spec), "job": to_dict(job)}


@app.get("/sessions/{session_id}")
def get_session(session_id: str) -> Dict[str, Any]:
    return _summary(_store(session_id))


@app.patch("/sessions/{session_id}")
def update_session(session_id: str, body: UpdateSessionIn) -> Dict[str, Any]:
    store = _store(session_id)
    spec = store.spec()
    if body.title is not None:
        spec.title = body.title.strip()
    if body.language is not None:
        spec.language = body.language or None
    if body.voiceprint is not None:
        spec.voiceprint = body.voiceprint or None
    if body.layout is not None:
        spec.layout = body.layout.to_layout()
        # Proxies are cropped with the layout: everything visual must be redone.
        for name in ("media.json", "face.json", "motion.json", "ocr.json", "sync.json"):
            store.path(name).unlink(missing_ok=True)
    if body.clear_game_subtitles_region:
        spec.game_subtitles_region = None
        store.path("ocr.json").unlink(missing_ok=True)
    elif body.game_subtitles_region is not None:
        spec.game_subtitles_region = body.game_subtitles_region.to_rect()
        store.path("ocr.json").unlink(missing_ok=True)
    store.save("session.json", spec)
    return _summary(store)


@app.get("/sessions/{session_id}/frame")
def frame(
    session_id: str,
    source: Literal["gameplay", "camera"] = "gameplay",
    t: float = Query(default=30.0, ge=0),
    width: int = Query(default=960, ge=160, le=1920),
) -> Response:
    """Full, uncropped frame for the layout / OCR-region picker."""
    store = _store(session_id)
    paths = pipeline.source_paths(store)
    path = paths.get(source)
    if not path:
        raise HTTPException(409, "La fuente aún no está lista (espera a que termine la ingesta).")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "frame.jpg"
        try:
            ffmpeg.extract_frame(path, t, out, width=width)
        except ffmpeg.FfmpegError as exc:
            raise HTTPException(500, str(exc)) from exc
        return Response(out.read_bytes(), media_type="image/jpeg")


@app.put("/sessions/{session_id}/sync")
def set_sync(session_id: str, body: SyncIn) -> Dict[str, Any]:
    store = _store(session_id)
    result = SyncResult(shift_sec=body.shift_sec, scale=body.scale, method="manual", confidence=1.0)
    store.save("sync.json", result)
    return to_dict(result)


@app.post("/sessions/{session_id}/ingest")
def run_ingest(session_id: str) -> Dict[str, Any]:
    return to_dict(_submit_ingest(_store(session_id)))


@app.post("/sessions/{session_id}/analyze")
def run_analysis(session_id: str, body: AnalyzeIn) -> Dict[str, Any]:
    store = _store(session_id)
    try:
        validate_spec(store.spec(), require_layout=True)
    except SourceError as exc:
        raise HTTPException(400, str(exc)) from exc
    manager = get_job_manager()
    active = manager.active_for(session_id, "analyze")
    if active:
        return to_dict(active)
    return to_dict(manager.submit("analyze", session_id, lambda report: pipeline.analyze(session_id, report, body.force)))


@app.get("/sessions/{session_id}/transcript")
def transcript(session_id: str) -> List[Dict[str, Any]]:
    return to_dict(_store(session_id).transcript())


@app.get("/sessions/{session_id}/signals")
def signals(session_id: str) -> Optional[Dict[str, Any]]:
    return to_dict(_store(session_id).signals())


@app.get("/sessions/{session_id}/candidates")
def candidates(session_id: str) -> List[Dict[str, Any]]:
    return to_dict(_store(session_id).candidates())


@app.post("/sessions/{session_id}/clips")
def render_clip(session_id: str, body: RenderIn) -> Dict[str, Any]:
    store = _store(session_id)
    if not any(c.id == body.candidate_id for c in store.candidates()):
        raise HTTPException(404, "Candidato no encontrado")
    opts = RenderOptions(
        captions=body.captions,
        title_duration_sec=body.title_duration_sec,
        camera_ratio=body.camera_ratio,
        gameplay_focus_x=body.gameplay_focus_x,
        punch_in=body.punch_in,
        voice_boost=body.voice_boost,
    )
    job = get_job_manager().submit(
        "render",
        session_id,
        lambda report: pipeline.render(
            session_id, body.candidate_id, report, opts, body.start, body.end, body.overlay_title
        ),
    )
    return to_dict(job)


@app.get("/sessions/{session_id}/clips")
def list_clips(session_id: str) -> List[Dict[str, Any]]:
    return to_dict(_store(session_id).clips())


@app.get("/sessions/{session_id}/clips/{clip_id}/file")
def clip_file(session_id: str, clip_id: str, download: bool = False) -> FileResponse:
    store = _store(session_id)
    if not ID_RE.match(clip_id):
        raise HTTPException(400, "Id de clip inválido")
    clip = next((c for c in store.clips() if c.id == clip_id), None)
    if clip is None or not Path(clip.path).exists():
        raise HTTPException(404, "Clip no encontrado")
    return FileResponse(
        clip.path,
        media_type="video/mp4",
        filename=f"{clip_id}.mp4" if download else None,
    )


# Jobs ---------------------------------------------------------------------


@app.get("/jobs")
def list_jobs(session_id: Optional[str] = None) -> List[Dict[str, Any]]:
    return [to_dict(j) for j in get_job_manager().list(session_id)]


@app.get("/jobs/{job_id}")
def get_job(job_id: str) -> Dict[str, Any]:
    job = get_job_manager().get(job_id)
    if job is None:
        raise HTTPException(404, "Job no encontrado")
    return to_dict(job)


# Voiceprints ----------------------------------------------------------------


@app.get("/voiceprints")
def voiceprints() -> List[str]:
    from .audio.voiceprint import list_voiceprints

    return list_voiceprints()


@app.post("/voiceprints/{name}")
async def enroll_voiceprint(name: str, request: Request) -> Dict[str, Any]:
    """Body: ~30 s audio/video of the streamer talking alone."""
    from starlette.concurrency import run_in_threadpool

    from .audio.voiceprint import enroll

    if not re.match(r"^[A-Za-z0-9_-]{1,40}$", name):
        raise HTTPException(400, "Nombre inválido (letras, números, - y _)")
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp) / "sample.bin"
        with src.open("wb") as fh:
            async for chunk in request.stream():
                fh.write(chunk)
        if src.stat().st_size == 0:
            raise HTTPException(400, "Audio vacío")
        await run_in_threadpool(enroll, name, src)
    return {"name": name}
