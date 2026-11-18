import argparse
import asyncio
import json
import shutil
import tempfile
from pathlib import Path

from clipscore.domain import PreparedMedia, SessionState, SyncResult
from clipseditplan import EditPlan, OutputPlan, SourcePlan
from clipsmedia.ffmpeg import probe, verify_final_av_duration
from clipsserver.api import create_app
from clipsserver.config import ServerSettings
from clipsserver.experimental.detector import digest
from clipsserver.orchestrator.engine import FinalDurationError

async def verify(root: Path, data_dir: Path, out: Path):
    inventory = json.loads((root / "vinculacion_vods_v1/vod_index.json").read_text())["vods"]
    manifest = json.loads((root / "cierre_preintegracion_v1/manifiesto_congelacion.json").read_text())
    reference = json.loads((root / "fase_preintegracion_v2/montaje_referencia.json").read_text())
    v1 = json.loads((root / "fase_preintegracion_v1/candidatos.json").read_text())["vods"]
    v2 = json.loads((root / "fase_preintegracion_v2/candidatos.json").read_text())["vods"]
    for entry in manifest["artefactos"]:
        assert digest(root / entry.get("copia", entry["origen"])) == entry["sha256"]
    assert sum(len(v["candidatos"]) for v in v1) == sum(len(v["candidatos"]) for v in v2) == 787
    assert sum(
        (b-a) > (d-c) for vod in v2 for row in vod["candidatos"]
        for a,b in [row["intervalo_corte_propuesto_seg"]] for c,d in [row["intervalo_v1_seg"]]
    ) == 295
    historical = [tuple(round(v, 3) for v in row["vod_intervalo_seg"])
                  for row in reference["tramos"] if not row["ambiguedad"]]
    inputs = [
        ("vod_5fad77fe76d52cb1", "referencia_plataformas", historical),
        ("vod_7c5c1b1bd9570618", "llamada_individual", [(2301, 2348)]),
        ("vod_c0e9416f054c6109", "referencia_pelotas", [(6294, 6326)]),
    ]
    cfg = ServerSettings(data_dir=data_dir, drive_mode="disabled", use_nvenc=False, use_videotoolbox=True)
    app = create_app(cfg, use_process_pool=False, enable_drive_watcher=False)
    orch = app.state.orchestrator
    await orch.startup(enable_watcher=False)
    try:
        by_id = {row["vod_id"]: row for row in inventory}
        for vod_id, clip_id, ranges in inputs:
            source = by_id[vod_id]
            path = root / source["ruta"]
            assert digest(path) == source["sha256"]
            media = probe(path)
            session = orch.db.create_session(clip_id, str(path), str(path), initial_state=SessionState.PREPARED)
            sid = session["id"]
            prepared = PreparedMedia(session_id=sid, gameplay=media, camera=media, camera_opus_path="",
                                     chunks=[], camera_wav16k="", gameplay_wav16k="", sync=SyncResult())
            orch.db.update_session(sid, prepared_json=prepared.model_dump_json())
            plan = EditPlan(clip_id=clip_id, source=SourcePlan(session=sid, ranges=ranges),
                            output=OutputPlan(w=540, h=960, fps=30, style="hormozi-gaming"))
            state = "REVIEW_SHORT" if plan.total_duration() < 40 else "PLANNED"
            orch.db.upsert_clip(clip_id, sid, 1, ranges[0][0], ranges[-1][1], clip_id, clip_id, [],
                                "Referencia congelada", 0, 0, 0, "{}", editplan_json=plan.model_dump_json(),
                                state=state)
            try:
                result = await orch.render_and_deliver_clip(clip_id, upload_to_drive=False)
            except FinalDurationError:
                print(clip_id, plan.total_duration(), "s, retenido para revisión", flush=True)
            else:
                assert verify_final_av_duration(result, 40)
                destination = out / f"{clip_id}.mp4"
                shutil.copyfile(result, destination)
                print(clip_id, probe(destination).duration, "s", destination, flush=True)
    finally:
        await orch.shutdown()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Verifica las tres referencias congeladas sin llamar al proveedor.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="farmclips-vods-") as folder:
        asyncio.run(verify(args.dataset.resolve(), Path(folder), args.output.resolve()))
