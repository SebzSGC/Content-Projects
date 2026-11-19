"""Encode a montage with the real renderer, then inspect the media across a cut."""
import json
import subprocess

import numpy as np
import pytest
from fastapi.testclient import TestClient

from clipscore.domain import PreparedMedia, SessionState, SignalSeries, SyncResult
from clipseditplan import EditPlan, OutputPlan, SourcePlan
from clipsmedia.ffmpeg import probe, resolve_binary, run_ffmpeg, verify_final_av_duration
from clipsserver.api import create_app
from clipsserver.config import ServerSettings


def test_editorial_montage_renders_ordered_av_and_short_cuts_stay_in_review(tmp_path, monkeypatch):
    monkeypatch.setenv("CLIPS_EXPERIMENTAL_HIGHLIGHTS", "1")
    ffmpeg = resolve_binary("ffmpeg")
    features = subprocess.check_output([ffmpeg, "-hide_banner", "-filters"], text=True, stderr=subprocess.STDOUT)
    if " subtitles " not in features:
        pytest.skip("Se requiere FFmpeg con libass para el render editorial")

    source = tmp_path / "montage_source.mp4"
    run_ffmpeg([
        "-f", "lavfi", "-i", "color=c=red:s=320x180:r=24:d=22",
        "-f", "lavfi", "-i", "sine=f=440:r=48000:d=22",
        "-f", "lavfi", "-i", "color=c=green:s=320x180:r=24:d=12",
        "-f", "lavfi", "-i", "sine=f=550:r=48000:d=12",
        "-f", "lavfi", "-i", "color=c=blue:s=320x180:r=24:d=24",
        "-f", "lavfi", "-i", "sine=f=660:r=48000:d=24",
        "-filter_complex", "[0:v][1:a][2:v][3:a][4:v][5:a]concat=n=3:v=1:a=1[v][a]",
        "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "ultrafast",
        "-c:a", "aac", str(source),
    ])
    media = probe(source)
    settings = ServerSettings(data_dir=tmp_path / "data", drive_mode="disabled",
                              use_nvenc=False, use_videotoolbox=False)
    app = create_app(settings, use_process_pool=False, enable_drive_watcher=False)
    with TestClient(app, base_url="http://localhost") as client:
        db = app.state.orchestrator.db
        session = db.create_session("Prueba audiovisual", str(source), str(source),
                                    initial_state=SessionState.PREPARED)
        sid = session["id"]
        prepared = PreparedMedia(session_id=sid, gameplay=media, camera=media, camera_opus_path="",
                                 chunks=[], camera_wav16k="", gameplay_wav16k="", sync=SyncResult())
        db.update_session(sid, prepared_json=prepared.model_dump_json())
        for name, ranges in (
            ("montage", [(0, 22), (34, 58)]),
            ("individual", [(1, 45)]),
            ("short", [(0, 12)]),
        ):
            plan = EditPlan(clip_id=name, source=SourcePlan(session=sid, ranges=ranges),
                            output=OutputPlan(w=270, h=480, fps=24, style="hormozi-gaming"))
            segments = [
                {"id": f"tramo-{i}", "start": start, "end": end, "event": title,
                 "role": role, "evidence_ids": [f"u000{i}"], "relation": "Secuencia del fixture"}
                for i, ((start, end), title, role) in enumerate(
                    zip(ranges, ("Inicio rojo", "Remate azul"), ("acontecimiento", "remate")), 1
                )
            ] if name == "montage" else []
            curated = {"id": name, "start_id": "u0001", "end_id": "u0002", "start": ranges[0][0],
                       "end": ranges[-1][1], "overlay_title": "Prueba", "post_title": "Prueba",
                       "editorial_segments": segments,
                       "editorial_format": "recopilacion" if segments else "individual"}
            db.upsert_clip(name, sid, 1, ranges[0][0], ranges[-1][1], "Prueba", "Prueba", [], "", 90, .1,
                           70, json.dumps(curated), editplan_json=plan.model_dump_json())
        short = client.post("/clips/short/render", json={"quality": "final", "upload_to_drive": False})
        assert short.status_code == 422
        assert not db.get_clip("short")["final_mp4_path"]
        invalid = client.post("/clips/short/render", json={"quality": "final", "async_mode": True})
        assert invalid.status_code == 422
        files = {}
        for clip_id in ("montage", "individual"):
            response = client.post(f"/clips/{clip_id}/render", json={"quality": "final", "upload_to_drive": False})
            assert response.status_code == 200, response.text
            path = response.json()["mp4_path"]
            assert verify_final_av_duration(path, 40)
            files[clip_id] = path
        assert abs(probe(files["montage"]).duration - 46) < .12
        review = client.post("/experimental/highlights/v1/generated-clips/montage/reviews", json={
            "decision": "interesante", "notes": "La transición funciona", "operation": "fixture-montage-review",
            "proposal": {"start": 0, "end": 58}, "source_ranges": [[0, 22], [34, 58]],
        })
        assert review.status_code == 200
        session_dir = app.state.orchestrator.session_dir(sid)
        (session_dir / "utterances.json").write_text("[]")
        SignalSeries(duration=58, excitement=[0.0] * 58).to_parquet(session_dir / "signals.parquet")
        retimed = client.post("/clips/montage/retime", json={
            "start": 0, "end": 58, "ranges": [[0, 21], [35, 58]], "jump_cuts": False,
        })
        assert retimed.status_code == 200, retimed.text
        assert retimed.json()["editplan"]["source"]["ranges"] == [[0, 21], [35, 58]]
        assert not retimed.json()["clip"]["has_final"]
        old = client.get("/experimental/highlights/v1/generated-clips/montage/reviews").json()
        assert old[0]["payload"]["source_ranges"] == [[0, 22], [34, 58]]


    for t, channel, tone in ((21.7, 0, 440), (22.3, 2, 660)):
        color = np.frombuffer(subprocess.check_output([
            ffmpeg, "-v", "error", "-ss", str(t), "-i", files["montage"], "-frames:v", "1",
            "-vf", "scale=1:1", "-pix_fmt", "rgb24", "-f", "rawvideo", "-",
        ]), dtype=np.uint8)
        pcm = np.frombuffer(subprocess.check_output([
            ffmpeg, "-v", "error", "-ss", str(t), "-i", files["montage"], "-t", "0.2", "-vn", "-ar", "8000", "-ac", "1", "-f", "f32le", "-",
        ]), dtype="<f4")
        peak = np.fft.rfftfreq(len(pcm), 1 / 8000)[np.argmax(np.abs(np.fft.rfft(pcm)))]
        assert int(color.argmax()) == channel
        assert abs(peak - tone) <= 5
