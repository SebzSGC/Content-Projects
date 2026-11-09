"""End-to-end golden pipeline test: Drive Entradas -> size stability -> Sync -> Parallel STT+Signals -> LLM -> MediaPipe Face Parquet -> EditPlan v2 -> 1080p Render -> Salidas -> Cache Idempotency -> Editor 540p/1080p Re-export."""

from __future__ import annotations

import asyncio
import json
import shutil
import time
from pathlib import Path

import httpx
from clipsmedia.ffmpeg import probe
from clipsserver.api import create_app
from clipsserver.config import ServerSettings

ROOT_DIR = Path(__file__).resolve().parents[1]
GOLDEN_DIR = ROOT_DIR / "tests" / "golden"
FIXTURES_DIR = ROOT_DIR / "tests" / "fixtures" / "api"


async def test_full_golden_hybrid_pipeline_and_editor_cycle(tmp_path: Path) -> None:
    gp_src = GOLDEN_DIR / "gameplay.mp4"
    cam_src = GOLDEN_DIR / "camara.mp4"
    assert gp_src.is_file() and cam_src.is_file(), "Golden reference videos must exist"

    drive_root = tmp_path / "drive_mirror"
    rec_in = drive_root / "Entradas" / "sesion_torneo_01"
    rec_in.mkdir(parents=True, exist_ok=True)
    shutil.copy2(gp_src, rec_in / "gameplay.mp4")
    shutil.copy2(cam_src, rec_in / "camara.mp4")

    settings = ServerSettings(
        data_dir=tmp_path / "data",
        stt_primary="fixture",
        stt_backup="fixture",
        llm_primary="fixture",
        llm_backup="fixture",
        fixtures_dir=FIXTURES_DIR,
        drive_mode="local",
        drive_local_dir=drive_root,
        drive_poll_sec=0.0,  # Trigger manually in test
        use_nvenc=True,
        nvenc_slots=2,
        cpu_workers=2,
        max_budget_usd=9.0,
    )

    # Use thread-backed CpuPool inside pytest for fast deterministic execution while testing real FFmpeg + MediaPipe + SQLite
    app = create_app(settings=settings, use_process_pool=False, enable_drive_watcher=False)
    orch = app.state.orchestrator
    await orch.startup(enable_watcher=False)

    # Record the silences the pipeline hands to the STT pool (they drive the AFK filter and speech-only upload)
    stt_silences_seen: list = []
    original_transcribe = orch.api_pool.transcribe_chunk_cached

    async def _spy_transcribe(*args, **kwargs):
        stt_silences_seen.append(list(kwargs.get("silences") or []))
        return await original_transcribe(*args, **kwargs)

    orch.api_pool.transcribe_chunk_cached = _spy_transcribe

    try:
        # 1. Verify crash-recovery lease expiration logic
        dummy_ses = orch.db.create_session(title="Crash Lease Check")
        tid = orch.db.start_task(dummy_ses["id"], "prepare_media", "hash_crash_test", lease_sec=60.0)
        # Force lease_until into the past to simulate process crash
        orch.db._conn.execute("UPDATE tasks SET lease_until = ? WHERE id = ?", (time.time() - 10.0, tid))
        orch.db._conn.commit()
        recovered_count = orch.db.recover_expired_leases()
        assert recovered_count == 1

        # 2. First Drive poll records initial file sizes -> returns 0 sessions (protects half-uploaded OBS files!)
        first_poll = await orch.poll_drive_once()
        assert first_poll == []

        # 3. Second Drive poll sees stable file sizes -> downloads & launches full 7-step session!
        second_poll = await orch.poll_drive_once()
        assert len(second_poll) == 1
        sid = second_poll[0]

        # Wait for background session pipeline task to complete
        ses_task = orch._running_sessions[sid]
        await asyncio.wait_for(ses_task, timeout=180.0)
        assert stt_silences_seen and any(stt_silences_seen), "El STT debe recibir los silencios de la cámara"

        ses_row = orch.db.get_session(sid)
        assert ses_row is not None
        assert ses_row["state"] == "DELIVERED", f"Unexpected state: {ses_row}"

        # Verify audio xcorr recovered ~ +0.40s shift and multi-track clean game audio stream 1
        sync_info = json.loads(ses_row["sync_json"])
        assert sync_info["method"] == "audio_xcorr"
        assert abs(sync_info["shift_sec"] - 0.40) <= 0.08
        prep_info = json.loads(ses_row["prepared_json"])
        assert prep_info["gameplay_clean_audio_stream"] == 1

        # Verify Parquet artifacts exist for signals & per-clip MediaPipe face trajectory
        sdir = orch.session_dir(sid)
        assert (sdir / "signals.parquet").is_file()
        clips = orch.db.list_clips(sid)
        assert len(clips) == 1
        clip_row = clips[0]
        cid = clip_row["id"]
        assert clip_row["final_score"] > 60.0
        assert (sdir / "clips" / cid / "face.parquet").is_file()

        # Verify EditPlan v2 jump cuts removed the 1.35s silence gap (>1 range in source.ranges)
        plan_dict = json.loads(clip_row["editplan_json"])
        assert plan_dict["version"] == 2
        assert len(plan_dict["source"]["ranges"]) >= 2
        assert len(plan_dict["captions"]["groups"]) >= 10

        # Verify 1080p MP4 + metadata JSON delivered into Salidas/sesion_torneo_01/
        salidas_dir = drive_root / "Salidas" / "sesion_torneo_01"
        salidas_mp4s = list(salidas_dir.glob("*.mp4"))
        salidas_jsons = list(salidas_dir.glob("*.json"))
        assert len(salidas_mp4s) == 1
        assert len(salidas_jsons) == 1

        mp4_meta = probe(salidas_mp4s[0])
        assert mp4_meta.width == 1080
        assert mp4_meta.height == 1920
        assert mp4_meta.has_audio is True
        assert 20.0 <= mp4_meta.duration <= 40.0

        # 4. Principle #4 ("Never pay twice"): re-run session and verify ZERO new API calls!
        calls_before = orch.db.budget_summary(settings.max_budget_usd)["calls_count"]
        assert calls_before == 2  # 1 STT chunk + 1 LLM curation window
        await orch.run_session(sid)
        calls_after = orch.db.budget_summary(settings.max_budget_usd)["calls_count"]
        assert calls_after == calls_before

        # 5. FastAPI HTTP endpoints + Non-destructive Editor update + 540p Draft + 1080p Replacement in Salidas/
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://testserver") as client:
            r_health = await client.get("/health")
            assert r_health.status_code == 200
            assert r_health.json()["ffmpeg"] is True
            assert r_health.json()["mediapipe_face_detector"] is True

            r_clip = await client.get(f"/clips/{cid}")
            assert r_clip.status_code == 200
            detail = r_clip.json()
            edited_plan = detail["clip"]["editplan"]
            edited_plan["overlays"] = [
                {"kind": "title", "text": "EDITADO EN STUDIO 1v3", "start": 0.0, "end": 3.0}
            ]

            r_save = await client.put(f"/clips/{cid}/editplan", json=edited_plan)
            assert r_save.status_code == 200
            assert r_save.json()["clip"]["state"] == "EDITED"

            # Render fast 540p draft
            r_draft = await client.post(f"/clips/{cid}/render", json={"quality": "draft", "upload_to_drive": False})
            assert r_draft.status_code == 200
            draft_path = Path(r_draft.json()["mp4_path"])
            draft_probe = probe(draft_path)
            assert (draft_probe.width, draft_probe.height) == (540, 960)

            # Export 1080p final -> must REPLACE existing file in Salidas/ (still exactly 1 MP4 and 1 JSON!)
            r_final = await client.post(f"/clips/{cid}/render", json={"quality": "final", "upload_to_drive": True})
            assert r_final.status_code == 200
            assert len(list(salidas_dir.glob("*.mp4"))) == 1
            updated_meta = json.loads(salidas_jsons[0].read_text(encoding="utf-8"))
            assert updated_meta["overlay_title"] == "EDITADO EN STUDIO 1v3"
    finally:
        await orch.shutdown()
