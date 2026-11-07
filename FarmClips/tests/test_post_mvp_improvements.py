"""Automated verification & benchmarks for all 8 post-MVP improvements."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Dict, List

import cv2
import httpx
import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient

from clipscore.domain import CuratedClip, EmojiSuggestion, SignalPeak, SignalSeries, SyncResult
from clipscore.signals import build_signal_series
from clipscore.timeline import build_compact_timeline, group_words_into_utterances
from clipseditplan import (
    AudioPlan,
    CaptionGroup,
    CaptionsPlan,
    CaptionWord,
    CropKeyframe,
    EditPlan,
    EmojiCue,
    GameplayCropKeyframe,
    LayoutEvent,
    OutputPlan,
    OverlayItem,
    SfxCue,
    SourcePlan,
)
from clipsmedia.drive import LocalFolderDriveConnector
from clipsmedia.ffmpeg import probe
from clipsproviders.notifications import detect_webhook_format, send_delivery_webhook
from clipsrender import LocalFfmpegRenderBackend, measure_plan_loudnorm_pass1
from clipsserver.api.routes import create_app
from clipsserver.config import ServerSettings
from clipsserver.orchestrator import Orchestrator, cleanup_temp_media, compute_storage_stats
from clipsstyles import ensure_emoji_png, list_emoji_catalog, load_preset, resolve_game_keyterms

REPO_ROOT = Path(__file__).resolve().parent.parent
GOLDEN_GAMEPLAY = REPO_ROOT / "tests" / "golden" / "gameplay.mp4"
GOLDEN_CAMERA = REPO_ROOT / "tests" / "golden" / "camara.mp4"
FIXTURES_DIR = REPO_ROOT / "tests" / "fixtures" / "api"


def _make_sample_plan() -> EditPlan:
    # Realistic 24-second clip with continuous face-tracking + slow-zoom + 2 impact zooms (24 keyframes)
    kfs = [
        CropKeyframe(
            t=round(i * 1.0, 2),
            cx=round(0.50 + 0.08 * np.sin(i * 0.6), 3),
            cy=round(0.44 + 0.03 * np.cos(i * 0.5), 3),
            zoom=round(1.02 + 0.14 * ((i % 7) / 6.0), 3),
            ease="inOutSine" if i % 2 == 0 else "outBack",
        )
        for i in range(25)
    ]
    return EditPlan(
        version=2,
        clip_id="bench_clip",
        source=SourcePlan(session="ses_bench", ranges=[(10.0, 22.0), (23.5, 35.5)]),
        output=OutputPlan(w=1080, h=1920, fps=30, style="hormozi-gaming"),
        layout=[
            LayoutEvent(t=0.0, kind="split", camera_ratio=0.4),
            LayoutEvent(t=8.0, kind="camera_full", until=10.0),
            LayoutEvent(t=18.0, kind="camera_full", until=20.0),
        ],
        camera_crop=kfs,
        gameplay_crop=[GameplayCropKeyframe(t=0.0, cx=0.55, cy=0.5, zoom=1.0)],
        overlays=[OverlayItem(kind="title", text="CLUTCH 1V3 HISTÓRICO", start=0.0, end=3.0)],
        captions=CaptionsPlan(
            preset="hormozi",
            groups=[
                CaptionGroup(
                    words=[
                        CaptionWord(w="NO", s=0.4, e=0.7),
                        CaptionWord(w="PUEDE", s=0.7, e=1.1),
                        CaptionWord(w="SER", s=1.1, e=1.6, emphasis=True),
                    ],
                    emoji=EmojiCue(id="1f631", at=1.1),
                ),
                CaptionGroup(
                    words=[
                        CaptionWord(w="HEADSHOT", s=8.1, e=8.8, emphasis=True),
                        CaptionWord(w="FINAL", s=8.8, e=9.4),
                    ],
                    emoji=EmojiCue(id="1f3af", at=8.1),
                ),
                CaptionGroup(
                    words=[
                        CaptionWord(w="VAMOS", s=18.2, e=18.9, emphasis=True),
                        CaptionWord(w="CAMPEONES", s=18.9, e=19.8),
                    ],
                    emoji=EmojiCue(id="1f525", at=18.2),
                ),
            ],
        ),
        audio=AudioPlan(
            mic_gain_db=2.0,
            duck_game_db=-9.0,
            sfx=[SfxCue(t=8.15, id="boom", gain_db=-3.0), SfxCue(t=18.2, id="boom", gain_db=-3.0)],
        ),
    )


@pytest.mark.asyncio
async def test_fast_affine_compositor_and_twopass_loudnorm_benchmark(tmp_path: Path) -> None:
    preset = load_preset("hormozi-gaming")
    plan = _make_sample_plan()
    sync = SyncResult(shift_sec=0.4, scale=1.0, method="audio_xcorr", confidence=0.95)

    # 1. Verify two-pass EBU R128 loudness pass 1 measurement (<2s)
    t_m0 = time.perf_counter()
    stats = measure_plan_loudnorm_pass1(
        plan=plan,
        preset=preset,
        gameplay_path=GOLDEN_GAMEPLAY,
        camera_path=GOLDEN_CAMERA,
        sync=sync,
        clean_game_audio_stream=1,
    )
    t_measure = time.perf_counter() - t_m0
    assert stats is not None
    assert "input_i" in stats and float(stats["input_i"]) > -60.0
    assert t_measure < 4.0

    # 2. Benchmark Legacy FFmpeg `eval=frame` vs New C++ `cv2.warpAffine` on 1080x1920
    legacy_backend = LocalFfmpegRenderBackend(use_nvenc=True, use_fast_affine=False, two_pass_loudnorm=False)
    fast_backend = LocalFfmpegRenderBackend(use_nvenc=True, use_fast_affine=True, two_pass_loudnorm=True)

    t0 = time.perf_counter()
    legacy_mp4 = await legacy_backend.render_plan(
        plan=plan,
        preset=preset,
        gameplay_path=GOLDEN_GAMEPLAY,
        camera_path=GOLDEN_CAMERA,
        sync=sync,
        out_dir=tmp_path / "legacy",
        quality="final",
        clean_game_audio_stream=1,
    )
    t_legacy = time.perf_counter() - t0

    t1 = time.perf_counter()
    fast_mp4 = await fast_backend.render_plan(
        plan=plan,
        preset=preset,
        gameplay_path=GOLDEN_GAMEPLAY,
        camera_path=GOLDEN_CAMERA,
        sync=sync,
        out_dir=tmp_path / "fast",
        quality="final",
        clean_game_audio_stream=1,
    )
    t_fast = time.perf_counter() - t1

    t2 = time.perf_counter()
    draft_mp4 = await fast_backend.render_plan(
        plan=plan,
        preset=preset,
        gameplay_path=GOLDEN_GAMEPLAY,
        camera_path=GOLDEN_CAMERA,
        sync=sync,
        out_dir=tmp_path / "fast_draft",
        quality="draft",
        clean_game_audio_stream=1,
    )
    t_draft = time.perf_counter() - t2

    probe_final = probe(fast_mp4)
    probe_draft = probe(draft_mp4)
    assert probe_final.width == 1080 and probe_final.height == 1920 and probe_final.has_audio
    assert abs(probe_final.duration - plan.total_duration()) < 0.35
    assert probe_draft.width == 540 and probe_draft.height == 960 and probe_draft.has_audio
    assert legacy_mp4.is_file()

    # Check .ffscript contains linear=true from 2-pass loudnorm
    ffscripts = list((tmp_path / "fast").glob("*.ffscript"))
    assert ffscripts and "linear=true" in ffscripts[0].read_text(encoding="utf-8")

    print(
        f"\n[BENCHMARK 24s clip] Legacy FFmpeg eval=frame 1080p: {t_legacy:.2f}s | "
        f"Fast warpAffine+2pass 1080p: {t_fast:.2f}s ({t_legacy / max(0.01, t_fast):.1f}x speedup) | "
        f"Draft 540p: {t_draft:.2f}s"
    )
    assert t_fast < t_legacy * 0.65


def test_emoji_42_catalog_and_sfx_endpoints(tmp_path: Path) -> None:
    catalog = list_emoji_catalog()
    assert len(catalog) >= 40
    # Render every catalog emoji cleanly via 2x Lanczos supersampling
    for item in catalog:
        p = ensure_emoji_png(item["id"], size=128, cache_dir=tmp_path / "emojis")
        assert p.is_file() and p.stat().st_size > 250

    settings = ServerSettings(data_dir=tmp_path / "srv_data", drive_mode="disabled", fixtures_dir=FIXTURES_DIR)
    app = create_app(settings, use_process_pool=False, enable_drive_watcher=False)
    with TestClient(app) as client:
        r_cat = client.get("/emojis")
        assert r_cat.status_code == 200
        assert len(r_cat.json()) == len(catalog)

        r_png = client.get("/emojis/1f451.png")
        assert r_png.status_code == 200 and r_png.headers["content-type"] == "image/png"

        r_sfx = client.get("/sfx/boom.wav")
        assert r_sfx.status_code == 200 and "audio" in r_sfx.headers["content-type"]
        assert len(r_sfx.content) > 10_000


def test_per_game_keyterms_autodetection_and_api(tmp_path: Path) -> None:
    game_v, terms_v = resolve_game_keyterms(title="Subiendo a Radiante en Valorant con Jett", base_keyterms=["clip"])
    assert game_v == "valorant"
    assert "Vandal" in terms_v and "Jett" in terms_v
    assert len(terms_v) <= 50

    game_lol, terms_lol = resolve_game_keyterms(recording_name="2026_pentakill_baron_lol")
    assert game_lol == "lol"
    assert "Baron Nashor" in terms_lol

    game_cs, terms_cs = resolve_game_keyterms(title="CS2 Faceit lvl 10 Mirage")
    assert game_cs == "cs2"
    assert "AWP" in terms_cs

    game_none, terms_gen = resolve_game_keyterms(title="Charlando con el chat")
    assert game_none is None
    assert "clutch" in [t.lower() for t in terms_gen]

    settings = ServerSettings(data_dir=tmp_path / "kt_data", drive_mode="disabled", fixtures_dir=FIXTURES_DIR)
    app = create_app(settings, use_process_pool=False, enable_drive_watcher=False)
    with TestClient(app) as client:
        res = client.get("/keyterms", params={"title": "Fortnite Zero Build Torneo"})
        assert res.status_code == 200
        body = res.json()
        assert body["detected_game"] == "fortnite"
        assert len(body["profiles"]) >= 8


def test_hud_killfeed_2fps_signal_and_timeline(tmp_path: Path) -> None:
    # Synthesize a 10s 30fps video where t=5.0..5.8s has a sharp high-contrast killfeed banner in top-right + hitmarker
    vid_path = tmp_path / "hud_test.mp4"
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    writer = cv2.VideoWriter(str(vid_path), fourcc, 10.0, (320, 180))
    for f_i in range(100):
        sec = f_i / 10.0
        frame = np.full((180, 320, 3), 35, dtype=np.uint8)
        if 5.0 <= sec <= 5.8:
            # High-contrast striped killfeed rows in top-right (x: 220..315, y: 6..45) + center hitmarker
            for ry in range(8, 42, 8):
                cv2.rectangle(frame, (225, ry), (312, ry + 5), (255, 255, 255), -1)
                cv2.line(frame, (250, ry), (250, ry + 5), (0, 0, 255), 2)
            cv2.line(frame, (152, 82), (168, 98), (255, 255, 255), 2)
            cv2.line(frame, (168, 82), (152, 98), (255, 255, 255), 2)
        writer.write(frame)
    writer.release()

    sr = 16000
    t_arr = np.linspace(0, 10.0, sr * 10, endpoint=False, dtype=np.float32)
    mic_wave = np.where((t_arr >= 5.0) & (t_arr <= 6.2), 0.65 * np.sin(2 * np.pi * 420 * t_arr), 0.01 * np.sin(2 * np.pi * 150 * t_arr))
    game_wave = 0.05 * np.sin(2 * np.pi * 110 * t_arr)
    cam_wav = tmp_path / "cam16.wav"
    game_wav = tmp_path / "game16.wav"
    sf.write(str(cam_wav), mic_wave, sr)
    sf.write(str(game_wav), game_wave, sr)

    sig = build_signal_series(
        duration=10.0,
        camera_wav16k=str(cam_wav),
        gameplay_wav16k=str(game_wav),
        gameplay_video_path=str(vid_path),
        enable_motion=True,
    )
    assert len(sig.hud_activity) == 10
    assert sig.hud_activity[5] > 0.6

    pq_path = tmp_path / "signals.parquet"
    sig.to_parquet(pq_path)
    reloaded = SignalSeries.from_parquet(pq_path)
    assert reloaded.hud_activity == sig.hud_activity
    assert any(p.hud >= 0.45 for p in reloaded.peaks)

    tl_txt = build_compact_timeline([], reloaded)
    assert "hud=" in tl_txt


@pytest.mark.asyncio
async def test_concurrent_drive_upload_and_webhooks(tmp_path: Path) -> None:
    # 1. LocalFolderDriveConnector concurrent upload
    conn = LocalFolderDriveConnector(tmp_path / "drive", require_two_polls=False)
    dummy_mp4 = tmp_path / "dummy.mp4"
    dummy_mp4.write_bytes(b"\x00\x00\x00\x18ftypmp42" + b"x" * 4096)
    uploaded = await conn.upload_clip_bundle("valorant_noche", "clip_01_demo", dummy_mp4, {"score": 91.0})
    assert Path(uploaded["mp4"]).is_file() and Path(uploaded["json"]).is_file()

    # 2. Discord, Slack & Generic webhooks with transient 503 retry
    received: List[Dict[str, Any]] = []
    attempts = 0

    def _mock_handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        body = json.loads(request.content.decode("utf-8"))
        if attempts == 1:
            return httpx.Response(503, text="temporary overload")
        received.append({"url": str(request.url), "body": body})
        return httpx.Response(204)

    transport = httpx.MockTransport(_mock_handler)
    async with httpx.AsyncClient(transport=transport) as client:
        discord_url = "https://discord.com/api/webhooks/12345/token_abc"
        assert detect_webhook_format(discord_url) == "discord"
        res = await send_delivery_webhook(
            webhook_url=discord_url,
            session_id="ses_999",
            title="Valorant Radiante",
            clips=[{"id": "clip_01", "overlay_title": "ACE LIMPIO", "final_score": 94.0}],
            client=client,
        )
        assert res["ok"] is True and res["format"] == "discord"
        assert attempts == 2
        assert "embeds" in received[0]["body"]

        slack_res = await send_delivery_webhook(
            webhook_url="https://hooks.slack.com/services/T00/B00/XXX",
            session_id="ses_999",
            title="Valorant Radiante",
            clips=[{"id": "clip_01", "overlay_title": "ACE LIMPIO", "final_score": 94.0}],
            client=client,
        )
        assert slack_res["ok"] is True and slack_res["format"] == "slack"


@pytest.mark.asyncio
async def test_ttl_cleanup_preserves_zero_dollar_rerun_guarantee(tmp_path: Path) -> None:
    webhook_calls: List[Dict[str, Any]] = []
    settings = ServerSettings(
        data_dir=tmp_path / "data",
        drive_mode="local",
        drive_local_dir=tmp_path / "drive_mirror",
        stt_primary="fixture",
        stt_backup="none",
        llm_primary="fixture",
        llm_backup="none",
        fixtures_dir=FIXTURES_DIR,
        auto_render_top_k=1,
        auto_render_min_score=50.0,
        temp_ttl_days=7.0,
    )
    orch = Orchestrator(settings, use_process_pool=False, require_two_drive_polls=False)
    try:
        ses = orch.db.create_session(
            title="Valorant Clutch Test",
            gameplay_path=str(GOLDEN_GAMEPLAY),
            camera_path=str(GOLDEN_CAMERA),
            recording_name="valorant_clutch_test",
        )
        sid = ses["id"]
        await orch.run_session(sid)

        row_after = orch.db.get_session(sid)
        assert row_after is not None and row_after["state"] == "DELIVERED"
        budget_before = orch.db.budget_summary(settings.max_budget_usd)
        assert budget_before["calls_count"] >= 2

        stats_before = compute_storage_stats(settings.data_dir, orch.db, temp_ttl_days=0.0)
        assert stats_before["temp_media_bytes"] > 50_000
        assert stats_before["eligible_sessions_count"] == 1

        # Purge all intermediate WAV & Opus files with ttl_days=0.0
        clean_res = cleanup_temp_media(settings.data_dir, orch.db, ttl_days=0.0, include_inputs=False)
        assert clean_res["purged_files"] >= 3
        assert clean_res["freed_bytes"] > 50_000
        assert sid in clean_res["cleaned_sessions"]

        media_dir = orch.session_dir(sid) / "media"
        assert not list(media_dir.rglob("*.wav"))
        assert not list(media_dir.rglob("*.opus"))
        # Preserved artifacts must still exist
        assert (orch.session_dir(sid) / "signals.parquet").is_file()
        assert (orch.session_dir(sid) / "utterances.json").is_file()

        # Re-running the session AFTER temp files were purged must succeed with ZERO new API calls!
        await orch.run_session(sid)
        budget_after = orch.db.budget_summary(settings.max_budget_usd)
        assert budget_after["calls_count"] == budget_before["calls_count"]
        assert budget_after["spent_usd"] == budget_before["spent_usd"]
        row_rerun = orch.db.get_session(sid)
        assert row_rerun is not None and row_rerun["state"] == "DELIVERED"
    finally:
        await orch.shutdown()


def test_settings_persistence_masking_hot_reload_and_test_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from clipsserver.config import mask_api_key, read_dotenv_values

    assert mask_api_key("AIzaSyD12345678908a9b") == "AIza...8a9b"
    assert mask_api_key("sk-proj-12345678903f1a") == "sk-...3f1a"
    assert mask_api_key("") == ""

    env_file = tmp_path / ".env"
    env_file.write_text(
        "# Comentario preservado\nCLIPS_STT_PRIMARY=deepgram\nGEMINI_API_KEY=AIzaSyInitialKey8a9b\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("CLIPS_ENV_FILE", str(env_file))
    monkeypatch.setenv("GEMINI_API_KEY", "AIzaSyInitialKey8a9b")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("DEEPGRAM_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_API_KEY", raising=False)

    settings = ServerSettings(
        data_dir=tmp_path / "data",
        drive_mode="disabled",
        gemini_api_key="AIzaSyInitialKey8a9b",
    )
    app = create_app(settings, use_process_pool=False, enable_drive_watcher=False)

    def _mock_provider_handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers.get("Authorization", "")
        url_str = str(request.url)
        if "api.deepgram.com" in url_str:
            if auth == "Token dg_valid_key_9999":
                return httpx.Response(200, json={"projects": [{"name": "FarmClips"}]})
            return httpx.Response(401, json={"err_msg": "Invalid credentials"})
        if "generativelanguage.googleapis.com" in url_str:
            if "key=AIzaSyInitialKey8a9b" in url_str:
                return httpx.Response(200, json={"models": [{"name": "models/gemini-3.5-flash-lite"}]})
            return httpx.Response(400, json={"error": {"message": "API key not valid"}})
        if "api.openai.com" in url_str:
            if auth == "Bearer sk-live-secret-3f1a":
                return httpx.Response(200, json={"data": [{"id": "gpt-6-luna"}]})
            return httpx.Response(401, json={"error": {"message": "Incorrect API key provided"}})
        return httpx.Response(200, json={"ok": True})

    app.state.test_http_client = httpx.AsyncClient(transport=httpx.MockTransport(_mock_provider_handler))

    with TestClient(app) as client:
        # 1. GET /settings returns masked keys and booleans
        r0 = client.get("/settings")
        assert r0.status_code == 200
        s0 = r0.json()
        assert s0["gemini_api_key"] == "AIza...8a9b"
        assert s0["has_gemini_key"] is True
        assert s0["api_keys"]["gemini"] == {"masked": "AIza...8a9b", "has_key": True}
        assert s0["has_openai_key"] is False
        assert s0["api_keys"]["openai"] == {"masked": "", "has_key": False}

        # 2. POST /settings updates new keys, preserves masked/blank keys, updates .env & hot-reloads memory
        r1 = client.post(
            "/settings",
            json={
                "stt_primary": "groq",
                "llm_primary": "openai_compat",
                "llm_model": "gpt-6-luna",
                "max_budget_usd": 14.5,
                "gemini_api_key": "AIza...8a9b",  # Masked -> must preserve AIzaSyInitialKey8a9b
                "deepgram_api_key": "",            # Blank -> must not overwrite
                "openai_api_key": "sk-live-secret-3f1a",
            },
        )
        assert r1.status_code == 200
        s1 = r1.json()
        assert s1["stt_primary"] == "groq"
        assert s1["llm_primary"] == "openai_compat"
        assert s1["llm_model"] == "gpt-6-luna"
        assert s1["max_budget_usd"] == 14.5
        assert s1["gemini_api_key"] == "AIza...8a9b"
        assert s1["has_gemini_key"] is True
        assert s1["openai_api_key"] == "sk-...3f1a"
        assert s1["has_openai_key"] is True

        # Verify .env file on disk kept comments, preserved GEMINI_API_KEY, and added OPENAI_API_KEY
        disk_vals = read_dotenv_values(env_file)
        assert disk_vals["GEMINI_API_KEY"] == "AIzaSyInitialKey8a9b"
        assert disk_vals["OPENAI_API_KEY"] == "sk-live-secret-3f1a"
        assert disk_vals["CLIPS_STT_PRIMARY"] == "groq"
        assert disk_vals["CLIPS_MAX_BUDGET_USD"] == "14.50"
        assert "# Comentario preservado" in env_file.read_text(encoding="utf-8")

        # Verify in-memory hot reload reflected immediately in /health and Orchestrator.api_pool
        h1 = client.get("/health").json()
        assert h1["stt_primary"] == "groq"
        assert h1["llm_primary"] == "openai_compat"
        assert h1["budget"]["max_budget_usd"] == 14.5
        assert app.state.orchestrator.api_pool.settings.openai_api_key == "sk-live-secret-3f1a"

        # 3. POST /settings/test-connection works with saved key (when omitted/masked) and explicit key
        t_gemini = client.post("/settings/test-connection", json={"provider": "gemini"}).json()
        assert t_gemini["ok"] is True
        assert t_gemini["provider"] == "gemini"

        t_openai = client.post("/settings/test-connection", json={"provider": "openai_compat"}).json()
        assert t_openai["ok"] is True

        t_dg_fail = client.post(
            "/settings/test-connection",
            json={"provider": "deepgram", "api_key": "dg_wrong_key"},
        ).json()
        assert t_dg_fail["ok"] is False
        assert "Invalid credentials" in t_dg_fail["detail"]

        t_dg_ok = client.post(
            "/settings/test-connection",
            json={"provider": "deepgram", "api_key": "dg_valid_key_9999"},
        ).json()
        assert t_dg_ok["ok"] is True


def test_analytics_summary_breakdown_and_logs_endpoints(tmp_path: Path) -> None:
    settings = ServerSettings(
        data_dir=tmp_path / "analytics_data",
        drive_mode="disabled",
        max_budget_usd=9.0,
    )
    app = create_app(settings, use_process_pool=False, enable_drive_watcher=False)
    orch = app.state.orchestrator
    ses = orch.db.create_session(title="Streaming general de video juegos", session_id="ses_analytics_1")

    raw_dummy = tmp_path / "raw.json"
    raw_dummy.write_text("{}", encoding="utf-8")

    # Record 10 Deepgram STT calls (~5,980.8s total) + 1 Gemini LLM call (40,611 in / 1,363 out)
    for idx in range(10):
        orch.db.record_api_call(
            session_id=ses["id"],
            task_hash=f"hash_stt_{idx:02d}",
            provider="deepgram",
            model="nova-3",
            kind="stt",
            raw_response_path=raw_dummy,
            units_billed=598.0842,
            input_tokens=0,
            output_tokens=0,
            cost_usd=0.0428627,
            latency_ms=4800 + idx * 50,
        )
    orch.db.record_api_call(
        session_id=ses["id"],
        task_hash="hash_llm_01",
        provider="gemini",
        model="gemini-3.5-flash-lite",
        kind="llm",
        raw_response_path=raw_dummy,
        units_billed=41974.0,
        input_tokens=40611,
        output_tokens=1363,
        cost_usd=0.015591,
        latency_ms=4632,
    )

    for c_i in range(5):
        orch.db.upsert_clip(
            clip_id=f"clip_an_{c_i}",
            session_id=ses["id"],
            rank_order=c_i + 1,
            start_sec=float(c_i * 60),
            end_sec=float(c_i * 60 + 30),
            overlay_title=f"CLIP {c_i}",
            post_title=f"Post {c_i}",
            hashtags=["#gaming"],
            reason="Momento clave",
            llm_score=90.0,
            signal_score=85.0,
            final_score=88.5,
            curated_json="{}",
            state="DELIVERED",
        )

    with TestClient(app) as client:
        s_res = client.get("/analytics/summary")
        assert s_res.status_code == 200
        summary = s_res.json()
        assert summary["total_calls"] == 11
        assert summary["stt_calls"] == 10
        assert summary["llm_calls"] == 1
        assert abs(summary["spent_usd"] - 0.444218) < 1e-4
        assert summary["input_tokens"] == 40611
        assert summary["output_tokens"] == 1363
        assert summary["total_tokens"] == 41974
        assert abs(summary["audio_minutes_billed"] - 99.68) < 0.05
        assert summary["alert_status"] == "NORMAL"
        assert summary["projections"]["estimated_remaining_stream_hours"] > 25.0
        assert summary["projections"]["estimated_remaining_clips"] >= 90

        b_res = client.get("/analytics/breakdown")
        assert b_res.status_code == 200
        brk = b_res.json()
        provs = {p["provider"]: p for p in brk["by_provider"]}
        assert "deepgram" in provs and "gemini" in provs
        assert provs["deepgram"]["calls"] == 10
        assert provs["gemini"]["calls"] == 1
        assert len(brk["by_session"]) == 1
        assert brk["by_session"][0]["clips_count"] == 5

        l_all = client.get("/analytics/logs").json()
        assert l_all["total"] == 11
        assert len(l_all["items"]) == 11

        l_gem = client.get("/analytics/logs", params={"provider": "gemini", "kind": "llm"}).json()
        assert l_gem["total"] == 1
        assert l_gem["items"][0]["model"] == "gemini-3.5-flash-lite"

        # Free-tier credit: estimated by default, then anchored to the real balance from the Deepgram console
        ft = {m["id"]: m for m in summary["free_tier"]["models"]}
        assert ft["nova-3"]["credit"]["source"] == "estimated"
        cal = client.post("/analytics/free-tier/calibrate", json={"provider": "deepgram", "balance_usd": 199.43})
        assert cal.status_code == 200
        dg = {m["id"]: m for m in cal.json()["summary"]["free_tier"]["models"]}["nova-3"]["credit"]
        assert dg["source"] == "manual"
        assert abs(dg["remaining_usd"] - 199.43) < 1e-6
        assert abs(dg["used_usd"] - 0.57) < 1e-6

        # New calls after calibration are subtracted from the real balance
        orch.db.record_api_call(
            session_id=ses["id"], task_hash="hash_stt_after", provider="deepgram", model="nova-3", kind="stt",
            raw_response_path=raw_dummy, units_billed=600.0, cost_usd=0.056, latency_ms=4000,
        )
        dg2 = {m["id"]: m for m in client.get("/analytics/summary").json()["free_tier"]["models"]}["nova-3"]["credit"]
        assert abs(dg2["remaining_usd"] - 199.374) < 1e-4

        assert client.post("/analytics/free-tier/calibrate", json={"balance_usd": 250.0}).status_code == 400
        reset = client.delete("/analytics/free-tier/calibrate/deepgram").json()
        dg3 = {m["id"]: m for m in reset["summary"]["free_tier"]["models"]}["nova-3"]["credit"]
        assert dg3["source"] == "estimated"


def test_google_drive_oauth_connector_explorer_and_session_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("# Drive OAuth test\n", encoding="utf-8")
    monkeypatch.setenv("CLIPS_ENV_FILE", str(env_file))

    gp_bytes = GOLDEN_GAMEPLAY.read_bytes()
    cam_bytes = GOLDEN_CAMERA.read_bytes()

    token_calls: List[str] = []

    def _mock_google_drive_handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        # 1. OAuth 2.0 token endpoint (authorization_code & refresh_token)
        if "oauth2.googleapis.com/token" in url:
            body_str = request.content.decode("utf-8")
            token_calls.append(body_str)
            if "grant_type=authorization_code" in body_str:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ya29.initial_token",
                        "refresh_token": "1//refresh_token_secret_xyz",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    },
                )
            if "grant_type=refresh_token" in body_str:
                return httpx.Response(
                    200,
                    json={
                        "access_token": "ya29.refreshed_token",
                        "expires_in": 3600,
                        "token_type": "Bearer",
                    },
                )
            return httpx.Response(400, json={"error": "unsupported_grant_type"})

        # 2. User info (/drive/v3/about)
        if "/drive/v3/about" in url:
            return httpx.Response(
                200,
                json={"user": {"emailAddress": "streamer@farmclips.gg", "displayName": "Streamer Pro"}},
            )

        # 3. File download (?alt=media)
        if "alt=media" in url:
            if "/files/file_gp_01" in url:
                return httpx.Response(200, content=gp_bytes, headers={"Content-Type": "video/mp4"})
            if "/files/file_cam_01" in url:
                return httpx.Response(200, content=cam_bytes, headers={"Content-Type": "video/mp4"})
            return httpx.Response(404, json={"error": "not found"})

        # 4. Folder/File metadata (/drive/v3/files/<id>)
        if "/drive/v3/files/fld_entradas" in url:
            return httpx.Response(
                200,
                json={
                    "id": "fld_entradas",
                    "name": "Entradas",
                    "parents": ["root"],
                    "mimeType": "application/vnd.google-apps.folder",
                },
            )
        if "/drive/v3/files/fld_val_01" in url:
            return httpx.Response(
                200,
                json={
                    "id": "fld_val_01",
                    "name": "valorant_ranked_noche",
                    "parents": ["fld_entradas"],
                    "mimeType": "application/vnd.google-apps.folder",
                },
            )
        if "/drive/v3/files/file_gp_01" in url:
            return httpx.Response(
                200,
                json={
                    "id": "file_gp_01",
                    "name": "gameplay_valorant.mp4",
                    "size": str(len(gp_bytes)),
                    "mimeType": "video/mp4",
                    "modifiedTime": "2026-11-07T14:00:00.000Z",
                },
            )
        if "/drive/v3/files/file_cam_01" in url:
            return httpx.Response(
                200,
                json={
                    "id": "file_cam_01",
                    "name": "camara_streamer.mp4",
                    "size": str(len(cam_bytes)),
                    "mimeType": "video/mp4",
                    "modifiedTime": "2026-11-07T14:00:05.000Z",
                },
            )

        # 5. Folder listing (/drive/v3/files?q=...)
        if "/drive/v3/files" in url:
            q_param = request.url.params.get("q", "")
            if "'root' in parents" in q_param:
                return httpx.Response(
                    200,
                    json={
                        "files": [
                            {
                                "id": "fld_entradas",
                                "name": "Entradas",
                                "mimeType": "application/vnd.google-apps.folder",
                                "modifiedTime": "2026-11-07T13:00:00.000Z",
                            }
                        ]
                    },
                )
            if "'fld_val_01' in parents" in q_param or "name contains" in q_param:
                return httpx.Response(
                    200,
                    json={
                        "files": [
                            {
                                "id": "file_gp_01",
                                "name": "gameplay_valorant.mp4",
                                "size": str(len(gp_bytes)),
                                "mimeType": "video/mp4",
                                "modifiedTime": "2026-11-07T14:00:00.000Z",
                            },
                            {
                                "id": "file_cam_01",
                                "name": "camara_streamer.mp4",
                                "size": str(len(cam_bytes)),
                                "mimeType": "video/mp4",
                                "modifiedTime": "2026-11-07T14:00:05.000Z",
                            },
                        ]
                    },
                )
            return httpx.Response(200, json={"files": []})

        return httpx.Response(200, json={"ok": True})

    settings = ServerSettings(
        data_dir=tmp_path / "oauth_data",
        drive_mode="local",
        drive_local_dir=tmp_path / "drive_mirror",
        stt_primary="fixture",
        stt_backup="none",
        llm_primary="fixture",
        llm_backup="none",
        fixtures_dir=FIXTURES_DIR,
    )
    app = create_app(settings, use_process_pool=False, enable_drive_watcher=False)
    app.state.test_http_client = httpx.AsyncClient(transport=httpx.MockTransport(_mock_google_drive_handler))

    with TestClient(app) as client:
        # 1. Configure OAuth Client ID & Secret via POST /settings
        r_cfg = client.post(
            "/settings",
            json={
                "drive_mode": "oauth",
                "drive_client_id": "123456-test.apps.googleusercontent.com",
                "drive_client_secret": "GOCSPX-super-secret-9988",
            },
        )
        assert r_cfg.status_code == 200
        cfg_json = r_cfg.json()
        assert cfg_json["drive_mode"] == "oauth"
        assert cfg_json["drive_client_id"] == "123456-test.apps.googleusercontent.com"
        assert cfg_json["has_drive_client_secret"] is True
        assert cfg_json["drive_client_secret"] == "GOCS...9988"

        # 2. GET /drive/auth/url generates Google OAuth 2.0 authorization URL
        r_url = client.get("/drive/auth/url", params={"state": "st_test_1"})
        assert r_url.status_code == 200
        url_data = r_url.json()
        assert "accounts.google.com/o/oauth2/v2/auth" in url_data["auth_url"]
        assert "access_type=offline" in url_data["auth_url"]
        assert "123456-test.apps.googleusercontent.com" in url_data["auth_url"]

        # 3. GET /drive/auth/callback exchanges authorization code and persists data/drive_oauth_token.json
        r_cb = client.get("/drive/auth/callback", params={"code": "4/0AeanS_mock_auth_code", "state": "st_test_1"})
        assert r_cb.status_code == 200
        cb_data = r_cb.json()
        assert cb_data["ok"] is True
        assert cb_data["oauth_connected"] is True
        assert cb_data["user_email"] == "streamer@farmclips.gg"

        token_file = settings.data_dir / "drive_oauth_token.json"
        assert token_file.is_file()
        saved_tok = json.loads(token_file.read_text(encoding="utf-8"))
        assert saved_tok["refresh_token"] == "1//refresh_token_secret_xyz"
        assert saved_tok["user_email"] == "streamer@farmclips.gg"

        # Force token expiration to verify automatic refresh_token flow on next Drive API call
        app.state.orchestrator.drive._token_exp = 0.0

        # 4. GET /drive/status reflects active OAuth connection
        st_res = client.get("/drive/status").json()
        assert st_res["mode"] == "oauth"
        assert st_res["connected"] is True
        assert st_res["oauth_connected"] is True
        assert st_res["user_email"] == "streamer@farmclips.gg"

        # 5. GET /drive/files browses subfolder with multi-level breadcrumbs & auto-detected gameplay+camera pair
        r_files = client.get("/drive/files", params={"folder_id": "fld_val_01"})
        assert r_files.status_code == 200
        browsed = r_files.json()
        assert browsed["folder_id"] == "fld_val_01"
        assert browsed["folder_name"] == "valorant_ranked_noche"
        assert [b["name"] for b in browsed["breadcrumbs"]] == ["Mi unidad", "Entradas", "valorant_ranked_noche"]
        assert len(browsed["files"]) == 2
        assert browsed["detected_pair"] is not None
        assert browsed["detected_pair"]["gameplay"]["id"] == "file_gp_01"
        assert browsed["detected_pair"]["camera"]["id"] == "file_cam_01"
        assert any("grant_type=refresh_token" in c for c in token_calls)

        # 6. POST /drive/sessions downloads gameplay + camera via ApiPool and creates session
        r_ses = client.post(
            "/drive/sessions",
            json={
                "title": "Valorant Ranked desde Drive OAuth",
                "folder_id": "fld_val_01",
                "gameplay_file_id": "file_gp_01",
                "camera_file_id": "file_cam_01",
                "auto_start": False,
            },
        )
        assert r_ses.status_code == 200
        ses_data = r_ses.json()
        assert ses_data["title"] == "Valorant Ranked desde Drive OAuth"
        assert ses_data["state"] == "DOWNLOADED"
        assert ses_data["detected_game"] == "valorant"
        assert Path(ses_data["gameplay_path"]).is_file()
        assert Path(ses_data["camera_path"]).is_file()
        assert Path(ses_data["gameplay_path"]).stat().st_size == len(gp_bytes)
        assert Path(ses_data["camera_path"]).stat().st_size == len(cam_bytes)

        # 7. POST /drive/auth/disconnect removes token file and marks OAuth disconnected
        r_disc = client.post("/drive/auth/disconnect")
        assert r_disc.status_code == 200
        assert r_disc.json()["oauth_connected"] is False
        assert not token_file.is_file()



