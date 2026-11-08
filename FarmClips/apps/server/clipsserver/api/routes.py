"""FastAPI HTTP & SSE routes for ClipsApp unified server."""

from __future__ import annotations

import asyncio
import dataclasses
import json
import re
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

import httpx
from clipscore.domain import SessionState, SignalSeries, SyncResult, new_id
from clipseditplan import EditPlan
from clipsmedia.drive import (
    GoogleDriveOAuthConnector,
    GoogleDriveServiceAccountConnector,
    LocalFolderDriveConnector,
)
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
from fastapi.responses import FileResponse, HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from ..config import (
    ServerSettings,
    get_server_settings,
    is_masked_or_blank,
    reload_server_settings,
    update_dotenv_values,
)
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


class CreateDriveSessionBody(BaseModel):
    title: str = ""
    folder_id: Optional[str] = None
    gameplay_file_id: Optional[str] = None
    camera_file_id: Optional[str] = None
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
    async_mode: bool = False


class CleanupBody(BaseModel):
    ttl_days: Optional[float] = None
    include_inputs: bool = False


class TestWebhookBody(BaseModel):
    webhook_url: Optional[str] = None
    session_id: Optional[str] = None


class UpdateSettingsBody(BaseModel):
    stt_primary: Optional[Literal["deepgram", "groq", "fixture"]] = None
    stt_backup: Optional[Literal["groq", "deepgram", "fixture", "none"]] = None
    deepgram_model: Optional[str] = None
    groq_stt_model: Optional[str] = None
    llm_primary: Optional[Literal["gemini", "openai_compat", "fixture"]] = None
    llm_model: Optional[str] = None
    llm_backup: Optional[Literal["openai_compat", "gemini", "fixture", "none"]] = None
    llm_backup_model: Optional[str] = None
    llm_backup_base_url: Optional[str] = None
    max_budget_usd: Optional[float] = Field(default=None, ge=0.05, le=10000.0)
    deepgram_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None
    gemini_api_key: Optional[str] = None
    openai_api_key: Optional[str] = None
    webhook_url: Optional[str] = None
    temp_ttl_days: Optional[float] = Field(default=None, ge=0.0, le=3650.0)
    drive_mode: Optional[Literal["local", "oauth", "service_account", "disabled"]] = None
    drive_client_id: Optional[str] = None
    drive_client_secret: Optional[str] = None
    drive_root_folder_id: Optional[str] = None
    drive_local_dir: Optional[str] = None
    drive_poll_sec: Optional[float] = Field(default=None, ge=0.0, le=86400.0)


class TestConnectionBody(BaseModel):
    provider: Literal["deepgram", "groq", "gemini", "openai_compat", "openai", "fixture"]
    api_key: Optional[str] = None
    model: Optional[str] = None
    base_url: Optional[str] = None


class FreeTierCalibrationBody(BaseModel):
    provider: Literal["deepgram"] = "deepgram"
    # Saldo real mostrado en la consola del proveedor. Si se omite, se intenta leer en vivo vía API.
    balance_usd: Optional[float] = Field(default=None, ge=0.0, le=100000.0)
    credit_usd: float = Field(default=200.0, gt=0.0, le=100000.0)


async def fetch_deepgram_live_balance(api_key: str) -> Dict[str, Any]:
    """Read the real Deepgram balance (requires an API key with the `billing:read` scope)."""
    headers = {"Authorization": f"Token {api_key}"}
    async with httpx.AsyncClient(base_url="https://api.deepgram.com/v1", headers=headers, timeout=15.0) as client:
        projs = await client.get("/projects")
        if projs.status_code >= 400:
            return {"ok": False, "status_code": projs.status_code, "detail": _extract_provider_error(projs)}
        items = projs.json().get("projects", [])
        if not items:
            return {"ok": False, "status_code": 404, "detail": "La API key no tiene proyectos asociados."}
        pid = items[0]["project_id"]
        bal = await client.get(f"/projects/{pid}/balances")
        if bal.status_code >= 400:
            return {"ok": False, "status_code": bal.status_code, "detail": _extract_provider_error(bal)}
        balances = bal.json().get("balances", [])
        total = sum(float(b.get("amount") or 0.0) for b in balances if str(b.get("units", "usd")).lower() == "usd")
        return {"ok": True, "status_code": 200, "balance_usd": round(total, 4)}


def _extract_provider_error(resp: httpx.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            err = data.get("error")
            if isinstance(err, dict) and err.get("message"):
                return str(err["message"])
            if isinstance(err, str) and err:
                return err
            if data.get("err_msg"):
                return str(data["err_msg"])
            if data.get("message"):
                return str(data["message"])
            if data.get("detail"):
                return str(data["detail"])
    except Exception:
        pass
    return (resp.text or f"HTTP {resp.status_code}").strip()[:220]


async def test_provider_connection(
    provider: str,
    api_key: str,
    model: Optional[str] = None,
    base_url: Optional[str] = None,
    client: Optional[httpx.AsyncClient] = None,
) -> Dict[str, Any]:
    """Perform a fast, lightweight ping against Deepgram, Groq, Gemini, or OpenAI-compatible API."""
    prov = provider.strip().lower()
    if prov == "openai":
        prov = "openai_compat"

    if prov == "fixture":
        return {
            "ok": True,
            "provider": "fixture",
            "latency_ms": 1,
            "status_code": 200,
            "detail": "Modo offline (fixtures locales) activo sin consumo de API.",
        }

    target_base = (base_url or "https://api.openai.com/v1").rstrip("/")
    is_local_oa = prov == "openai_compat" and any(h in target_base for h in ("127.0.0.1", "localhost"))

    if not api_key and not is_local_oa:
        return {
            "ok": False,
            "provider": prov,
            "latency_ms": 0,
            "status_code": 401,
            "detail": f"No se ingresó ni existe una API Key configurada para {prov}.",
        }

    owns_client = client is None
    http = client or httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=6.0))
    t0 = time.perf_counter()
    try:
        if prov == "deepgram":
            resp = await http.get(
                "https://api.deepgram.com/v1/projects",
                headers={"Authorization": f"Token {api_key}"},
            )
            label = f"Deepgram API ({model or 'nova-3'})"
        elif prov == "groq":
            resp = await http.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            label = f"Groq Cloud ({model or 'whisper-large-v3-turbo'})"
        elif prov == "gemini":
            resp = await http.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": api_key, "pageSize": "5"},
            )
            label = f"Google Gemini API ({model or 'gemini-3.5-flash-lite'})"
        elif prov == "openai_compat":
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
            resp = await http.get(f"{target_base}/models", headers=headers)
            label = f"OpenAI-compatible ({target_base})"
        else:
            return {
                "ok": False,
                "provider": prov,
                "latency_ms": 0,
                "status_code": 400,
                "detail": f"Proveedor no soportado: {prov}",
            }

        latency_ms = max(1, int((time.perf_counter() - t0) * 1000))
        if 200 <= resp.status_code < 300:
            return {
                "ok": True,
                "provider": prov,
                "latency_ms": latency_ms,
                "status_code": resp.status_code,
                "detail": f"Conexión verificada con {label} ({latency_ms} ms).",
            }
        err_msg = _extract_provider_error(resp)
        return {
            "ok": False,
            "provider": prov,
            "latency_ms": latency_ms,
            "status_code": resp.status_code,
            "detail": f"Error {resp.status_code} en {label}: {err_msg}",
        }
    except Exception as exc:
        latency_ms = max(1, int((time.perf_counter() - t0) * 1000))
        return {
            "ok": False,
            "provider": prov,
            "latency_ms": latency_ms,
            "status_code": 0,
            "detail": f"Error de conexión con {prov}: {exc}",
        }
    finally:
        if owns_client:
            await http.aclose()


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
    if "clips_count" in row and "rendered_count" in row:
        clips_count = int(row["clips_count"] or 0)
        rendered_count = int(row["rendered_count"] or 0)
    else:
        clips = orch.db.list_clips(row["id"])
        clips_count = len(clips)
        rendered_count = sum(1 for c in clips if c.get("final_mp4_path") and Path(c["final_mp4_path"]).is_file())
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
        "clips_count": clips_count,
        "rendered_count": rendered_count,
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

    @app.get("/analytics/summary")
    def get_analytics_summary() -> Dict[str, Any]:
        return orch.db.analytics_summary(cfg.max_budget_usd)

    @app.get("/analytics/breakdown")
    def get_analytics_breakdown() -> Dict[str, Any]:
        return orch.db.analytics_breakdown()

    @app.get("/analytics/logs")
    def get_analytics_logs(
        provider: Optional[str] = Query(default=None),
        kind: Optional[str] = Query(default=None),
        session_id: Optional[str] = Query(default=None),
        date_from: Optional[str] = Query(default=None),
        date_to: Optional[str] = Query(default=None),
        search: Optional[str] = Query(default=None),
        limit: int = Query(default=50, ge=1, le=500),
        offset: int = Query(default=0, ge=0),
    ) -> Dict[str, Any]:
        return orch.db.analytics_logs(
            provider=provider,
            kind=kind,
            session_id=session_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
            limit=limit,
            offset=offset,
        )

    @app.post("/analytics/free-tier/calibrate")
    async def calibrate_free_tier(body: FreeTierCalibrationBody) -> Dict[str, Any]:
        balance = body.balance_usd
        source = "manual"
        if balance is None:
            live = await fetch_deepgram_live_balance(cfg.deepgram_api_key)
            if not live.get("ok"):
                hint = (
                    " Tu API key no tiene el permiso 'billing:read'; ingresa el saldo manualmente "
                    "o usa una key de rol Owner/Admin."
                    if live.get("status_code") == 403
                    else ""
                )
                raise HTTPException(status_code=400, detail=f"No se pudo leer el saldo de Deepgram: {live.get('detail')}.{hint}")
            balance = float(live["balance_usd"])
            source = "live"
        if balance > body.credit_usd:
            raise HTTPException(status_code=400, detail="El saldo no puede ser mayor que el crédito gratuito total.")
        saved = orch.db.set_provider_balance(body.provider, balance, body.credit_usd, source=source)
        return {"ok": True, "calibration": saved, "summary": orch.db.analytics_summary(cfg.max_budget_usd)}

    @app.delete("/analytics/free-tier/calibrate/{provider}")
    def reset_free_tier_calibration(provider: str) -> Dict[str, Any]:
        orch.db.clear_provider_balance(provider)
        return {"ok": True, "summary": orch.db.analytics_summary(cfg.max_budget_usd)}

    @app.get("/settings")
    def get_settings_endpoint() -> Dict[str, Any]:
        return cfg.to_masked_dict()

    @app.post("/settings")
    def update_settings_endpoint(body: UpdateSettingsBody) -> Dict[str, Any]:
        nonlocal cfg
        env_updates: Dict[str, str] = {}

        if body.stt_primary is not None:
            env_updates["CLIPS_STT_PRIMARY"] = body.stt_primary.strip().lower()
        if body.stt_backup is not None:
            env_updates["CLIPS_STT_BACKUP"] = body.stt_backup.strip().lower()
        if body.deepgram_model is not None and body.deepgram_model.strip():
            env_updates["CLIPS_DEEPGRAM_MODEL"] = body.deepgram_model.strip()
        if body.groq_stt_model is not None and body.groq_stt_model.strip():
            env_updates["CLIPS_GROQ_STT_MODEL"] = body.groq_stt_model.strip()

        if body.llm_primary is not None:
            env_updates["CLIPS_LLM_PRIMARY"] = body.llm_primary.strip().lower()
        if body.llm_model is not None and body.llm_model.strip():
            env_updates["CLIPS_LLM_MODEL"] = body.llm_model.strip()
        if body.llm_backup is not None:
            env_updates["CLIPS_LLM_BACKUP"] = body.llm_backup.strip().lower()
        if body.llm_backup_model is not None and body.llm_backup_model.strip():
            env_updates["CLIPS_LLM_BACKUP_MODEL"] = body.llm_backup_model.strip()
        if body.llm_backup_base_url is not None and body.llm_backup_base_url.strip():
            env_updates["CLIPS_LLM_BACKUP_BASE_URL"] = body.llm_backup_base_url.strip()

        if body.max_budget_usd is not None:
            env_updates["CLIPS_MAX_BUDGET_USD"] = f"{float(body.max_budget_usd):.2f}"
        if body.webhook_url is not None:
            env_updates["CLIPS_WEBHOOK_URL"] = body.webhook_url.strip()
        if body.temp_ttl_days is not None:
            env_updates["CLIPS_TEMP_TTL_DAYS"] = str(float(body.temp_ttl_days))


        if body.drive_mode is not None:
            env_updates["CLIPS_DRIVE_MODE"] = body.drive_mode.strip().lower()
        if body.drive_client_id is not None:
            env_updates["CLIPS_DRIVE_CLIENT_ID"] = body.drive_client_id.strip()
        if not is_masked_or_blank(body.drive_client_secret, cfg.drive_client_secret):
            env_updates["CLIPS_DRIVE_CLIENT_SECRET"] = (body.drive_client_secret or "").strip()
        if body.drive_root_folder_id is not None:
            env_updates["CLIPS_DRIVE_ROOT_FOLDER_ID"] = body.drive_root_folder_id.strip()
        if body.drive_local_dir is not None and body.drive_local_dir.strip():
            env_updates["CLIPS_DRIVE_LOCAL_DIR"] = body.drive_local_dir.strip()
        if body.drive_poll_sec is not None:
            env_updates["CLIPS_DRIVE_POLL_SEC"] = str(float(body.drive_poll_sec))

        # API Keys: if blank or masked, keep existing value in .env and memory
        if not is_masked_or_blank(body.deepgram_api_key, cfg.deepgram_api_key):
            env_updates["DEEPGRAM_API_KEY"] = (body.deepgram_api_key or "").strip()
        if not is_masked_or_blank(body.groq_api_key, cfg.groq_api_key):
            env_updates["GROQ_API_KEY"] = (body.groq_api_key or "").strip()
        if not is_masked_or_blank(body.gemini_api_key, cfg.gemini_api_key):
            env_updates["GEMINI_API_KEY"] = (body.gemini_api_key or "").strip()
        if not is_masked_or_blank(body.openai_api_key, cfg.openai_api_key):
            env_updates["OPENAI_API_KEY"] = (body.openai_api_key or "").strip()

        # If switching to real providers, ensure CLIPS_FIXTURES_DIR is cleared and purge any old fixture cache
        next_stt = env_updates.get("CLIPS_STT_PRIMARY", cfg.stt_primary)
        next_llm = env_updates.get("CLIPS_LLM_PRIMARY", cfg.llm_primary)
        if next_stt != "fixture" and next_llm != "fixture":
            env_updates["CLIPS_FIXTURES_DIR"] = ""
            orch.db.purge_fixture_cache()

        update_dotenv_values(env_updates)
        reloaded = reload_server_settings()
        if settings is not None:
            reloaded = dataclasses.replace(
                reloaded,
                data_dir=cfg.data_dir,
                drive_local_dir=cfg.drive_local_dir if body.drive_local_dir is None else reloaded.drive_local_dir,
                fixtures_dir=reloaded.fixtures_dir or cfg.fixtures_dir,
            )
        cfg = reloaded
        app.state.settings = cfg
        orch.reload_settings(cfg)
        custom_client = getattr(app.state, "test_http_client", None)
        if custom_client is not None and isinstance(orch.drive, GoogleDriveServiceAccountConnector):
            orch.drive._client = custom_client

        budget = orch.db.budget_summary(cfg.max_budget_usd)
        orch.events.publish("budget_update", **budget)
        orch.events.publish(
            "settings_updated",
            stt_primary=cfg.stt_primary,
            llm_primary=cfg.llm_primary,
            llm_model=cfg.llm_model,
            max_budget_usd=cfg.max_budget_usd,
            drive_mode=cfg.drive_mode,
        )
        return cfg.to_masked_dict()

    @app.post("/settings/test-connection")
    async def test_settings_connection_endpoint(body: TestConnectionBody) -> Dict[str, Any]:
        prov = body.provider.strip().lower()
        if prov == "openai":
            prov = "openai_compat"

        saved_keys = {
            "deepgram": cfg.deepgram_api_key,
            "groq": cfg.groq_api_key,
            "gemini": cfg.gemini_api_key,
            "openai_compat": cfg.openai_api_key or cfg.groq_api_key,
        }
        saved_key = saved_keys.get(prov, "")
        if body.api_key and not is_masked_or_blank(body.api_key, saved_key):
            effective_key = body.api_key.strip()
        else:
            effective_key = saved_key

        effective_base_url = body.base_url or cfg.llm_backup_base_url
        custom_client = getattr(app.state, "test_http_client", None)
        return await test_provider_connection(
            provider=prov,
            api_key=effective_key,
            model=body.model,
            base_url=effective_base_url,
            client=custom_client,
        )

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
        return FileResponse(
            fpath,
            media_type="font/ttf",
            headers={"Cache-Control": "public, max-age=86400, immutable"},
        )

    @app.get("/emojis")
    def get_emojis_catalog() -> List[Dict[str, str]]:
        return [
            {**item, "url": f"/emojis/{item['id']}.png"}
            for item in list_emoji_catalog()
        ]

    @app.get("/emojis/{emoji_id}.png")
    def serve_emoji(emoji_id: str) -> FileResponse:
        png = ensure_emoji_png(emoji_id)
        return FileResponse(
            png,
            media_type="image/png",
            headers={"Cache-Control": "public, max-age=86400, immutable"},
        )

    @app.get("/sfx/{sfx_id}.wav")
    def serve_sfx(sfx_id: str) -> FileResponse:
        wav = ensure_sfx_wav(sfx_id)
        return FileResponse(
            wav,
            media_type="audio/wav",
            headers={"Cache-Control": "public, max-age=86400, immutable"},
        )

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

        oauth_connected = cfg.is_drive_oauth_connected()
        user_email: Optional[str] = None
        user_name: Optional[str] = None
        if isinstance(orch.drive, GoogleDriveOAuthConnector):
            oauth_connected = orch.drive.is_connected()
            user_email = orch.drive.user_email
            user_name = orch.drive.user_name
        elif cfg.drive_oauth_token_path.is_file():
            try:
                tok_raw = json.loads(cfg.drive_oauth_token_path.read_text(encoding="utf-8"))
                user_email = tok_raw.get("user_email") or None
                user_name = tok_raw.get("user_name") or None
            except Exception:
                pass
        elif isinstance(orch.drive, GoogleDriveServiceAccountConnector):
            user_email = orch.drive.client_email

        if cfg.drive_mode == "disabled" or orch.drive is None:
            connected = False
        elif cfg.drive_mode == "oauth":
            connected = oauth_connected
        elif cfg.drive_mode == "service_account":
            connected = isinstance(orch.drive, GoogleDriveServiceAccountConnector)
        else:
            connected = isinstance(orch.drive, LocalFolderDriveConnector)

        return {
            "mode": cfg.drive_mode,
            "connected": connected,
            "oauth_connected": oauth_connected,
            "client_configured": bool(cfg.drive_client_id and cfg.drive_client_secret),
            "client_id": cfg.drive_client_id,
            "has_client_secret": bool(cfg.drive_client_secret),
            "user_email": user_email,
            "user_name": user_name,
            "root_folder_id": cfg.drive_root_folder_id or ("root" if cfg.drive_mode == "oauth" else None),
            "local_dir": str(cfg.drive_local_dir),
            "poll_sec": cfg.drive_poll_sec,
            "entradas": entradas_folders,
            "salidas": salidas_folders,
        }

    @app.get("/drive/auth/url")
    def drive_auth_url(
        redirect_uri: Optional[str] = Query(default=None),
        state: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        if not cfg.drive_client_id or not cfg.drive_client_secret:
            raise HTTPException(
                400,
                "Configura CLIPS_DRIVE_CLIENT_ID y CLIPS_DRIVE_CLIENT_SECRET antes de vincular Google Drive OAuth 2.0.",
            )
        effective_redirect = (redirect_uri or "").strip() or f"http://{cfg.host}:{cfg.port}/drive/auth/callback"
        effective_state = (state or "").strip() or new_id("oauth")
        app.state.last_drive_redirect_uri = effective_redirect

        conn = (
            orch.drive
            if isinstance(orch.drive, GoogleDriveOAuthConnector)
            else GoogleDriveOAuthConnector(
                client_id=cfg.drive_client_id,
                client_secret=cfg.drive_client_secret,
                token_path=cfg.drive_oauth_token_path,
                root_folder_id=cfg.drive_root_folder_id or "root",
            )
        )
        auth_url = conn.build_auth_url(redirect_uri=effective_redirect, state=effective_state)
        return {
            "auth_url": auth_url,
            "url": auth_url,
            "redirect_uri": effective_redirect,
            "state": effective_state,
        }

    @app.get("/drive/auth/callback", response_model=None)
    async def drive_auth_callback(
        request: Request,
        code: Optional[str] = Query(default=None),
        state: Optional[str] = Query(default=None),
        error: Optional[str] = Query(default=None),
        redirect_uri: Optional[str] = Query(default=None),
        format: Optional[str] = Query(default=None),
    ) -> Any:
        nonlocal cfg
        if error:
            raise HTTPException(400, f"Autorización de Google Drive rechazada: {error}")
        if not code or not code.strip():
            raise HTTPException(400, "Falta el parámetro 'code' de autorización OAuth 2.0.")
        if not cfg.drive_client_id or not cfg.drive_client_secret:
            raise HTTPException(
                400,
                "Configura CLIPS_DRIVE_CLIENT_ID y CLIPS_DRIVE_CLIENT_SECRET antes de completar OAuth 2.0.",
            )

        effective_redirect = (
            (redirect_uri or "").strip()
            or getattr(app.state, "last_drive_redirect_uri", None)
            or f"http://{cfg.host}:{cfg.port}/drive/auth/callback"
        )

        if isinstance(orch.drive, GoogleDriveOAuthConnector):
            oauth_conn = orch.drive
            oauth_conn.client_id = cfg.drive_client_id
            oauth_conn.client_secret = cfg.drive_client_secret
        else:
            oauth_conn = GoogleDriveOAuthConnector(
                client_id=cfg.drive_client_id,
                client_secret=cfg.drive_client_secret,
                token_path=cfg.drive_oauth_token_path,
                root_folder_id=cfg.drive_root_folder_id or "root",
            )

        custom_client = getattr(app.state, "test_http_client", None)
        if custom_client is not None:
            oauth_conn._client = custom_client

        try:
            token_data = await oauth_conn.exchange_code(code=code.strip(), redirect_uri=effective_redirect)
        except Exception as exc:
            raise HTTPException(400, f"Error intercambiando código OAuth 2.0 con Google Drive: {exc}") from exc

        if cfg.drive_mode != "oauth":
            update_dotenv_values({"CLIPS_DRIVE_MODE": "oauth"})
            cfg = dataclasses.replace(cfg, drive_mode="oauth")
            app.state.settings = cfg
            orch.settings = cfg
        orch.drive = oauth_conn

        orch.events.publish(
            "drive_auth_updated",
            connected=True,
            mode=cfg.drive_mode,
            user_email=token_data.get("user_email"),
        )

        accept_hdr = request.headers.get("accept", "")
        if format == "html" or ("text/html" in accept_hdr and format != "json"):
            target_settings_url = f"{cfg.public_web_url.rstrip('/')}/settings?drive_oauth=connected"
            email_txt = token_data.get("user_email") or "Cuenta de Google vinculada"
            html_doc = f"""<!DOCTYPE html>
<html lang="es">
<head>
  <meta charset="utf-8" />
  <title>Google Drive Conectado — FarmClips</title>
  <style>
    body {{ background: #090d16; color: #f8fafc; font-family: system-ui, sans-serif; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
    .card {{ background: #1e293b; border: 1px solid rgba(255,255,255,0.1); border-radius: 24px; padding: 32px; max-width: 420px; text-align: center; box-shadow: 0 20px 40px rgba(0,0,0,0.4); }}
    .badge {{ display: inline-block; background: rgba(52,211,153,0.15); color: #6ee7b7; border-radius: 999px; padding: 6px 14px; font-size: 12px; font-weight: 700; margin-bottom: 12px; }}
    a {{ display: inline-block; margin-top: 16px; background: #fbbf24; color: #090d16; text-decoration: none; font-weight: 800; padding: 10px 20px; border-radius: 999px; font-size: 14px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="badge">OAuth 2.0 Verificado</div>
    <h2 style="margin: 0 0 8px 0;">Google Drive conectado</h2>
    <p style="color: #94a3b8; font-size: 14px; margin: 0;">{email_txt}</p>
    <a href="{target_settings_url}">Volver a FarmClips Studio</a>
  </div>
  <script>
    try {{
      if (window.opener) {{
        window.opener.postMessage({{ type: "drive_oauth_connected", ok: true }}, "*");
        setTimeout(() => window.close(), 600);
      }}
    }} catch (e) {{}}
  </script>
</body>
</html>"""
            return HTMLResponse(content=html_doc)

        return {
            "ok": True,
            "mode": cfg.drive_mode,
            "connected": True,
            "oauth_connected": True,
            "state": state,
            "user_email": token_data.get("user_email"),
            "user_name": token_data.get("user_name"),
            "token_path": str(cfg.drive_oauth_token_path),
        }

    @app.post("/drive/auth/disconnect")
    async def drive_auth_disconnect() -> Dict[str, Any]:
        if isinstance(orch.drive, GoogleDriveOAuthConnector):
            await orch.drive.disconnect()
        else:
            cfg.drive_oauth_token_path.unlink(missing_ok=True)
        orch.events.publish("drive_auth_updated", connected=False, mode=cfg.drive_mode)
        return {
            "ok": True,
            "mode": cfg.drive_mode,
            "connected": False,
            "oauth_connected": False,
        }

    @app.get("/drive/files")
    async def list_drive_files(
        folder_id: Optional[str] = Query(default=None),
        query: Optional[str] = Query(default=None),
        q: Optional[str] = Query(default=None),
    ) -> Dict[str, Any]:
        if orch.drive is None or cfg.drive_mode == "disabled":
            raise HTTPException(
                400,
                "Google Drive está deshabilitado (CLIPS_DRIVE_MODE=disabled). Activa 'oauth' o 'local' en Configuración.",
            )
        if isinstance(orch.drive, GoogleDriveOAuthConnector) and not orch.drive.is_connected():
            raise HTTPException(
                401,
                "Google Drive OAuth 2.0 no está vinculado. Conecta tu cuenta en Configuración (/settings).",
            )
        custom_client = getattr(app.state, "test_http_client", None)
        if custom_client is not None and isinstance(orch.drive, GoogleDriveServiceAccountConnector):
            orch.drive._client = custom_client

        effective_query = query if query is not None else q
        try:
            browsed = await orch.drive.browse_folder(folder_id=folder_id, query=effective_query)
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"Error consultando archivos en Google Drive: {exc}") from exc

        return {"mode": cfg.drive_mode, **browsed}

    @app.post("/drive/sessions")
    async def create_drive_session_endpoint(body: CreateDriveSessionBody) -> Dict[str, Any]:
        if orch.drive is None or cfg.drive_mode == "disabled":
            raise HTTPException(400, "El conector de Google Drive está deshabilitado.")
        if isinstance(orch.drive, GoogleDriveOAuthConnector) and not orch.drive.is_connected():
            raise HTTPException(401, "Google Drive OAuth 2.0 no está vinculado. Conecta tu cuenta en Configuración.")

        custom_client = getattr(app.state, "test_http_client", None)
        if custom_client is not None and isinstance(orch.drive, GoogleDriveServiceAccountConnector):
            orch.drive._client = custom_client

        try:
            row = await orch.create_session_from_drive(
                gameplay_file_id=body.gameplay_file_id,
                camera_file_id=body.camera_file_id,
                folder_id=body.folder_id,
                title=body.title,
                recording_name=body.recording_name,
                language=body.language or "es",
                style_preset=body.style_preset or cfg.style_preset,
                auto_start=body.auto_start,
            )
        except FileNotFoundError as exc:
            raise HTTPException(404, str(exc)) from exc
        except (ValueError, RuntimeError) as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:
            raise HTTPException(502, f"Error descargando sesión desde Google Drive: {exc}") from exc

        return _serialize_session(orch, row)

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

        frames_cache_dir = cfg.data_dir / "cache" / "frames"
        frames_cache_dir.mkdir(parents=True, exist_ok=True)
        t_bucket_ds = int(round(t * 10.0))
        cached_jpg = frames_cache_dir / f"{session_id}_{source}_{width}_{t_bucket_ds}.jpg"
        if cached_jpg.is_file() and cached_jpg.stat().st_size > 100:
            return Response(
                cached_jpg.read_bytes(),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=3600", "X-Frame-Cache": "HIT"},
            )

        extract_frame(src_path, t, cached_jpg, width=width)
        return Response(
            cached_jpg.read_bytes(),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=3600", "X-Frame-Cache": "MISS"},
        )

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
        return FileResponse(
            src_path,
            media_type="video/mp4",
            headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"},
        )

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
        if body.async_mode:
            asyncio.create_task(
                orch.render_and_deliver_clip(
                    clip_id=clip_id,
                    quality=body.quality,
                    priority=1000.0,
                    upload_to_drive=(body.quality == "final" and body.upload_to_drive),
                )
            )
            return {"clip": _serialize_clip(crow), "mp4_path": None, "queued": True}
        mp4 = await orch.render_and_deliver_clip(
            clip_id=clip_id,
            quality=body.quality,
            priority=1000.0,  # Interactive editor requests always jump to front of render queue
            upload_to_drive=(body.quality == "final" and body.upload_to_drive),
        )
        updated = orch.db.get_clip(clip_id)
        assert updated is not None
        return {"clip": _serialize_clip(updated), "mp4_path": str(mp4), "queued": False}

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
            headers={"Accept-Ranges": "bytes", "Cache-Control": "public, max-age=3600"},
        )

    @app.get("/clips/{clip_id}/thumbnail")
    def get_clip_thumbnail(
        clip_id: str,
        width: int = Query(default=540, ge=240, le=1080),
    ) -> Response:
        crow = orch.db.get_clip(clip_id)
        if not crow:
            raise HTTPException(404, "Clip no encontrado")

        thumbnails_dir = cfg.data_dir / "cache" / "thumbnails"
        thumbnails_dir.mkdir(parents=True, exist_ok=True)
        cached_jpg = thumbnails_dir / f"{clip_id}_{width}.jpg"

        if cached_jpg.is_file() and cached_jpg.stat().st_size > 100:
            return Response(
                cached_jpg.read_bytes(),
                media_type="image/jpeg",
                headers={"Cache-Control": "public, max-age=3600", "X-Frame-Cache": "HIT"},
            )

        # 1. Si existe video renderizado (final o draft), extraer frame directamente del MP4
        rendered_mp4 = crow.get("final_mp4_path") or crow.get("draft_mp4_path")
        if rendered_mp4 and Path(rendered_mp4).is_file():
            try:
                extract_frame(rendered_mp4, 1.0, cached_jpg, width=width)
                return Response(
                    cached_jpg.read_bytes(),
                    media_type="image/jpeg",
                    headers={"Cache-Control": "public, max-age=3600", "X-Frame-Cache": "MISS"},
                )
            except Exception:
                pass  # Fallback a composición de fuentes originales

        # 2. Generar composición vertical 9:16 desde las fuentes originales de la sesión
        srow = orch.db.get_session(crow["session_id"])
        if not srow:
            raise HTTPException(404, "Sesión asociada no encontrada")

        gameplay_path = srow.get("gameplay_path")
        if not gameplay_path or not Path(gameplay_path).is_file():
            raise HTTPException(404, "Archivo de gameplay no encontrado")

        camera_path = srow.get("camera_path")
        has_camera = bool(camera_path and Path(camera_path).is_file())

        start_sec = float(crow.get("start_sec") or 0.0)
        end_sec = float(crow.get("end_sec") or (start_sec + 30.0))
        t_game = max(0.0, min(start_sec + 1.0, end_sec - 0.2))

        sync_info = json.loads(srow.get("sync_json") or "{}") if srow.get("sync_json") else {}
        shift_sec = float(sync_info.get("shift_sec", 0.0)) if isinstance(sync_info, dict) else 0.0
        t_cam = max(0.0, t_game - shift_sec)

        import cv2
        import numpy as np

        target_h = int(round(width * 16 / 9))
        canvas = np.zeros((target_h, width, 3), dtype=np.uint8)

        temp_dir = thumbnails_dir / f"tmp_{clip_id}_{width}"
        temp_dir.mkdir(parents=True, exist_ok=True)
        tmp_game = temp_dir / "game.jpg"
        tmp_cam = temp_dir / "cam.jpg"

        try:
            extract_frame(gameplay_path, t_game, tmp_game, width=width)
            img_game = cv2.imread(str(tmp_game)) if tmp_game.is_file() else None

            img_cam = None
            if has_camera:
                try:
                    extract_frame(camera_path, t_cam, tmp_cam, width=width)
                    img_cam = cv2.imread(str(tmp_cam)) if tmp_cam.is_file() else None
                except Exception:
                    img_cam = None

            if img_game is not None and img_cam is not None:
                # Composición 40% cámara arriba / 60% gameplay abajo (estilo Hormozi gaming clásico)
                cam_target_h = int(round(target_h * 0.40))
                game_target_h = target_h - cam_target_h

                # Cover crop cámara
                ch, cw = img_cam.shape[:2]
                s_cam = max(width / max(1, cw), cam_target_h / max(1, ch))
                rw_c, rh_c = max(width, int(round(cw * s_cam))), max(cam_target_h, int(round(ch * s_cam)))
                res_cam = cv2.resize(img_cam, (rw_c, rh_c), interpolation=cv2.INTER_AREA)
                cx_off = max(0, (rw_c - width) // 2)
                cy_off = max(0, (rh_c - cam_target_h) // 2)
                canvas[0:cam_target_h, 0:width] = res_cam[cy_off : cy_off + cam_target_h, cx_off : cx_off + width]

                # Cover crop gameplay
                gh, gw = img_game.shape[:2]
                s_game = max(width / max(1, gw), game_target_h / max(1, gh))
                rw_g, rh_g = max(width, int(round(gw * s_game))), max(game_target_h, int(round(gh * s_game)))
                res_game = cv2.resize(img_game, (rw_g, rh_g), interpolation=cv2.INTER_AREA)
                gx_off = max(0, (rw_g - width) // 2)
                gy_off = max(0, (rh_g - game_target_h) // 2)
                canvas[cam_target_h:target_h, 0:width] = res_game[gy_off : gy_off + game_target_h, gx_off : gx_off + width]

                # Separador sutil
                cv2.line(canvas, (0, cam_target_h), (width, cam_target_h), (25, 25, 25), 2)

            elif img_game is not None:
                # Sólo gameplay: cover crop centrado vertical
                gh, gw = img_game.shape[:2]
                s_game = max(width / max(1, gw), target_h / max(1, gh))
                rw_g, rh_g = max(width, int(round(gw * s_game))), max(target_h, int(round(gh * s_game)))
                res_game = cv2.resize(img_game, (rw_g, rh_g), interpolation=cv2.INTER_AREA)
                gx_off = max(0, (rw_g - width) // 2)
                gy_off = max(0, (rh_g - target_h) // 2)
                canvas[:, :] = res_game[gy_off : gy_off + target_h, gx_off : gx_off + width]
            else:
                raise RuntimeError("No se pudieron decodificar fotogramas de la sesión")

            cv2.imwrite(str(cached_jpg), canvas, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)

        return Response(
            cached_jpg.read_bytes(),
            media_type="image/jpeg",
            headers={"Cache-Control": "public, max-age=3600", "X-Frame-Cache": "MISS"},
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
