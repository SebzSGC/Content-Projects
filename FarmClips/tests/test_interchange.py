"""Pruebas unitarias y de integración para clipsinterchange (FilmCraft y OTIO)."""

import json
import shutil
import subprocess
from fractions import Fraction
from pathlib import Path

import pytest
from clipseditplan import CropKeyframe, EditPlan
from clipsinterchange import (
    ExportContext,
    TICKS_PER_SECOND,
    frame_to_ticks,
    seconds_to_ticks,
    ticks_to_seconds,
)
from clipsinterchange.audio import generate_ducking_keyframes, merge_voice_spans
from clipsinterchange.filmcraft.exporter import FilmCraftExporter
from clipsinterchange.geometry import compute_motion_transform, get_layout_regions
from clipsinterchange.otio.exporter import OtioExporter


def test_timebase_exactness():
    fps = Fraction(60, 1)
    # 1 segundo exacto = 254,016,000,000 ticks
    assert seconds_to_ticks(1.0, fps=fps) == TICKS_PER_SECOND
    assert ticks_to_seconds(TICKS_PER_SECOND) == 1.0

    # 1/60 segundo (1 frame a 60 fps)
    one_frame_ticks = frame_to_ticks(1, fps=fps)
    assert one_frame_ticks == TICKS_PER_SECOND // 60
    assert seconds_to_ticks(1 / 60, fps=fps) == one_frame_ticks


def test_geometry_layout_and_motion():
    # Split layout (camera ratio 0.40)
    regions = get_layout_regions("split", camera_ratio=0.40, canvas_w=1080, canvas_h=1920)
    assert regions.camera == (0, 0, 1080, 768)
    assert regions.gameplay == (0, 768, 1080, 1152)

    # Transformación de cámara
    cam_xform = compute_motion_transform(
        source_w=1920,
        source_h=1080,
        region=regions.camera,
        cx=0.5,
        cy=0.5,
        zoom=1.0,
    )
    assert cam_xform.opacity_pct == 100.0
    assert cam_xform.scale_pct > 0.0
    assert cam_xform.anchor_x == 960.0
    assert cam_xform.anchor_y == 540.0

    # Camera full
    full_cam = get_layout_regions("camera_full", canvas_w=1080, canvas_h=1920)
    assert full_cam.camera == (0, 0, 1080, 1920)
    assert full_cam.gameplay is None

    game_hidden = compute_motion_transform(
        source_w=1920, source_h=1080, region=full_cam.gameplay
    )
    assert game_hidden.opacity_pct == 0.0


def test_audio_ducking():
    spans = [(1.0, 3.0), (3.1, 4.0)]  # Espacio entre ellos es 0.1s (< 0.25s) -> deben fusionarse
    merged = merge_voice_spans(spans, min_gap_s=0.25)
    assert len(merged) == 1
    assert merged[0] == (1.0, 4.0)

    kfs = generate_ducking_keyframes(merged, duck_gain_db=-18.0, base_gain_db=0.0)
    assert len(kfs) == 4
    assert kfs[0].level_db == 0.0
    assert kfs[1].level_db == -18.0
    assert kfs[2].level_db == -18.0
    assert kfs[3].level_db == 0.0


def test_filmcraft_exporter_e2e(tmp_path: Path):
    out_dir = tmp_path / "export_test"
    plan = EditPlan(
        version=2,
        clip_id="test_clip_123",
        source={"session": "test_session_abc", "ranges": [(5.0, 10.0), (15.0, 20.0)]},
        layout=[{"t": 0.0, "kind": "split", "camera_ratio": 0.40}],
        camera_crop=[
            CropKeyframe(t=0.0, cx=0.5, cy=0.5, zoom=1.0),
            CropKeyframe(t=2.0, cx=0.6, cy=0.4, zoom=1.5, ease="inOutSine"),
        ],
        audio={"mic_gain_db": 1.5, "duck_game_db": -16.0},
        captions={
            "preset": "hormozi",
            "groups": [
                {"words": [{"w": "Hola", "s": 0.5, "e": 0.8}, {"w": "mundo", "s": 0.9, "e": 1.2}]},
                {"words": [{"w": "increíble", "s": 1.5, "e": 2.2}]},
            ],
        },
    )

    ctx = ExportContext(
        gameplay_path=tmp_path / "gameplay.mp4",
        camera_path=tmp_path / "camara.mp4",
        camera_offset_s=0.125,
        source_fps=Fraction(60, 1),
        voice_spans=[(0.5, 2.2)],
        clip_id="test_clip_123",
        session_id="test_session_abc",
    )

    exporter = FilmCraftExporter()
    res = exporter.export(plan, ctx, out_dir)

    assert res.project_path.exists()
    assert res.project_path.name == "clip.fcproj"
    assert res.duration_s == 10.0  # 5s + 5s = 10s

    with open(res.project_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["format"] == "filmcraft.project"
    assert data["schema_version"] == 17
    assert "project" in data
    assert "items" in data["project"]

    seq_item = None
    for item in data["project"]["items"].values():
        if "Sequence" in item.get("kind", {}):
            seq_item = item["kind"]["Sequence"]
            break

    assert seq_item is not None
    assert seq_item["settings"]["width"] == 1080
    assert seq_item["settings"]["height"] == 1920
    assert len(seq_item["video_tracks"]) == 3
    assert len(seq_item["audio_tracks"]) == 3
    assert len(seq_item["markers"]) == 2
    assert len(seq_item["video_tracks"][0]["items"]) == 2  # 2 rangos en V1
    assert len(seq_item["video_tracks"][1]["items"]) == 2  # 2 rangos en V2


def test_filmcraft_cli_inspection(tmp_path: Path):
    """Verifica que el CLI oficial de FilmCraft pueda inspeccionar el proyecto generado sin fallar."""
    fc_cli = Path(r"C:\Users\sebas\AppData\Local\Programs\ArtCraft\FilmCraft\filmcraft-cli.exe")
    if not fc_cli.exists():
        pytest.skip("filmcraft-cli no encontrado")

    out_dir = tmp_path / "fc_cli_test"
    plan = EditPlan(
        version=2,
        clip_id="cli_clip",
        source={"session": "session_cli", "ranges": [(1.0, 4.0)]},
        layout=[{"t": 0.0, "kind": "split", "camera_ratio": 0.40}],
    )
    ctx = ExportContext(
        gameplay_path=tmp_path / "gameplay.mp4",
        camera_path=tmp_path / "camara.mp4",
        source_fps=Fraction(60, 1),
        clip_id="cli_clip",
    )
    res = FilmCraftExporter().export(plan, ctx, out_dir)

    # Ejecutar filmcraft-cli inspect project
    proc = subprocess.run(
        [str(fc_cli), "--project", str(res.project_path), "inspect"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"filmcraft-cli falló: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert "project" in data
    assert "sequence" in data
    assert data["sequence"]["settings"]["width"] == 1080
    assert data["sequence"]["settings"]["height"] == 1920


def test_otio_exporter(tmp_path: Path):
    out_dir = tmp_path / "otio_test"
    plan = EditPlan(
        version=2,
        clip_id="otio_clip",
        source={"session": "session_otio", "ranges": [(2.0, 6.0)]},
    )
    ctx = ExportContext(
        gameplay_path=tmp_path / "gameplay.mp4",
        camera_path=tmp_path / "camara.mp4",
        source_fps=Fraction(60, 1),
        clip_id="otio_clip",
    )
    res = OtioExporter().export(plan, ctx, out_dir)

    assert res.project_path.exists()
    assert res.project_path.name == "clip.otio"
    with open(res.project_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["OTIO_SCHEMA"] == "Timeline.1"
    assert len(data["tracks"]["children"]) == 4
