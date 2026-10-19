"""Comprehensive automated test suite for VidForge (Phases 1 to 5)."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf
from fastapi.testclient import TestClient
from hypothesis import given, settings as hyp_settings, strategies as st

from vidforge.api.app import app
from vidforge.domain.models import TimelineModel
from vidforge.infra.hw import detect_hardware
from vidforge.infra.secrets import SecretStore
from vidforge.services.asr import (
    export_ass,
    export_srt,
    reconcile_script_with_asr_words,
    transcribe_or_align,
)
from vidforge.services.audio import (
    join_audio_files,
    normalize_audio_loudnorm,
    probe_media,
    synthesize_tts,
)
from vidforge.services.director import extract_character_tags, segment_script_into_beats
from vidforge.services.export import (
    export_capcut_draft,
    export_otio_json,
    validate_capcut_draft,
)
from vidforge.services.media_gen import generate_visual_image
from vidforge.services.planner import (
    build_auto_timeline,
    list_templates,
    validate_motion_semantics,
    validate_timeline_invariants,
)
from vidforge.services.render import (
    compute_xfade_schedule,
    render_gl_transition_via_sidecar,
    render_motion_scene_via_sidecar,
    render_timeline_to_mp4,
)


def test_hardware_and_nvenc_detection():
    hw = detect_hardware()
    assert hw["cpu_cores_logical"] >= 1
    assert "encoders" in hw
    assert hw["preferred_encoder"] in ("h264_nvenc", "h264_amf", "h264_qsv", "libx264")
    assert Path(hw["ffmpeg_path"]).exists()


def test_secret_store_encryption_and_redaction(tmp_path: Path):
    vault = tmp_path / "test_vault.bin"
    store = SecretStore(vault_path=vault)
    store.set_secret("openai", "sk-proj-1234567890ABCDEF")
    assert store.get_secret("openai") == "sk-proj-1234567890ABCDEF"
    statuses = {s["provider"]: s for s in store.list_status()}
    assert statuses["openai"]["configured"] is True
    assert statuses["openai"]["last4"] == "CDEF"
    # Ensure raw secret is not stored in plaintext on disk
    raw_bytes = vault.read_bytes()
    assert b"sk-proj-1234567890ABCDEF" not in raw_bytes
    store.delete_secret("openai")


def test_director_beats_and_semantic_rules():
    script_txt = "En 2026 las ventas subieron 87% en total. @Elena compara el sistema A versus el sistema B."
    tags = extract_character_tags(script_txt)
    assert tags == ["@Elena"]
    script = segment_script_into_beats(script_txt, "Estilo test")
    assert len(script.beats) == 2
    assert script.characters[0].tag == "@Elena"
    assert script.beats[0].media_kind == "motion"

    templates = {t["id"]: t for t in list_templates()}
    assert "stat-highlight" in templates
    # Valid number present in speech
    err_ok = validate_motion_semantics(
        templates["stat-highlight"],
        {"value": "87%", "label": "Ventas"},
        script.beats[0].text,
    )
    assert err_ok == []
    # Hallucinated number NOT in speech -> fail-closed
    err_bad = validate_motion_semantics(
        templates["stat-highlight"],
        {"value": "999%", "label": "Ventas"},
        script.beats[0].text,
    )
    assert len(err_bad) == 1


@given(
    slots=st.lists(st.integers(min_value=500_000, max_value=10_000_000), min_size=1, max_size=25),
    trans_val=st.integers(min_value=0, max_value=600_000),
)
@hyp_settings(max_examples=40)
def test_xfade_schedule_mathematical_invariant(slots: list[int], trans_val: int):
    trans = [trans_val for _ in range(len(slots) - 1)]
    clip_d, offsets, total_us = compute_xfade_schedule(slots, trans)
    assert len(clip_d) == len(slots)
    assert len(offsets) == len(slots) - 1
    assert total_us == sum(slots)
    # Monotonic offsets
    for i in range(1, len(offsets)):
        assert offsets[i] > offsets[i - 1]


def test_audio_tts_alignment_and_subtitles(tmp_path: Path):
    wav_path = tmp_path / "speech.wav"
    text = "Hola mundo este es un test de alineación precisa por palabra."
    synthesize_tts(text, wav_path, speed=1.1)
    assert wav_path.exists()

    norm_wav = tmp_path / "speech_norm.wav"
    normalize_audio_loudnorm(wav_path, norm_wav)
    assert norm_wav.exists()

    joined_wav = tmp_path / "joined.wav"
    join_audio_files([wav_path, norm_wav], joined_wav)
    assert joined_wav.exists()

    tr = transcribe_or_align(wav_path, "asset_123", script_text=text, language="es", use_whisper_if_available=False)
    assert len(tr.words) == 11
    for idx, w in enumerate(tr.words):
        assert w.start_us < w.end_us
        if idx > 0:
            assert w.start_us >= tr.words[idx - 1].end_us

    srt_txt = export_srt(tr)
    ass_txt = export_ass(tr, karaoke=True)
    assert "-->" in srt_txt
    assert "[V4+ Styles]" in ass_txt
    assert "{\\k" in ass_txt


def test_reconcile_script_with_asr_dp():
    script_words = ["El", "rendimiento", "creció", "un", "87%", "hoy"]
    asr_words = [
        {"text": "el", "start_us": 0, "end_us": 200_000, "confidence": 0.95},
        {"text": "rendimiento", "start_us": 200_000, "end_us": 600_000, "confidence": 0.92},
        {"text": "crecio", "start_us": 600_000, "end_us": 950_000, "confidence": 0.90},
        {"text": "87%", "start_us": 1_100_000, "end_us": 1_500_000, "confidence": 0.88},
        {"text": "hoy", "start_us": 1_500_000, "end_us": 1_800_000, "confidence": 0.96},
    ]
    aligned = reconcile_script_with_asr_words(script_words, asr_words, duration_us=2_000_000)
    assert len(aligned) == 6
    assert aligned[3].text == "un"
    assert aligned[3].source == "interpolated"
    for i in range(1, len(aligned)):
        assert aligned[i].start_us >= aligned[i - 1].end_us


def test_sidecar_motion_webm_alpha_and_gl_transition(tmp_path: Path):
    webm_out = tmp_path / "stat.webm"
    render_motion_scene_via_sidecar(
        template_id="stat-highlight",
        props={"value": "87%", "label": "Crecimiento", "sublabel": "Test Sidecar"},
        duration_us=1_000_000,
        output_path=webm_out,
        width=640,
        height=360,
        fps=15,
        alpha=True,
    )
    assert webm_out.exists()
    info = probe_media(webm_out)
    assert info["width"] == 640
    assert info["height"] == 360
    assert info["has_alpha"] is True

    # Test WebGL transition via sidecar
    dir_a = tmp_path / "frames_a"
    dir_b = tmp_path / "frames_b"
    dir_a.mkdir()
    dir_b.mkdir()
    generate_visual_image("Clip A", dir_a / "frame_001.png", width=640, height=360, beat_index=0)
    generate_visual_image("Clip B", dir_b / "frame_001.png", width=640, height=360, beat_index=1)

    gl_mp4 = tmp_path / "gl_trans.mp4"
    render_gl_transition_via_sidecar(
        transition_name="crosswarp",
        frames_a_dir=dir_a,
        frames_b_dir=dir_b,
        frame_count=8,
        output_path=gl_mp4,
        width=640,
        height=360,
        fps=15,
    )
    assert gl_mp4.exists()
    gl_info = probe_media(gl_mp4)
    assert gl_info["width"] == 640
    assert gl_info["height"] == 360


def test_end_to_end_synthetic_render_and_capcut_export(tmp_path: Path):
    client = TestClient(app)
    r_proj = client.post(
        "/api/v1/projects",
        json={"name": "Test Render E2E", "language": "es", "width": 640, "height": 360, "fps": 30},
    )
    assert r_proj.status_code == 200
    pid = r_proj.json()["id"]

    # Segment script
    r_seg = client.post(
        f"/api/v1/projects/{pid}/script/segment",
        json={
            "text": "El motor local creció un 87% este año. @Elena valida la exportación final.",
            "style_guide": "Minimalista",
        },
    )
    assert r_seg.status_code == 200

    # Create synthetic audio & upload
    wav_file = tmp_path / "narration.wav"
    sr = 24000
    t = np.linspace(0, 2.4, int(sr * 2.4), endpoint=False, dtype=np.float32)
    sf.write(str(wav_file), 0.2 * np.sin(2 * np.pi * 220 * t), sr)

    with wav_file.open("rb") as f:
        r_up = client.post(
            f"/api/v1/projects/{pid}/assets/upload?kind=audio",
            files={"file": ("narration.wav", f, "audio/wav")},
        )
    assert r_up.status_code == 200
    audio_aid = r_up.json()["id"]

    # Generate two scene images and upload
    for idx in range(2):
        img_p = tmp_path / f"scene_{idx}.png"
        generate_visual_image(f"Escena {idx}", img_p, width=640, height=360, beat_index=idx)
        with img_p.open("rb") as f:
            client.post(
                f"/api/v1/projects/{pid}/assets/upload?kind=image",
                files={"file": (img_p.name, f, "image/png")},
            )

    # Align transcript directly
    tr = transcribe_or_align(
        wav_file,
        audio_aid,
        script_text="El motor local creció un 87% este año. @Elena valida la exportación final.",
        language="es",
    )
    from vidforge.infra.db import db
    db.save_transcript(tr.model_dump(), pid)

    # Auto-plan timeline
    r_tl = client.post(
        f"/api/v1/projects/{pid}/timeline/autoplan",
        json={"transcript_id": tr.id, "default_transition": "fade", "transition_duration_us": 250_000, "include_motion_scenes": False},
    )
    assert r_tl.status_code == 200
    tl = TimelineModel(**r_tl.json())
    assert validate_timeline_invariants(tl) == []

    # Validate CapCut export
    draft_info = export_capcut_draft(tl, tmp_path / "capcut_out", "Proyecto_CapCut", copy_media=True, check_process_lock=False)
    draft_json = json.loads(Path(draft_info["draft_content_path"]).read_text(encoding="utf-8"))
    assert validate_capcut_draft(draft_json) == []

    # Validate OTIO export
    otio_file = export_otio_json(tl, tmp_path / "project.otio")
    assert otio_file.exists()

    # Render full MP4 video with Ken Burns + xfade + ASS subtitles + audio
    out_mp4 = tmp_path / "final_render.mp4"
    render_timeline_to_mp4(tl, out_mp4, transcript=tr, burn_subtitles=True, render_motion_overlays=False)
    assert out_mp4.exists()
    mp4_probe = probe_media(out_mp4)
    assert mp4_probe["width"] == 640
    assert mp4_probe["height"] == 360
    assert abs(mp4_probe["duration_us"] - tl.duration_us) < 250_000
