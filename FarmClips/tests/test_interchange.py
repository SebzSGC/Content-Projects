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
    SessionClipSpec,
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
    assert seq_item["video_tracks"][0]["name"] == "V1 Cámara"
    assert seq_item["video_tracks"][1]["name"] == "V2 Gameplay"
    assert seq_item["video_tracks"][2]["name"] == "V3 Overlays"
    assert len(seq_item["video_tracks"][0]["items"]) == 2  # 2 rangos en V1 Cámara
    assert len(seq_item["video_tracks"][1]["items"]) == 2  # 2 rangos en V2 Gameplay
    assert len(seq_item["caption_tracks"]) == 1  # Pista nativa C1 Subtitles
    assert len(seq_item["caption_tracks"][0]["captions"]) == 2  # 2 subtítulos editables
    assert seq_item["caption_tracks"][0]["name"] == "Subtitles"
    assert seq_item["caption_tracks"][0]["style"]["font"] == "Montserrat"
    assert seq_item["caption_tracks"][0]["style"]["size"] == 80.0
    assert seq_item["caption_tracks"][0]["style"]["outline"] == 8.0
    assert seq_item["caption_tracks"][0]["style"]["align"] == "Center"
    assert seq_item["caption_tracks"][0]["style"]["anchor"] == "Middle"

    # Verificar que los keyframes de motion de la cámara estén en mediaTime (source_in + offset)
    v1_first_clip = seq_item["video_tracks"][0]["items"][0]
    src_in = v1_first_clip["source_in"]
    motion_eff = next(e for e in v1_first_clip["effects"] if e["effect"] == "motion")
    pos_kfs = motion_eff["params"]["position"]["keyframes"]
    assert len(pos_kfs) > 0
    # Cada keyframe debe ser >= source_in
    assert pos_kfs[0]["time"] >= src_in


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


def test_filmcraft_session_exporter_e2e(tmp_path: Path):
    out_dir = tmp_path / "session_export"
    clip_a = SessionClipSpec(
        clip_id="clip_a",
        plan=EditPlan(
            version=2,
            clip_id="clip_a",
            source={"session": "ses_1", "ranges": [(10.0, 15.0), (18.0, 22.0)]},
            layout=[{"t": 0.0, "kind": "split", "camera_ratio": 0.40}],
            captions={
                "preset": "hormozi",
                "groups": [{"words": [{"w": "Clip", "s": 0.2, "e": 0.6}, {"w": "uno", "s": 0.7, "e": 1.1}]}],
            },
        ),
        title="Victoria épica",
        rank_order=1,
        score=92.0,
        reason="Triple kill",
        start_s=10.0,
        end_s=22.0,
        voice_spans=[(0.2, 1.1)],
    )
    clip_b = SessionClipSpec(
        clip_id="clip_b",
        plan=EditPlan(
            version=2,
            clip_id="clip_b",
            source={"session": "ses_1", "ranges": [(40.0, 50.0)]},
            layout=[{"t": 0.0, "kind": "split", "camera_ratio": 0.40}],
        ),
        title="Risa en vivo",
        rank_order=2,
        score=81.0,
        reason="Reacción graciosa",
        start_s=40.0,
        end_s=50.0,
    )
    clip_overlap = SessionClipSpec(
        clip_id="clip_c",
        plan=EditPlan(
            version=2,
            clip_id="clip_c",
            source={"session": "ses_1", "ranges": [(14.0, 25.0)]},
            layout=[{"t": 0.0, "kind": "split", "camera_ratio": 0.40}],
        ),
        title="Solapado",
        rank_order=3,
        score=75.0,
        reason="Solapa con clip A",
        start_s=14.0,
        end_s=25.0,
    )

    ctx = ExportContext(
        gameplay_path=tmp_path / "gameplay.mp4",
        camera_path=tmp_path / "camara.mp4",
        camera_offset_s=0.5,
        source_fps=Fraction(60, 1),
        session_id="ses_1",
        session_title="Partida Nocturna",
        gameplay_duration_s=120.0,
        camera_duration_s=120.0,
        gameplay_width=1920,
        gameplay_height=1080,
    )

    res = FilmCraftExporter().export_session([clip_a, clip_b, clip_overlap], ctx, out_dir)
    assert res.project_path.exists()
    assert res.project_path.name == "session.fcproj"
    assert res.duration_s == 120.0

    with open(res.project_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert data["format"] == "filmcraft.project"
    assert len(data["view"]["open_sequences"]) == 4  # 1 master + 3 sub-secuencias

    active_id = data["view"]["active_sequence"]
    master_seq = data["project"]["items"][str(active_id)]["kind"]["Sequence"]
    assert master_seq["settings"]["width"] == 1920
    assert master_seq["settings"]["height"] == 1080
    assert len(master_seq["markers"]) == 3

    # V1 VOD Gameplay, V2 VOD Cámara (Ref), V3 Clips, V4 Clips #2 (por solapamiento de clip_c)
    assert len(master_seq["video_tracks"]) == 4
    v3_items = master_seq["video_tracks"][2]["items"]
    v4_items = master_seq["video_tracks"][3]["items"]
    # clip_a tiene 2 rangos + clip_b tiene 1 rango => 3 ítems en V3; clip_c en V4
    assert len(v3_items) == 3
    assert len(v4_items) == 1
    assert v3_items[0]["start"] == seconds_to_ticks(10.0, fps=Fraction(60, 1))
    assert v3_items[1]["start"] == seconds_to_ticks(18.0, fps=Fraction(60, 1))
    assert v3_items[1]["source_in"] == seconds_to_ticks(5.0, fps=Fraction(60, 1))

    # Verificar que los ítems de V3 apuntan a sub-secuencias 1080x1920 distintas
    sub_item_a = data["project"]["items"][str(v3_items[0]["item"])]["kind"]["Sequence"]
    assert sub_item_a["settings"]["width"] == 1080
    assert sub_item_a["settings"]["height"] == 1920


def test_filmcraft_session_cli_inspection(tmp_path: Path):
    """Verifica que filmcraft-cli inspeccione sin errores un .fcproj multi-secuencia de sesión."""
    fc_cli = Path(r"C:\Users\sebas\AppData\Local\Programs\ArtCraft\FilmCraft\filmcraft-cli.exe")
    if not fc_cli.exists():
        pytest.skip("filmcraft-cli no encontrado")

    out_dir = tmp_path / "fc_session_cli"
    clips = [
        SessionClipSpec(
            clip_id="c1",
            plan=EditPlan(version=2, clip_id="c1", source={"session": "s1", "ranges": [(5.0, 10.0), (12.0, 16.0)]}),
            title="Momento 1",
            rank_order=1,
            start_s=5.0,
            end_s=16.0,
        ),
        SessionClipSpec(
            clip_id="c2",
            plan=EditPlan(version=2, clip_id="c2", source={"session": "s1", "ranges": [(30.0, 38.0)]}),
            title="Momento 2",
            rank_order=2,
            start_s=30.0,
            end_s=38.0,
        ),
    ]
    ctx = ExportContext(
        gameplay_path=tmp_path / "gameplay.mp4",
        camera_path=tmp_path / "camara.mp4",
        source_fps=Fraction(60, 1),
        session_id="s1",
        session_title="Test Sesión",
        gameplay_duration_s=90.0,
    )
    res = FilmCraftExporter().export_session(clips, ctx, out_dir)

    proc = subprocess.run(
        [str(fc_cli), "--project", str(res.project_path), "inspect"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert proc.returncode == 0, f"filmcraft-cli falló: {proc.stderr}"
    data = json.loads(proc.stdout)
    assert data["sequence"]["settings"]["width"] == 1920
    assert data["sequence"]["settings"]["height"] == 1080
    assert len(data["sequence"]["video"]) == 3
