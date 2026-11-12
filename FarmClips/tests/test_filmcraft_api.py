"""Pruebas unitarias para endpoints de integración con FilmCraft en FastAPI."""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from clipsserver.api.routes import create_app
from clipsserver.config import ServerSettings
from clipsserver.filmcraft import FilmCraftLauncher, OpenFilmCraftResponse
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path):
    settings = ServerSettings(data_dir=tmp_path / "data")
    app = create_app(settings, use_process_pool=False, enable_drive_watcher=False)

    # Insertar sesión y clip de prueba directamente en orch.db
    orch = app.state.orchestrator
    srow = orch.db.create_session(
        title="Sesión Test",
        gameplay_path=str(tmp_path / "gameplay.mp4"),
        camera_path=str(tmp_path / "camara.mp4"),
        recording_name="rec_test",
    )

    dummy_plan = {
        "version": 2,
        "clip_id": "clip_456",
        "source": {"session": srow["id"], "ranges": [(1.0, 5.0)]},
        "layout": [{"t": 0.0, "kind": "split", "camera_ratio": 0.40}],
        "audio": {"mic_gain_db": 1.0, "duck_game_db": -12.0},
        "captions": {
            "preset": "hormozi",
            "groups": [{"words": [{"w": "test", "s": 1.5, "e": 2.0}]}],
        },
    }

    orch.db.upsert_clip(
        clip_id="clip_456",
        session_id=srow["id"],
        rank_order=1,
        start_sec=1.0,
        end_sec=5.0,
        overlay_title="Clip Test",
        post_title="Post Test",
        hashtags=["#gaming"],
        reason="Test",
        llm_score=80.0,
        signal_score=90.0,
        final_score=85.0,
        curated_json="{}",
        editplan_json=json.dumps(dummy_plan),
    )

    dummy_plan_2 = {
        "version": 2,
        "clip_id": "clip_789",
        "source": {"session": srow["id"], "ranges": [(12.0, 18.0)]},
        "layout": [{"t": 0.0, "kind": "split", "camera_ratio": 0.40}],
    }
    orch.db.upsert_clip(
        clip_id="clip_789",
        session_id=srow["id"],
        rank_order=2,
        start_sec=12.0,
        end_sec=18.0,
        overlay_title="Clip Dos",
        post_title="Post Dos",
        hashtags=["#clutch"],
        reason="Test 2",
        llm_score=75.0,
        signal_score=80.0,
        final_score=78.0,
        curated_json="{}",
        editplan_json=json.dumps(dummy_plan_2),
    )

    app.state.test_session_id = srow["id"]

    with TestClient(app) as test_client:
        yield test_client


def test_filmcraft_status_endpoint(client):
    res = client.get("/integrations/filmcraft/status")
    assert res.status_code == 200
    data = res.json()
    assert "installed" in data
    assert "supported_version" in data
    assert data["supported_version"] == "0.20.1"
    assert "bridge_up" in data


def test_filmcraft_export_endpoint(client):
    res = client.post("/clips/clip_456/filmcraft/export?format=filmcraft")
    assert res.status_code == 200
    data = res.json()
    assert data["exporter"] == "filmcraft"
    assert Path(data["project_path"]).exists()
    assert data["project_path"].endswith("clip.fcproj")


def test_filmcraft_export_otio_endpoint(client):
    res = client.post("/clips/clip_456/filmcraft/export?format=otio")
    assert res.status_code == 200
    data = res.json()
    assert data["exporter"] == "otio"
    assert Path(data["project_path"]).exists()
    assert data["project_path"].endswith("clip.otio")


def test_filmcraft_open_endpoint(client):
    with patch.object(
        FilmCraftLauncher,
        "open_project",
        return_value=OpenFilmCraftResponse(
            project_path="mock/path/clip.fcproj",
            launched=True,
            reused_instance=False,
        ),
    ):
        res = client.post("/clips/clip_456/filmcraft/open")
        assert res.status_code == 200
        data = res.json()
        assert data["launched"] is True
        assert data["reused_instance"] is False


def test_filmcraft_download_endpoint(client):
    res = client.get("/clips/clip_456/filmcraft/download?format=filmcraft")
    assert res.status_code == 200
    assert "attachment" in res.headers.get("content-disposition", "") or "clip_456.fcproj" in res.headers.get("content-disposition", "")
    assert len(res.content) > 0


def test_filmcraft_reveal_endpoint(client):
    with patch("subprocess.Popen") as mock_popen:
        res = client.post("/clips/clip_456/filmcraft/reveal")
        assert res.status_code == 200
        data = res.json()
        assert data["ok"] is True
        assert "path" in data
        assert mock_popen.called


def test_filmcraft_launcher_windows_helpers(tmp_path):
    from clipsserver.filmcraft import (
        _build_launch_args,
        find_filmcraft_hwnd_windows,
        has_visible_filmcraft_window,
        launch_filmcraft_windows,
    )

    # find_filmcraft_hwnd_windows & has_visible_filmcraft_window can be called safely
    hwnd = find_filmcraft_hwnd_windows()
    assert hwnd is None or isinstance(hwnd, int)
    assert isinstance(has_visible_filmcraft_window(), bool)

    dummy_app = tmp_path / "filmcraft.exe"
    dummy_app.write_text("dummy")
    dummy_proj = tmp_path / "test.fcproj"
    dummy_proj.write_text("{}")

    assert _build_launch_args(dummy_proj, 9876) == ["--control", "9876", str(dummy_proj)]
    assert _build_launch_args(dummy_proj, None) == [str(dummy_proj)]

    with patch("os.startfile", return_value=None) as mock_startfile:
        # If CreateProcess fails, it falls back to os.startfile with --control
        ok = launch_filmcraft_windows(dummy_app, dummy_proj, bridge_port=9876)
        assert ok is True
        if mock_startfile.called:
            _, kwargs = mock_startfile.call_args
            assert "--control 9876" in kwargs.get("arguments", "")


def test_filmcraft_launcher_open_project_passes_control_bridge(tmp_path, monkeypatch):
    dummy_app = tmp_path / "filmcraft.exe"
    dummy_app.write_text("dummy")
    dummy_cli = tmp_path / "filmcraft-cli.exe"
    dummy_cli.write_text("dummy")
    dummy_proj = tmp_path / "clip.fcproj"
    dummy_proj.write_text("{}")

    token = "a" * 64
    monkeypatch.setenv("FILMCRAFT_CONTROL_TOKEN", token)

    launcher = FilmCraftLauncher(
        app_path=str(dummy_app),
        cli_path=str(dummy_cli),
        bridge_port=9888,
    )

    with (
        patch.object(launcher, "is_bridge_listening", return_value=False),
        patch("clipsserver.filmcraft.is_filmcraft_process_running", return_value=False),
        patch("clipsserver.filmcraft.cleanup_orphaned_recovery"),
        patch("clipsserver.filmcraft.register_windows_association"),
        patch("clipsserver.filmcraft._async_bring_to_front"),
        patch("clipsserver.filmcraft.launch_filmcraft_windows", return_value=True) as mock_launch,
    ):
        res = launcher.open_project(dummy_proj)
        assert res.launched is True
        assert res.reused_instance is False
        mock_launch.assert_called_once()
        _, kwargs = mock_launch.call_args
        assert kwargs.get("bridge_port") == 9888


def test_ensure_control_token_reads_user_env_fallback(tmp_path, monkeypatch):
    from clipsserver.filmcraft import ensure_control_token

    monkeypatch.delenv("FILMCRAFT_CONTROL_TOKEN", raising=False)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    reg_token = "b" * 64

    with patch("clipsserver.filmcraft._read_user_env_token", return_value=reg_token):
        tok = ensure_control_token()

    assert tok == reg_token
    assert (tmp_path / "FilmCraft" / ".farmclips_control_token").read_text(encoding="utf-8") == reg_token


def test_session_filmcraft_export_all_and_filtered(client):
    sid = client.app.state.test_session_id

    # 1. Exportar todos los clips de la sesión
    res_all = client.post(f"/sessions/{sid}/filmcraft/export")
    assert res_all.status_code == 200
    data_all = res_all.json()
    assert data_all["clips_count"] == 2
    assert set(data_all["clip_ids"]) == {"clip_456", "clip_789"}
    assert data_all["project_path"].endswith("session.fcproj")
    assert Path(data_all["project_path"]).exists()

    # 2. Exportar solo 1 clip elegido por el usuario
    res_one = client.post(f"/sessions/{sid}/filmcraft/export", json={"clip_ids": ["clip_789"]})
    assert res_one.status_code == 200
    data_one = res_one.json()
    assert data_one["clips_count"] == 1
    assert data_one["clip_ids"] == ["clip_789"]

    # 3. Selección vacía debe retornar 400
    res_empty = client.post(f"/sessions/{sid}/filmcraft/export", json={"clip_ids": []})
    assert res_empty.status_code == 400


def test_session_filmcraft_open_download_reveal(client):
    sid = client.app.state.test_session_id

    with patch.object(
        FilmCraftLauncher,
        "open_project",
        return_value=OpenFilmCraftResponse(
            project_path="mock/path/session.fcproj",
            launched=True,
            reused_instance=False,
        ),
    ):
        res_open = client.post(f"/sessions/{sid}/filmcraft/open", json={"clip_ids": ["clip_456"]})
        assert res_open.status_code == 200
        d = res_open.json()
        assert d["launched"] is True
        assert d["clips_count"] == 1
        assert d["clip_ids"] == ["clip_456"]

    res_dl = client.get(f"/sessions/{sid}/filmcraft/download?clip_ids=clip_456,clip_789")
    assert res_dl.status_code == 200
    assert f"{sid}_master.fcproj" in res_dl.headers.get("content-disposition", "")
    assert len(res_dl.content) > 0

    with patch("subprocess.Popen") as mock_popen:
        res_rev = client.post(f"/sessions/{sid}/filmcraft/reveal", json={"clip_ids": ["clip_456"]})
        assert res_rev.status_code == 200
        assert res_rev.json()["ok"] is True
        assert mock_popen.called
