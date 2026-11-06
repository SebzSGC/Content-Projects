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
