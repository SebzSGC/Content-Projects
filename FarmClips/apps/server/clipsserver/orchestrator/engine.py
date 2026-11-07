"""Durable SQLite + asyncio orchestrator implementing the exact 7-step hybrid pipeline and Drive watcher."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from clipscore.domain import (
    CuratedClip,
    PreparedMedia,
    SessionState,
    SignalSeries,
    SyncResult,
    TranscriptWord,
    Utterance,
)
from clipscore.selection import resolve_curated_clips
from clipscore.timeline import build_timeline_windows_if_needed, group_words_into_utterances
from clipseditplan import EditPlan
from clipsmedia.drive import (
    DriveConnector,
    GoogleDriveOAuthConnector,
    GoogleDriveServiceAccountConnector,
    LocalFolderDriveConnector,
    RemoteFileEntry,
)
from clipsproviders.notifications import send_delivery_webhook
from clipsrender import RenderQuality, ResolveMcpBridge, detect_resolve_environment
from clipsstyles import load_preset, resolve_game_keyterms

from ..config import ServerSettings
from ..pools.api_pool import ApiPool
from ..pools.cpu_pool import (
    CpuPool,
    worker_build_editplan,
    worker_compute_signals,
    worker_prepare_media,
    worker_track_face,
)
from ..pools.render_pool import RenderPool
from .cleanup import cleanup_temp_media
from .db import OrchestratorDB, stable_hash
from .events import EventHub

SLUG_RE = re.compile(r"[^a-z0-9_-]+")


def _clip_slug(rank: int, clip_id: str) -> str:
    return f"clip_{rank:02d}_{SLUG_RE.sub('_', clip_id.lower())}"


def _file_sig(path_str: str) -> Dict[str, Any]:
    p = Path(path_str)
    st = p.stat()
    return {"path": str(p.resolve()), "size": st.st_size, "mtime_ns": st.st_mtime_ns}


class Orchestrator:
    def __init__(
        self,
        settings: ServerSettings,
        use_process_pool: bool = True,
        require_two_drive_polls: bool = True,
    ) -> None:
        self.settings = settings
        self.settings.data_dir.mkdir(parents=True, exist_ok=True)
        self.db = OrchestratorDB(self.settings.data_dir / "clipsapp.db")
        self.events = EventHub()

        self.api_pool = ApiPool(settings, self.db)
        self.cpu_pool = CpuPool(max_workers=settings.cpu_workers, use_processes=use_process_pool)
        self.render_pool = RenderPool(
            use_nvenc=settings.use_nvenc,
            nvenc_slots=settings.nvenc_slots,
            cache_dir=settings.data_dir / "render_cache",
        )
        self._require_two_drive_polls = require_two_drive_polls
        self.drive: Optional[DriveConnector] = self._init_drive(require_two_drive_polls)
        self.resolve_bridge: ResolveMcpBridge = self._init_resolve_bridge()

        self._running_sessions: Dict[str, asyncio.Task] = {}
        self._drive_watcher_task: Optional[asyncio.Task] = None

    def _init_resolve_bridge(self) -> ResolveMcpBridge:
        return ResolveMcpBridge(
            mode=self.settings.resolve_mcp_mode,  # type: ignore[arg-type]
            mcp_command=self.settings.resolve_mcp_command,
            mcp_url=self.settings.resolve_mcp_url,
            project_prefix=self.settings.resolve_project_prefix,
        )

    def reload_settings(self, new_settings: ServerSettings) -> None:
        """Hot-reload in-memory ServerSettings across Orchestrator, ApiPool, DriveConnector and ResolveMcpBridge."""
        self.settings = new_settings
        self.api_pool.reload_settings(new_settings)
        self.drive = self._init_drive(self._require_two_drive_polls)
        self.resolve_bridge = self._init_resolve_bridge()

    def _init_drive(self, require_two_polls: bool) -> Optional[DriveConnector]:
        mode = self.settings.drive_mode
        if mode == "disabled":
            return None
        if mode == "oauth":
            return GoogleDriveOAuthConnector(
                client_id=self.settings.drive_client_id,
                client_secret=self.settings.drive_client_secret,
                token_path=self.settings.drive_oauth_token_path,
                root_folder_id=self.settings.drive_root_folder_id or "root",
            )
        if (
            mode == "service_account"
            and self.settings.drive_service_account_json
            and self.settings.drive_root_folder_id
        ):
            return GoogleDriveServiceAccountConnector(
                service_account_json=self.settings.drive_service_account_json,
                root_folder_id=self.settings.drive_root_folder_id,
            )
        return LocalFolderDriveConnector(
            root_dir=self.settings.drive_local_dir,
            require_two_polls=require_two_polls,
        )

    def session_dir(self, session_id: str) -> Path:
        d = self.settings.data_dir / "sessions" / session_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    async def startup(self, enable_watcher: bool = True) -> None:
        recovered = self.db.recover_expired_leases()
        if recovered:
            self.events.publish("leases_recovered", count=recovered)
        if self.settings.temp_ttl_days >= 0:
            sweep = cleanup_temp_media(
                self.settings.data_dir,
                self.db,
                ttl_days=self.settings.temp_ttl_days,
            )
            if sweep["purged_files"] > 0:
                self.events.publish("maintenance_cleanup", **sweep)
        for row in self.db.sessions_to_resume():
            if row.get("gameplay_path") and row.get("camera_path"):
                self.launch_session(row["id"])
        if enable_watcher and self.drive is not None and self.settings.drive_poll_sec > 0:
            self._drive_watcher_task = asyncio.create_task(self._drive_poll_loop(), name="drive-watcher")

    async def shutdown(self) -> None:
        if self._drive_watcher_task:
            self._drive_watcher_task.cancel()
            await asyncio.gather(self._drive_watcher_task, return_exceptions=True)
        for t in list(self._running_sessions.values()):
            t.cancel()
        if self._running_sessions:
            await asyncio.gather(*self._running_sessions.values(), return_exceptions=True)
        self._running_sessions.clear()
        await self.render_pool.shutdown()
        await self.api_pool.aclose()
        self.cpu_pool.shutdown()
        self.db.close()

    # --- Google Drive Poller & Streaming Ingestion -------------------------

    async def _drive_poll_loop(self) -> None:
        while True:
            try:
                await self.poll_drive_once()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.events.publish("drive_error", message=str(exc))
            await asyncio.sleep(max(5.0, self.settings.drive_poll_sec))

    async def poll_drive_once(self) -> List[str]:
        if self.drive is None:
            return []
        if isinstance(self.drive, GoogleDriveOAuthConnector) and not self.drive.is_connected():
            return []
        ready = await self.drive.list_ready_recordings()
        launched_ids: List[str] = []
        for rec in ready:
            existing = self.db.find_session_by_drive_folder(rec.folder_id)
            if existing is not None:
                continue
            ses = self.db.create_session(
                title=rec.recording_name,
                recording_name=rec.recording_name,
                drive_folder_id=rec.folder_id,
                style_preset=self.settings.style_preset,
                initial_state=SessionState.NEW,
            )
            sid = ses["id"]
            sdir = self.session_dir(sid) / "inputs"

            gp_ext = Path(rec.gameplay_file.name).suffix or ".mp4"
            cam_ext = Path(rec.camera_file.name).suffix or ".mp4"
            gp_dst = sdir / f"gameplay{gp_ext}"
            cam_dst = sdir / f"camara{cam_ext}"

            self.events.publish("session_state", session_id=sid, state="NEW", message="Descargando desde Drive…")
            gp_local, cam_local = await asyncio.gather(
                self.api_pool.run_download(lambda r=rec, d=gp_dst: self.drive.download_resumable(r.gameplay_file, d)),  # type: ignore[union-attr]
                self.api_pool.run_download(lambda r=rec, d=cam_dst: self.drive.download_resumable(r.camera_file, d)),  # type: ignore[union-attr]
            )
            self.db.update_session(
                sid,
                gameplay_path=str(gp_local.resolve()),
                camera_path=str(cam_local.resolve()),
                state=SessionState.DOWNLOADED.value,
            )
            self.events.publish("session_state", session_id=sid, state="DOWNLOADED", message="Grabación descargada")
            self.launch_session(sid)
            launched_ids.append(sid)
        return launched_ids

    async def create_session_from_drive(
        self,
        gameplay_file_id: Optional[str] = None,
        camera_file_id: Optional[str] = None,
        folder_id: Optional[str] = None,
        title: str = "",
        recording_name: str = "",
        language: str = "es",
        style_preset: Optional[str] = None,
        auto_start: bool = True,
    ) -> Dict[str, Any]:
        if self.drive is None:
            raise RuntimeError("El conector de Google Drive está deshabilitado.")
        if isinstance(self.drive, GoogleDriveOAuthConnector) and not self.drive.is_connected():
            raise RuntimeError("Google Drive OAuth 2.0 no está vinculado. Conecta tu cuenta en Configuración.")

        gp_id = (gameplay_file_id or "").strip()
        cam_id = (camera_file_id or "").strip()
        inferred_rec_name = ""

        if not gp_id or not cam_id:
            browsed = await self.drive.browse_folder(folder_id=folder_id)
            pair = browsed.get("detected_pair")
            if not pair:
                raise ValueError(
                    "Selecciona los archivos de gameplay y cámara o una carpeta que contenga ambos videos."
                )
            gp_id = str(pair["gameplay"]["id"])
            cam_id = str(pair["camera"]["id"])
            inferred_rec_name = str(pair.get("recording_name") or browsed.get("folder_name") or "")

        gp_entry, cam_entry = await asyncio.gather(
            self.drive.get_file_entry(gp_id),
            self.drive.get_file_entry(cam_id),
        )

        rec_name = (
            recording_name.strip()
            or title.strip()
            or inferred_rec_name
            or Path(gp_entry.name).stem
        )
        ses_title = title.strip() or rec_name

        ses = self.db.create_session(
            title=ses_title,
            recording_name=rec_name,
            drive_folder_id=(folder_id or "").strip() or gp_entry.id,
            language=language or "es",
            style_preset=style_preset or self.settings.style_preset,
            initial_state=SessionState.NEW,
        )
        sid = ses["id"]
        sdir = self.session_dir(sid) / "inputs"

        gp_ext = Path(gp_entry.name).suffix or ".mp4"
        cam_ext = Path(cam_entry.name).suffix or ".mp4"
        gp_dst = sdir / f"gameplay{gp_ext}"
        cam_dst = sdir / f"camara{cam_ext}"

        dl_msg = f"Descargando {gp_entry.name} y {cam_entry.name} desde Drive…"
        self.events.publish("session_state", session_id=sid, state="NEW", message=dl_msg)
        self.events.publish("stage_progress", session_id=sid, stage="download", progress=0.02, message=dl_msg)

        try:
            gp_local, cam_local = await asyncio.gather(
                self.api_pool.run_download(lambda e=gp_entry, d=gp_dst: self.drive.download_resumable(e, d)),  # type: ignore[union-attr]
                self.api_pool.run_download(lambda e=cam_entry, d=cam_dst: self.drive.download_resumable(e, d)),  # type: ignore[union-attr]
            )
        except Exception as exc:
            self._set_state(sid, SessionState.FAILED, message="Error descargando desde Drive", error=str(exc))
            raise

        self.db.update_session(
            sid,
            gameplay_path=str(gp_local.resolve()),
            camera_path=str(cam_local.resolve()),
            state=SessionState.DOWNLOADED.value,
        )
        self.events.publish("session_state", session_id=sid, state="DOWNLOADED", message="Grabación descargada")
        if auto_start:
            self.launch_session(sid)
        return self.db.get_session(sid) or ses

    # --- Session Execution -------------------------------------------------

    def launch_session(self, session_id: str) -> asyncio.Task:
        existing = self._running_sessions.get(session_id)
        if existing and not existing.done():
            return existing
        task = asyncio.create_task(self.run_session(session_id), name=f"session-{session_id}")
        self._running_sessions[session_id] = task
        return task

    async def cancel_session(self, session_id: str) -> None:
        t = self._running_sessions.get(session_id)
        if t and not t.done():
            t.cancel()
            await asyncio.gather(t, return_exceptions=True)
        self.db.update_session(session_id, state=SessionState.CANCELLED.value)
        self.events.publish("session_state", session_id=session_id, state="CANCELLED", message="Sesión cancelada")

    def _set_state(self, session_id: str, state: SessionState, message: str = "", error: Optional[str] = None) -> None:
        self.db.update_session(session_id, state=state.value, error=error)
        self.events.publish("session_state", session_id=session_id, state=state.value, message=message, error=error)

    async def _run_cached_cpu(
        self,
        session_id: str,
        kind: str,
        hash_payload: Dict[str, Any],
        expected_out: Path,
        worker_fn,
        *args: Any,
        clip_id: Optional[str] = None,
    ) -> Path:
        hkey = stable_hash({"kind": kind, **hash_payload})
        cached = self.db.get_artifact_path(hkey)
        if cached is not None:
            return cached
        tid = self.db.start_task(session_id, kind, hkey, clip_id=clip_id)
        try:
            await self.cpu_pool.run(worker_fn, *args)
        except Exception as exc:
            self.db.finish_task(tid, state="FAILED", error=str(exc))
            raise
        self.db.put_artifact(hkey, kind, expected_out)
        self.db.finish_task(tid, state="DONE")
        return expected_out

    async def run_session(self, session_id: str) -> None:
        row = self.db.get_session(session_id)
        if row is None:
            return
        sdir = self.session_dir(session_id)
        preset = load_preset(row.get("style_preset") or self.settings.style_preset)
        gp_path = row.get("gameplay_path")
        cam_path = row.get("camera_path")
        if not gp_path or not cam_path:
            self._set_state(session_id, SessionState.FAILED, error="Faltan rutas de gameplay o cámara.")
            return

        try:
            # 1. PREPARAR (CPU Pool): Opus chunks, 16kHz WAVs, audio xcorr sync
            self.events.publish("stage_progress", session_id=session_id, stage="prepare", progress=0.05, message="Alineando el audio de tu cámara con el del juego…")
            parsed_sync = json.loads(row["sync_json"]) if row.get("sync_json") else None
            manual_sync_dict = parsed_sync if (parsed_sync and parsed_sync.get("method") == "manual") else None
            if row.get("prepared_json") and (not Path(gp_path).is_file() or not Path(cam_path).is_file()):
                prep = PreparedMedia.model_validate_json(row["prepared_json"])
            else:
                prep_hash = stable_hash(
                    {
                        "kind": "prepare_media",
                        "gp": _file_sig(gp_path),
                        "cam": _file_sig(cam_path),
                        "manual_sync": manual_sync_dict,
                        "chunk_sec": self.settings.chunk_target_sec,
                    }
                )
                prep_file = sdir / f"prepared_{prep_hash[:12]}.json"
                cached_prep = self.db.get_artifact_path(prep_hash)
                if cached_prep is not None:
                    prep = PreparedMedia.model_validate_json(cached_prep.read_text(encoding="utf-8"))
                else:
                    tid = self.db.start_task(session_id, "prepare_media", prep_hash, lease_sec=600.0)
                    try:
                        prep_dict = await self.cpu_pool.run(
                            worker_prepare_media,
                            session_id,
                            gp_path,
                            cam_path,
                            str(sdir / "media"),
                            manual_sync_dict,
                            self.settings.chunk_target_sec,
                        )
                    except Exception as exc:
                        self.db.finish_task(tid, state="FAILED", error=str(exc))
                        raise
                    prep = PreparedMedia.model_validate(prep_dict)
                    prep_file.write_text(prep.model_dump_json(indent=2), encoding="utf-8")
                    self.db.put_artifact(prep_hash, "prepare_media", prep_file)
                    self.db.finish_task(tid, state="DONE")

            self.db.update_session(
                session_id,
                sync_json=prep.sync.model_dump_json(),
                prepared_json=prep.model_dump_json(),
            )
            self._set_state(session_id, SessionState.PREPARED, message="Audio y video sincronizados")

            # 2a & 2b IN PARALLEL: Transcribe Opus chunks (API Pool) + Compute Signals in Parquet (CPU Pool)
            async def _transcribe_all() -> List[Utterance]:
                detected_game, keyterms = resolve_game_keyterms(
                    title=str(row.get("title") or ""),
                    recording_name=str(row.get("recording_name") or ""),
                    base_keyterms=self.settings.default_keyterms,
                )
                if detected_game:
                    self.events.publish(
                        "game_detected",
                        session_id=session_id,
                        game_id=detected_game,
                        keyterms_count=len(keyterms),
                    )
                utts_file = sdir / "utterances.json"
                # If intermediate Opus files were purged by TTL cleanup and utterances.json exists without chunk sha256
                if utts_file.is_file() and any(not ch.sha256 and not Path(ch.path).is_file() for ch in prep.chunks):
                    raw_utts = json.loads(utts_file.read_text(encoding="utf-8"))
                    return [Utterance.model_validate(u) for u in raw_utts]

                chunk_lists = await asyncio.gather(
                    *(
                        self.api_pool.transcribe_chunk_cached(
                            session_id=session_id,
                            chunk=ch,
                            sync=prep.sync,
                            language=row.get("language") or "es",
                            keyterms=keyterms,
                            silences=[],
                            chunks_work_dir=sdir / "media" / "opus_chunks",
                        )
                        for ch in prep.chunks
                    )
                )
                all_words: List[TranscriptWord] = []
                for cw in chunk_lists:
                    all_words.extend(cw)
                all_words.sort(key=lambda w: (w.start, w.end))
                utts = group_words_into_utterances(all_words)
                utts_file.write_text(
                    json.dumps([u.model_dump(mode="json") for u in utts], ensure_ascii=False, indent=1),
                    encoding="utf-8",
                )
                return utts

            async def _compute_signals() -> Path:
                sig_out = sdir / "signals.parquet"
                if sig_out.is_file() and (
                    not Path(prep.camera_wav16k).is_file() or not Path(prep.gameplay_wav16k).is_file()
                ):
                    return sig_out
                return await self._run_cached_cpu(
                    session_id,
                    "compute_signals",
                    {
                        "cam_wav": _file_sig(prep.camera_wav16k),
                        "game_wav": _file_sig(prep.gameplay_wav16k),
                        "sync": prep.sync.model_dump(mode="json"),
                        "motion": self.settings.enable_gameplay_motion,
                    },
                    sig_out,
                    worker_compute_signals,
                    prep.gameplay.duration,
                    prep.camera_wav16k,
                    prep.gameplay_wav16k,
                    prep.sync.shift_sec,
                    prep.sync.scale,
                    prep.gameplay.path if self.settings.enable_gameplay_motion else None,
                    self.settings.enable_gameplay_motion,
                    str(sig_out),
                )

            self.events.publish("stage_progress", session_id=session_id, stage="transcribe_signals", progress=0.25, message="Escuchando lo que dices y detectando los momentos de mayor emoción…")
            utterances, signals_parquet = await asyncio.gather(_transcribe_all(), _compute_signals())
            signals = SignalSeries.from_parquet(signals_parquet)
            self.events.publish(
                "budget_update",
                session_id=session_id,
                **self.db.budget_summary(self.settings.max_budget_usd),
            )
            self._set_state(session_id, SessionState.TRANSCRIBED, message=f"{len(utterances)} frases detectadas")

            # 3 & 4. TIMELINE + CURAR CON LLM (API Pool)
            self.events.publish("stage_progress", session_id=session_id, stage="curate", progress=0.55, message="Eligiendo las mejores jugadas y momentos divertidos…")
            windows = build_timeline_windows_if_needed(utterances, signals)
            window_proposals = await asyncio.gather(
                *(
                    self.api_pool.curate_window_cached(
                        session_id=session_id,
                        timeline_text=w_txt,
                        title=row.get("title") or "Stream",
                        min_len=preset.duration.min_sec,
                        max_len=preset.duration.max_sec,
                    )
                    for w_txt in windows
                )
            )
            flat_proposals: List[Dict[str, Any]] = [item for sub in window_proposals for item in sub]
            curated_clips = resolve_curated_clips(
                llm_clips=flat_proposals,
                utterances=utterances,
                signals=signals,
                vod_duration=prep.gameplay.duration,
                min_sec=preset.duration.min_sec,
                max_sec=preset.duration.max_sec,
            )
            self.events.publish(
                "budget_update",
                session_id=session_id,
                **self.db.budget_summary(self.settings.max_budget_usd),
            )

            # Persist curated clips in deterministic rank order; reuse stable IDs if re-running same session
            existing_by_span = {
                (round(c["start_sec"], 1), round(c["end_sec"], 1)): c["id"]
                for c in self.db.list_clips(session_id)
            }
            for rank_idx, clip in enumerate(curated_clips, start=1):
                reused_id = existing_by_span.get((round(clip.start, 1), round(clip.end, 1)))
                if reused_id:
                    clip.id = reused_id
                self.db.upsert_clip(
                    clip_id=clip.id,
                    session_id=session_id,
                    rank_order=rank_idx,
                    start_sec=clip.start,
                    end_sec=clip.end,
                    overlay_title=clip.overlay_title,
                    post_title=clip.post_title,
                    hashtags=clip.hashtags,
                    reason=clip.reason,
                    llm_score=clip.llm_score,
                    signal_score=clip.signal_score,
                    final_score=clip.final_score,
                    curated_json=clip.model_dump_json(),
                    state="CURATED",
                )
            self.db.delete_stale_session_clips(session_id, [c.id for c in curated_clips])

            self._set_state(session_id, SessionState.CURATED, message=f"{len(curated_clips)} momentos seleccionados")

            # Identify top-5 clips > 60/100 for automatic 1080p render & Drive delivery
            auto_render_ids = {
                c.id
                for c in curated_clips
                if c.final_score >= self.settings.auto_render_min_score
            }
            top_ordered = [c.id for c in curated_clips if c.id in auto_render_ids][: self.settings.auto_render_top_k]
            auto_render_set = set(top_ordered)

            self._set_state(session_id, SessionState.PLANNING, message="Centrando tu cámara y preparando los subtítulos de cada clip…")

            # 5, 6, 7. INDEPENDENT PER-CLIP PIPELINE IN PARALLEL (TaskGroup)
            utts_dicts = [u.model_dump(mode="json") for u in utterances]
            silences_dicts = [s.model_dump(mode="json") for s in prep.speech_silences_master]
            sync_dict = prep.sync.model_dump(mode="json")

            async with asyncio.TaskGroup() as tg:
                for rank_idx, clip in enumerate(curated_clips, start=1):
                    tg.create_task(
                        self._clip_pipeline(
                            session_row=row,
                            prep=prep,
                            clip=clip,
                            rank_idx=rank_idx,
                            utts_dicts=utts_dicts,
                            signals_parquet=signals_parquet,
                            silences_dicts=silences_dicts,
                            sync_dict=sync_dict,
                            preset_id=preset.id,
                            preset_hash=preset.content_hash(),
                            should_auto_render=(clip.id in auto_render_set),
                        )
                    )

            self._set_state(session_id, SessionState.DELIVERED, message="¡Listo! Tus clips ya están disponibles")
            if self.settings.webhook_url:
                try:
                    wh_res = await send_delivery_webhook(
                        webhook_url=self.settings.webhook_url,
                        session_id=session_id,
                        title=str(row.get("title") or row.get("recording_name") or session_id),
                        clips=self.db.list_clips(session_id),
                        public_web_url=self.settings.public_web_url,
                    )
                    self.events.publish("webhook_sent", session_id=session_id, **wh_res)
                except Exception as wh_exc:
                    self.events.publish("webhook_error", session_id=session_id, message=str(wh_exc))
        except asyncio.CancelledError:
            self._set_state(session_id, SessionState.CANCELLED, message="Sesión cancelada")
            raise
        except Exception as exc:
            self._set_state(session_id, SessionState.FAILED, message="Error en pipeline", error=f"{type(exc).__name__}: {exc}")
            raise

    async def _clip_pipeline(
        self,
        session_row: Dict[str, Any],
        prep: PreparedMedia,
        clip: CuratedClip,
        rank_idx: int,
        utts_dicts: List[Dict[str, Any]],
        signals_parquet: Path,
        silences_dicts: List[Dict[str, Any]],
        sync_dict: Dict[str, Any],
        preset_id: str,
        preset_hash: str,
        should_auto_render: bool,
    ) -> None:
        sid = session_row["id"]
        cdir = self.session_dir(sid) / "clips" / clip.id
        cdir.mkdir(parents=True, exist_ok=True)

        # Step 5: MediaPipe Face Tracking ONLY on clip.padded_range (2s margin)
        pad_a, pad_b = clip.padded_range(margin_sec=2.0, max_duration=prep.gameplay.duration)
        face_parquet = cdir / "face.parquet"
        if not (face_parquet.is_file() and not Path(prep.camera.path).is_file()):
            await self._run_cached_cpu(
                sid,
                "track_face",
                {
                    "cam": _file_sig(prep.camera.path),
                    "range": [pad_a, pad_b],
                    "sync": sync_dict,
                },
                face_parquet,
                worker_track_face,
                prep.camera.path,
                pad_a,
                pad_b,
                sync_dict,
                str(face_parquet),
                clip_id=clip.id,
            )

        # Step 6: Build declarative EditPlan v2 (re-runs cheaply if preset changes without touching STT/LLM/Face!)
        existing_clip_row = self.db.get_clip(clip.id)
        plan_file = cdir / "editplan.json"
        await self._run_cached_cpu(
            sid,
            "build_editplan",
            {
                "clip": clip.model_dump(mode="json"),
                "preset_id": preset_id,
                "preset_hash": preset_hash,
                "sync": sync_dict,
            },
            plan_file,
            worker_build_editplan,
            sid,
            clip.model_dump(mode="json"),
            utts_dicts,
            str(signals_parquet),
            str(face_parquet),
            preset_id,
            silences_dicts,
            prep.camera_wav16k,
            sync_dict,
            prep.gameplay.fps,
            str(plan_file),
            clip_id=clip.id,
        )

        # Preserve manual user edits if user already customized editplan in editor
        if existing_clip_row and existing_clip_row.get("editplan_json") and existing_clip_row.get("state") == "EDITED":
            plan = EditPlan.model_validate_json(existing_clip_row["editplan_json"])
        else:
            plan = EditPlan.model_validate_json(plan_file.read_text(encoding="utf-8"))
            self.db.update_clip(clip.id, editplan_json=plan.model_dump_json(exclude_none=True), state="PLANNED")

        self.events.publish("clip_updated", session_id=sid, clip_id=clip.id, state="PLANNED")

        # Step 7: Automatic 1080p render / DaVinci Resolve MCP export for top-K (> min_score)
        if should_auto_render:
            self.db.update_session(sid, state=SessionState.RENDERING.value)
            if self.settings.editor_backend in ("resolve_mcp", "both") or self.settings.resolve_auto_export:
                await self.export_clip_to_resolve(
                    clip_id=clip.id,
                    open_in_resolve=True,
                    trigger_render=False,
                )
            if self.settings.editor_backend in ("local", "both"):
                await self.render_and_deliver_clip(
                    clip_id=clip.id,
                    quality="final",
                    priority=clip.final_score,
                    upload_to_drive=True,
                )

    def get_resolve_status(self) -> Dict[str, Any]:
        return detect_resolve_environment(
            editor_backend=self.settings.editor_backend,
            mcp_mode=self.settings.resolve_mcp_mode,
            mcp_command=self.settings.resolve_mcp_command,
            mcp_url=self.settings.resolve_mcp_url,
        )

    async def export_clip_to_resolve(
        self,
        clip_id: str,
        open_in_resolve: bool = True,
        trigger_render: bool = False,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        clip_row = self.db.get_clip(clip_id)
        if clip_row is None:
            raise KeyError(f"Clip {clip_id} no existe")
        sid = clip_row["session_id"]
        ses_row = self.db.get_session(sid)
        if ses_row is None or not ses_row.get("prepared_json"):
            raise RuntimeError("La sesión aún no está preparada para exportar a DaVinci Resolve.")
        if not clip_row.get("editplan_json"):
            raise RuntimeError("El clip aún no tiene EditPlan generado.")

        prep = PreparedMedia.model_validate_json(ses_row["prepared_json"])
        plan = EditPlan.model_validate_json(clip_row["editplan_json"])
        preset = load_preset(plan.output.style or ses_row.get("style_preset") or self.settings.style_preset)

        resolve_dir = self.session_dir(sid) / "clips" / clip_id / "resolve"

        def _on_prog(frac: float, msg: str) -> None:
            self.events.publish(
                "resolve_mcp_progress",
                session_id=sid,
                clip_id=clip_id,
                progress=round(frac, 3),
                message=msg,
            )

        res = await self.resolve_bridge.export_clip_to_resolve(
            plan=plan,
            preset=preset,
            gameplay_path=Path(prep.gameplay.path),
            camera_path=Path(prep.camera.path),
            sync=prep.sync,
            out_dir=resolve_dir,
            session_id=sid,
            session_title=str(ses_row.get("title") or ses_row.get("recording_name") or sid),
            clip_rank=int(clip_row.get("rank_order") or 1),
            clip_reason=str(clip_row.get("reason") or ""),
            open_in_resolve=open_in_resolve,
            trigger_render=trigger_render,
            project_name_override=project_name,
            on_progress=_on_prog,
        )

        self.events.publish(
            "clip_resolve_exported",
            session_id=sid,
            clip_id=clip_id,
            project_name=res["project_name"],
            timeline_name=res["timeline_name"],
            connected_to_resolve=res["connected_to_resolve"],
            mode_used=res["mode_used"],
        )
        return res

    async def export_session_to_resolve(
        self,
        session_id: str,
        top_k: Optional[int] = None,
        open_in_resolve: bool = True,
        trigger_render: bool = False,
        project_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        ses_row = self.db.get_session(session_id)
        if ses_row is None:
            raise KeyError(f"Sesión {session_id} no existe")
        clips = self.db.list_clips(session_id)
        if top_k is not None and top_k > 0:
            clips = clips[:top_k]

        exported: List[Dict[str, Any]] = []
        for c in clips:
            if not c.get("editplan_json"):
                continue
            item = await self.export_clip_to_resolve(
                clip_id=c["id"],
                open_in_resolve=open_in_resolve,
                trigger_render=trigger_render,
                project_name=project_name,
            )
            exported.append(item)

        proj_name = (
            exported[0]["project_name"]
            if exported
            else (project_name or f"{self.settings.resolve_project_prefix} - {ses_row.get('title') or session_id}")
        )
        return {
            "ok": True,
            "session_id": session_id,
            "project_name": proj_name,
            "exported_count": len(exported),
            "clips": exported,
        }

    async def save_clip_editplan(self, clip_id: str, plan: EditPlan) -> EditPlan:
        row = self.db.get_clip(clip_id)
        if row is None:
            raise KeyError(f"Clip {clip_id} no existe")
        plan.clip_id = clip_id
        cdir = self.session_dir(row["session_id"]) / "clips" / clip_id
        cdir.mkdir(parents=True, exist_ok=True)
        raw_json = plan.model_dump_json(indent=2, exclude_none=True)
        (cdir / "editplan.user.json").write_text(raw_json + "\n", encoding="utf-8")
        self.db.update_clip(clip_id, editplan_json=raw_json, state="EDITED")
        self.events.publish("clip_updated", session_id=row["session_id"], clip_id=clip_id, state="EDITED")
        return plan

    async def render_and_deliver_clip(
        self,
        clip_id: str,
        quality: RenderQuality = "final",
        priority: float = 1000.0,
        upload_to_drive: bool = True,
    ) -> Path:
        clip_row = self.db.get_clip(clip_id)
        if clip_row is None:
            raise KeyError(f"Clip {clip_id} no existe")
        sid = clip_row["session_id"]
        ses_row = self.db.get_session(sid)
        if ses_row is None or not ses_row.get("prepared_json"):
            raise RuntimeError("La sesión aún no está preparada para renderizar.")
        if not clip_row.get("editplan_json"):
            raise RuntimeError("El clip aún no tiene EditPlan generado.")

        prep = PreparedMedia.model_validate_json(ses_row["prepared_json"])
        plan = EditPlan.model_validate_json(clip_row["editplan_json"])
        preset = load_preset(plan.output.style or ses_row.get("style_preset") or self.settings.style_preset)

        out_dir = self.session_dir(sid) / "renders"
        self.db.update_clip(clip_id, state=f"RENDERING_{quality.upper()}")
        self.events.publish("render_progress", session_id=sid, clip_id=clip_id, quality=quality, progress=0.01, message="En cola de render…")

        def _on_prog(frac: float, msg: str) -> None:
            self.events.publish(
                "render_progress",
                session_id=sid,
                clip_id=clip_id,
                quality=quality,
                progress=round(frac, 3),
                message=msg,
            )

        mp4_path = await self.render_pool.submit(
            plan=plan,
            preset=preset,
            gameplay_path=Path(prep.gameplay.path),
            camera_path=Path(prep.camera.path),
            sync=prep.sync,
            out_dir=out_dir,
            quality=quality,
            priority=priority,
            clean_game_audio_stream=prep.gameplay_clean_audio_stream,
            on_progress=_on_prog,
        )

        field_key = "draft_mp4_path" if quality == "draft" else "final_mp4_path"
        new_state = "DRAFT_READY" if quality == "draft" else "RENDERED"
        self.db.update_clip(clip_id, **{field_key: str(mp4_path.resolve()), "state": new_state})

        # Upload or replace in Salidas/<grabación>/ when rendering 1080p final
        can_upload_drive = (
            quality == "final"
            and upload_to_drive
            and self.drive is not None
            and not (isinstance(self.drive, GoogleDriveOAuthConnector) and not self.drive.is_connected())
        )
        if can_upload_drive and self.drive is not None:
            rec_name = ses_row.get("recording_name") or ses_row.get("title") or sid
            slug = _clip_slug(int(clip_row.get("rank_order") or 1), clip_id)
            overlay_title = plan.overlays[0].text if plan.overlays else clip_row["overlay_title"]
            metadata = {
                "clip_id": clip_id,
                "session_id": sid,
                "post_title": clip_row["post_title"],
                "overlay_title": overlay_title,
                "hashtags": json.loads(clip_row.get("hashtags_json") or "[]"),
                "source_ranges": [list(r) for r in plan.source.ranges],
                "score": clip_row["final_score"],
                "llm_score": clip_row["llm_score"],
                "signal_score": clip_row["signal_score"],
                "reason": clip_row["reason"],
                "style": preset.id,
            }
            delivered = await self.drive.upload_clip_bundle(rec_name, slug, mp4_path, metadata)
            self.db.update_clip(
                clip_id,
                drive_salidas_json=json.dumps(delivered, ensure_ascii=False),
                state="DELIVERED",
            )
            self.events.publish("clip_updated", session_id=sid, clip_id=clip_id, state="DELIVERED", salidas=delivered)
        else:
            self.events.publish("clip_updated", session_id=sid, clip_id=clip_id, state=new_state)

        return mp4_path
