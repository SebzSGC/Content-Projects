"""FastAPI HTTP & SSE routes for ClipsApp unified server."""

from __future__ import annotations

import json
import re
import shutil
import tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from clipscore.domain import SessionState, SignalSeries, SyncResult, new_id
from clipseditplan import EditPlan
from clipsmedia.ffmpeg import extract_frame, resolve_binary
from clipsproviders.notifications import send_delivery_webhook
from clipsstyles import (
    ensure_emoji_png,
    ensure_sfx_wav,
    get_fonts_dir,
    list_emoji_catalog,
    list_game_profiles,
    list_presets,
    load_preset,
    resolve_game_keyterms,
)
from clipstracking import ensure_face_detector_model
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from ..config import ServerSettings, get_server_settings
from ..orchestrator import Orchestrator, cleanup_temp_media, compute_storage_stats

SAFE_NAME_RE = re.compile(r"[^A-Za-z0-9._-]+")


class CreateSessionBody(BaseModel):
    title: str = ""
    gameplay_path: str
    camera_path: str
    recording_name: str = ""
    language: str = "es"
    style_preset: str = "hormozi-gaming"
    auto_start: bool = True


class ManualSyncBody(BaseModel):
    shift_sec: float
    scale: float = Field(default=1.0, gt=0.98, lt=1.02)


class RenderClipBody(BaseModel):
    quality: Literal["draft", "final"] = "final"
    upload_to_drive: bool = True


class CleanupBody(BaseModel):
    ttl_days: Optional[float] = None
    include_inputs: bool = False


class TestWebhookBody(BaseModel):
    webhook_url: Optional[str] = None
    session_id: Optional[str] = None


def _serialize_clip(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "id": row["id"],
        "session_id": row["session_id"],
        "rank_order": row["rank_order"],
        "start": row["start_sec"],
        "end": row["end_sec"],
        "overlay_title": row["overlay_title"],
        "post_title": row["post_title"],
        "hashtags": json.loads(row.get("hashtags_json") or "[]"),
        "reason": row["reason"],
        "llm_score": row["llm_score"],
        "signal_score": row["signal_score"],
        "final_score": row["final_score"],
        "curated": json.loads(row["curated_json"]) if row.get("curated_json") else None,
        "editplan": json.loads(row["editplan_json"]) if row.get("editplan_json") else None,
        "has_draft": bool(row.get("draft_mp4_path") and Path(row["draft_mp4_path"]).is_file()),
        "has_final": bool(row.get("final_mp4_path") and Path(row["final_mp4_path"]).is_file()),
        "drive_salidas": json.loads(row["drive_salidas_json"]) if row.get("drive_salidas_json") else None,
        "state": row["state"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _serialize_session(orch: Orchestrator, row: Dict[str, Any]) -> Dict[str, Any]:
    clips = orch.db.list_clips(row["id"])
    prep = json.loads(row["prepared_json"]) if row.get("prepared_json") else None
    sync = json.loads(row["sync_json"]) if row.get("sync_json") else None
    detected_game, resolved_terms = resolve_game_keyterms(
        title=str(row.get("title") or ""),
        recording_name=str(row.get("recording_name") or ""),
        base_keyterms=orch.settings.default_keyterms,
    )
    return {
        "id": row["id"],
        "title": row["title"],
        "recording_name": row["recording_name"],
        "state": row["state"],
        "gameplay_path": row["gameplay_path"],
        "camera_path": row["camera_path"],
        "drive_folder_id": row["drive_folder_id"],
        "language": row["language"],
        "style_preset": row["style_preset"],
        "detected_game": detected_game,
        "keyterms_count": len(resolved_terms),
        "sync": sync,
        "prepared": prep,
        "error": row["error"],
        "clips_count": len(clips),
        "rendered_count": sum(1 for c in clips if c.get("final_mp4_path") and Path(c["final_mp4_path"]).is_file()),
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def create_app(
    settings: Optional[ServerSettings] = None,
    use_process_pool: bool = True,
    enable_drive_watcher: bool = True,
) -> FastAPI:
    cfg = settings or get_server_settings()
    orch = Orchestrator(cfg, use_process_pool=use_process_pool)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        await orch.startup(enable_watcher=enable_drive_watcher)
        yield
        await orch.shutdown()

    app = FastAPI(
        title="ClipsApp Hybrid Server",
        version="0.2.0",
        description="API local + orquestador SQLite + 3 pools (APIs, CPU, Render)",
        lifespan=lifespan,
    )
    app.state.orchestrator = orch
    app.state.settings = cfg

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/health")
    def health() -> Dict[str, Any]:
        ff_bin = resolve_binary("ffmpeg")
        ff_ok = bool(shutil.which(ff_bin) or Path(ff_bin).is_file())
        mp_ok = False
        try:
            mp_ok = ensure_face_detector_model().is_file()
        except Exception:
            mp_ok = False
        return {
            "ok": True,
            "ffmpeg": ff_ok,
            "mediapipe_face_detector": mp_ok,
            "stt_primary": cfg.stt_primary,
            "stt_backup": cfg.stt_backup,
            "llm_primary": cfg.llm_primary,
            "llm_model": cfg.llm_model,
            "llm_backup": cfg.llm_backup,
            "style_preset": cfg.style_preset,
            "drive_mode": cfg.drive_mode,
            "drive_local_dir": str(cfg.drive_local_dir),
            "cpu_workers": cfg.cpu_workers,
            "render_slots": orch.render_pool.slots,
            "use_nvenc": cfg.use_nvenc,
            "budget": orch.db.budget_summary(cfg.max_budget_usd),
        }

    @app.get("/budget")
    def get_budget() -> Dict[str, Any]:
        return orch.db.budget_summary(cfg.max_budget_usd)

    @app.get("/presets")
    def get_presets() -> List[str]:
        return list_presets()

    @app.get("/presets/{preset_id}")
    def get_preset_detail(preset_id: str) -> Dict[str, Any]:
        try:
            p = load_preset(preset_id)
            return p.model_dump(mode="json")
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc

    @app.get("/fonts/Montserrat-ExtraBold.ttf")
    def serve_montserrat_font() -> FileResponse:
        fpath = get_fonts_dir() / "Montserrat-ExtraBold.ttf"
        if not fpath.is_file():
            raise HTTPException(404, "Fuente no encontrada")
        return FileResponse(fpath, media_type="font/ttf")

    @app.get("/emojis")
    def get_emojis_catalog() -> List[Dict[str, str]]:
        return [
            {**item, "url": f"/emojis/{item['id']}.png"}
            for item in list_emoji_catalog()
        ]

    @app.get("/emojis/{emoji_id}.png")
    def serve_emoji(emoji_id: str) -> FileResponse:
        png = ensure_emoji_png(emoji_id)
        return FileResponse(png, media_type="image/png")

    @app.get("/sfx/{sfx_id}.wav")
    def serve_sfx(sfx_id: str) -> FileResponse:
        wav = ensure_sfx_wav(sfx_id)
        return FileResponse(wav, media_type="audio/wav")

    @app.get("/keyterms")
    def get_keyterms_profiles(
        title: str = Query(default=""),
        recording_name: str = Query(default=""),
    ) -> Dict[str, Any]:
        detected_game, resolved = resolve_game_keyterms(
            title=title,
            recording_name=recording_name,
            base_keyterms=cfg.default_keyterms,
        )
        return {
            "profiles": list_game_profiles(),
            "detected_game": detected_game,
            "resolved_keyterms": resolved,
        }

    @app.get("/maintenance/stats")
    def get_maintenance_stats() -> Dict[str, Any]:
        stats = compute_storage_stats(cfg.data_dir, orch.db, temp_ttl_days=cfg.temp_ttl_days)
        stats["webhook_configured"] = bool(cfg.webhook_url)
        return stats

    @app.post("/maintenance/cleanup")
    def run_maintenance_cleanup(body: CleanupBody) -> Dict[str, Any]:
        ttl = cfg.temp_ttl_days if body.ttl_days is None else body.ttl_days
        res = cleanup_temp_media(
            cfg.data_dir,
            orch.db,
            ttl_days=ttl,
            include_inputs=body.include_inputs,
        )
        orch.events.publish("maintenance_cleanup", **res)
        return res

    @app.post("/webhooks/test")
    async def test_webhook_endpoint(body: TestWebhookBody) -> Dict[str, Any]:
        target_url = (body.webhook_url or cfg.webhook_url or "").strip()
        if not target_url:
            raise HTTPException(400, "No hay URL de webhook configurada ni enviada en la petición.")
        sample_clips: List[Dict[str, Any]] = []
        title = "Prueba de Webhook — ClipsApp"
        sid = body.session_id or "ses_demo"
        if body.session_id:
            srow = orch.db.get_session(body.session_id)
            if srow:
                title = str(srow.get("title") or title)
                sample_clips = orch.db.list_clips(body.session_id)
        if not sample_clips:
            sample_clips = [
                {
                    "id": "clip_demo01",
                    "overlay_title": "CLUTCH IMPOSIBLE 1V4",
                    "post_title": "No creí ganar esta ronda final 🔥",
                    "final_score": 92.5,
                    "has_final": True,
                }
            ]
        return await send_delivery_webhook(
            webhook_url=target_url,
            session_id=sid,
            title=title,
            clips=sample_clips,
            public_web_url=cfg.public_web_url,
        )

    # --- Uploads (manual session files from browser) -----------------------

    @app.post("/uploads")
    async def upload_file(request: Request, filename: str = Query(...)) -> Dict[str, Any]:
        up_dir = cfg.data_dir / "uploads"
        up_dir.mkdir(parents=True, exist_ok=True)
        safe = SAFE_NAME_RE.sub("_", Path(filename).name)[-120:] or "video.mp4"
        dst = up_dir / f"{new_id('up')}_{safe}"
        size = 0
        with dst.open("wb") as fh:
            async for chunk in request.stream():
                fh.write(chunk)
                size += len(chunk)
        if size == 0:
            dst.unlink(missing_ok=True)
            raise HTTPException(400, "Archivo vacío")
        return {"path": str(dst.resolve()), "size": size}

    # --- Google Drive endpoints --------------------------------------------

    @app.get("/drive/status")
    def drive_status() -> Dict[str, Any]:
        entradas_folders: List[str] = []
        salidas_folders: List[str] = []
        if cfg.drive_mode == "local":
            ent = cfg.drive_local_dir / "Entradas"
            sal = cfg.drive_local_dir / "Salidas"
            if ent.is_dir():
                entradas_folders = sorted(p.name for p in ent.iterdir() if p.is_dir())
            if sal.is_dir():
                salidas_folders = sorted(p.name for p in sal.iterdir() if p.is_dir())
        return {
            "mode": cfg.drive_mode,
            "local_dir": str(cfg.drive_local_dir),
            "poll_sec": cfg.drive_poll_sec,
            "entradas": entradas_folders,
            "salidas": salidas_folders,
        }

    @app.post("/drive/poll")
    async def trigger_drive_poll() -> Dict[str, Any]:
        launched = await orch.poll_drive_once()
        return {"launched_sessions": launched}

    # --- Sessions ----------------------------------------------------------

    @app.get("/sessions")
    def list_sessions() -> List[Dict[str, Any]]:
        return [_serialize_session(orch, r) for r in orch.db.list_sessions()]

    @app.post("/sessions")
    async def create_session(body: CreateSessionBody) -> Dict[str, Any]:
        gp = Path(body.gameplay_path).expanduser()
        cm = Path(body.camera_path).expanduser()
        if not gp.is_file():
            raise HTTPException(400, f"No existe el archivo de gameplay: {gp}")
        if not cm.is_file():
            raise HTTPException(400, f"No existe el archivo de cámara: {cm}")

        row = orch.db.create_session(
            title=body.title.strip() or gp.stem,
            gameplay_path=str(gp.resolve()),
            camera_path=str(cm.resolve()),
            recording_name=body.recording_name.strip() or body.title.strip() or gp.stem,
            language=body.language or "es",
            style_preset=body.style_preset or cfg.style_preset,
            initial_state=SessionState.DOWNLOADED,
        )
        if body.auto_start:
            orch.launch_session(row["id"])
        return _serialize_session(orch, orch.db.get_session(row["id"]) or row)

    @app.get("/sessions/{session_id}")
    def get_session(session_id: str) -> Dict[str, Any]:
        row = orch.db.get_session(session_id)
        if not row:
            raise HTTPException(404, "Sesión no encontrada")
        data = _serialize_session(orch, row)
        data["tasks"] = orch.db.list_session_tasks(session_id)
        return data

    @app.post("/sessions/{session_id}/run")
    async def run_session_endpoint(session_id: str) -> Dict[str, Any]:
        row = orch.db.get_session(session_id)
        if not row:
            raise HTTPException(404, "Sesión no encontrada")
        orch.launch_session(session_id)
        return _serialize_session(orch, orch.db.get_session(session_id) or row)

    @app.post("/sessions/{session_id}/cancel")
    async def cancel_session_endpoint(session_id: str) -> Dict[str, Any]:
        row = orch.db.get_session(session_id)
        if not row:
            raise HTTPException(404, "Sesión no encontrada")
        await orch.cancel_session(session_id)
        return _serialize_session(orch, orch.db.get_session(session_id) or row)

    @app.put("/sessions/{session_id}/sync")
    async def set_manual_sync(session_id: str, body: ManualSyncBody) -> Dict[str, Any]:
        row = orch.db.get_session(session_id)
        if not row:
            raise HTTPException(404, "Sesión no encontrada")
        sr = SyncResult(shift_sec=body.shift_sec, scale=body.scale, method="manual", confidence=1.0)
        orch.db.update_session(session_id, sync_json=sr.model_dump_json())
        return sr.model_dump(mode="json")

    @app.get("/sessions/{session_id}/frame")
    def get_session_frame(
        session_id: str,
        source: Literal["gameplay", "camera"] = "gameplay",
        t: float = Query(default=5.0, ge=0.0),
        width: int = Query(default=640, ge=160, le=1920),
    ) -> Response:
        row = orch.db.get_session(session_id)
        if not row:
            raise HTTPException(404, "Sesión no encontrada")
        src_path = row.get("gameplay_path") if source == "gameplay" else row.get("camera_path")
        if not src_path or not Path(src_path).is_file():
            raise HTTPException(404, f"Fuente {source} no disponible")
        with tempfile.TemporaryDirectory() as tmp:
            dst = Path(tmp) / "frame.jpg"
            extract_frame(src_path, t, dst, width=width)
            return Response(dst.read_bytes(), media_type="image/jpeg")

    @app.get("/sessions/{session_id}/stream/{source}")
    def stream_source_video(
        session_id: str,
        source: Literal["gameplay", "camera"],
    ) -> FileResponse:
        row = orch.db.get_session(session_id)
        if not row:
            raise HTTPException(404, "Sesión no encontrada")
        src_path = row.get("gameplay_path") if source == "gameplay" else row.get("camera_path")
        if not src_path or not Path(src_path).is_file():
            raise HTTPException(404, f"Video original {source} no encontrado")
        return FileResponse(src_path, media_type="video/mp4")

    @app.get("/sessions/{session_id}/utterances")
    def get_utterances(session_id: str) -> List[Dict[str, Any]]:
        ufile = orch.session_dir(session_id) / "utterances.json"
        if not ufile.is_file():
            return []
        return json.loads(ufile.read_text(encoding="utf-8"))

    @app.get("/sessions/{session_id}/signals")
    def get_signals(session_id: str) -> Optional[Dict[str, Any]]:
        sfile = orch.session_dir(session_id) / "signals.parquet"
        if not sfile.is_file():
            return None
        return SignalSeries.from_parquet(sfile).model_dump(mode="json")

    @app.get("/sessions/{session_id}/clips")
    def list_session_clips(session_id: str) -> List[Dict[str, Any]]:
        return [_serialize_clip(c) for c in orch.db.list_clips(session_id)]

    # --- Clips & EditPlan Editor API ---------------------------------------

    @app.get("/clips/{clip_id}")
    def get_clip_detail(clip_id: str) -> Dict[str, Any]:
        crow = orch.db.get_clip(clip_id)
        if not crow:
            raise HTTPException(404, "Clip no encontrado")
        srow = orch.db.get_session(crow["session_id"])
        if not srow:
            raise HTTPException(404, "Sesión asociada no encontrada")
        preset = load_preset(srow.get("style_preset") or cfg.style_preset)
        return {
            "clip": _serialize_clip(crow),
            "session": _serialize_session(orch, srow),
            "preset": preset.model_dump(mode="json"),
        }

    @app.put("/clips/{clip_id}/editplan")
    async def update_editplan(clip_id: str, plan: EditPlan) -> Dict[str, Any]:
        try:
            saved = await orch.save_clip_editplan(clip_id, plan)
        except KeyError as exc:
            raise HTTPException(404, str(exc)) from exc
        crow = orch.db.get_clip(clip_id)
        assert crow is not None
        return {"clip": _serialize_clip(crow), "editplan": saved.model_dump(mode="json", exclude_none=True)}

    @app.post("/clips/{clip_id}/render")
    async def render_clip_endpoint(clip_id: str, body: RenderClipBody) -> Dict[str, Any]:
        crow = orch.db.get_clip(clip_id)
        if not crow:
            raise HTTPException(404, "Clip no encontrado")
        mp4 = await orch.render_and_deliver_clip(
            clip_id=clip_id,
            quality=body.quality,
            priority=1000.0,  # Interactive editor requests always jump to front of render queue
            upload_to_drive=(body.quality == "final" and body.upload_to_drive),
        )
        updated = orch.db.get_clip(clip_id)
        assert updated is not None
        return {"clip": _serialize_clip(updated), "mp4_path": str(mp4)}

    @app.get("/clips/{clip_id}/file")
    def serve_rendered_clip(
        clip_id: str,
        quality: Literal["final", "draft"] = "final",
        download: bool = False,
    ) -> FileResponse:
        crow = orch.db.get_clip(clip_id)
        if not crow:
            raise HTTPException(404, "Clip no encontrado")
        p_str = crow.get("draft_mp4_path") if quality == "draft" else crow.get("final_mp4_path")
        if not p_str and quality == "final":
            p_str = crow.get("draft_mp4_path")
        if not p_str or not Path(p_str).is_file():
            raise HTTPException(404, f"Archivo MP4 ({quality}) aún no renderizado")
        return FileResponse(
            p_str,
            media_type="video/mp4",
            filename=f"{clip_id}_{quality}.mp4" if download else None,
        )

    # --- Server-Sent Events (SSE) ------------------------------------------

    @app.get("/events")
    async def sse_events(session_id: Optional[str] = Query(default=None)) -> StreamingResponse:
        return StreamingResponse(
            orch.events.subscribe(filter_session_id=session_id),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    return app
