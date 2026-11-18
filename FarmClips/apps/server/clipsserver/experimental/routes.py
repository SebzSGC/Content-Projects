"""Local-only integration for VOD analysis and editorial review."""
import asyncio
import json
import logging
import os
import time
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from ..orchestrator.db import stable_hash
from .detector import CONFIG, digest, dump, render_preview, run_local
from .editorial import Segment, calibrate, visible_groups
from .storage import Store

LOGGER = logging.getLogger(__name__)
Category = Literal["llamada", "humor", "susto", "historia", "combate", "tarea", "resultado", "otro"]


class Start(BaseModel):
    source: str
    fresh: bool = False


class Review(BaseModel):
    decision: Literal["interesante", "no_interesante", "dudoso"]
    version: Literal["v1", "v2"]
    category: Category | None = None
    notes: str = Field(default="", max_length=3000)
    segment: Segment | None = None
    operation: str = Field(min_length=1, max_length=80)
    expected: int | None = None


def frozen_result(root, sha256):
    if root is None:
        return None
    manifest_path = root / "manifiesto_congelacion.json"
    if not manifest_path.is_file():
        return None
    manifest = json.loads(manifest_path.read_text())
    vod = next((row for row in manifest["vods"] if row["sha256"] == sha256), None)
    if vod is None:
        return None
    result = {"vod_id": vod["vod_id"], "sha256": sha256, "origin": 0,
              "coverage": {"audio": "RMS histórico", "video": "Fotogramas históricos",
                           "dialogue": None, "narrative": None}, "frozen": {}}
    for version in ("v1", "v2"):
        name = f"fase_preintegracion_{version}/candidatos.json"
        path = root / "referencias" / name
        entry = next(row for row in manifest["artefactos"] if row["origen"] == name)
        if digest(path) != entry["sha256"]:
            raise ValueError(f"Hash incorrecto en el ranking {version}")
        data = json.loads(path.read_text())
        item = next(row for row in data["vods"] if row["vod_id"] == vod["vod_id"])
        result["duration"] = item["duracion_seg"]
        result[version] = item["candidatos"]
        result["frozen"][version] = {"version": data["version"], "sha256": entry["sha256"]}
    return result


def require_local(request: Request):
    hosts = {"127.0.0.1", "localhost", "::1"}
    origin = request.headers.get("origin")
    try:
        local_origin = origin is None or urlsplit(origin).hostname in hosts
    except ValueError:
        local_origin = False
    if request.url.hostname not in hosts or not local_origin:
        raise HTTPException(403, "El panel experimental solo está disponible en localhost")


def source_signature(path):
    stat = path.stat()
    return f"{stat.st_dev}:{stat.st_ino}:{stat.st_size}:{stat.st_mtime_ns}"


def register(app, orch):
    directory = os.environ.get("CLIPS_HIGHLIGHTS_VOD_DIR")
    root = Path(directory).expanduser().resolve() if directory else None
    max_duration = int(os.environ.get("CLIPS_HIGHLIGHTS_MAX_DURATION_SEC", "28800"))
    freeze = os.environ.get("CLIPS_HIGHLIGHTS_FREEZE")
    freeze_root = Path(freeze).expanduser().resolve() if freeze else None
    store = Store(orch.db.db_path)
    store.migrate()
    router = APIRouter(prefix="/experimental/highlights/v1", dependencies=[Depends(require_local)])
    active = set()
    preview_slot = asyncio.Semaphore(1)
    app.state.highlight_jobs = active

    def sources():
        if root is None or not root.is_dir():
            return {}
        return {p.name: p for p in sorted(root.iterdir())
                if p.suffix.lower() == ".mp4" and p.is_file() and p.resolve().parent == root}

    def result_path(run_id):
        return app.state.settings.data_dir / "highlights" / run_id / "result.json"

    def get_run(run_id):
        row = store.run(run_id)
        if row is None:
            raise HTTPException(404, "Ejecución desconocida")
        return row

    def get_result(run_id):
        row = get_run(run_id)
        if row["state"] != "DONE":
            raise HTTPException(409, "La ejecución aún no está disponible")
        return json.loads(result_path(run_id).read_text())

    async def process(run_id, path, sha256, fresh):
        started = time.monotonic()
        output = result_path(run_id)
        try:
            output.parent.mkdir(parents=True, exist_ok=True)
            frozen = None if fresh else await asyncio.to_thread(frozen_result, freeze_root, sha256)
            if frozen:
                dump(output, frozen)
            else:
                cached = await orch._run_cached_cpu(
                    run_id, "experimental_highlights",
                    {"sha256": sha256, "config": CONFIG, "mode": "local" if fresh else "fallback",
                     "duration_limit": max_duration}, output, run_local,
                    str(path), sha256, str(output), max_duration,
                )
                if cached != output:
                    dump(output, json.loads(cached.read_text()))
            state, error = "DONE", None
        except ValueError as exc:
            state, error = "FAILED", str(exc)
        except Exception:
            LOGGER.exception("Fallo de highlights %s", run_id)
            state, error = "FAILED", "Falló el análisis local. Consulta el registro del servidor."
        with store.connect(write=True) as db:
            db.execute("UPDATE highlight_runs SET state=?, error=?, elapsed=? WHERE id=?",
                       (state, error, time.monotonic() - started, run_id))
        orch.events.publish("experimental_highlights", run_id=run_id, state=state, message=error)

    @router.get("/sources")
    def list_sources():
        return {"sources": list(sources()), "configured": root is not None}

    @router.get("/runs")
    def list_runs():
        with store.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM highlight_runs ORDER BY rowid DESC")]

    @router.post("/runs", status_code=202)
    async def start(body: Start):
        path = sources().get(body.source)
        if path is None:
            raise HTTPException(404, "Selecciona un MP4 dentro de la biblioteca local")
        if active:
            raise HTTPException(409, "Ya hay un análisis experimental en ejecución")
        signature = source_signature(path)
        sha256 = await asyncio.to_thread(digest, path)
        if signature != source_signature(path):
            raise HTTPException(409, "El VOD cambió mientras se calculaba su hash")
        manifest = freeze_root / "manifiesto_congelacion.json" if freeze_root and not body.fresh else None
        manifest_hash = digest(manifest) if manifest and manifest.is_file() else None
        mode = "local" if body.fresh else "prefer_frozen"
        run_id = stable_hash({"sha256": sha256, "mode": mode, "config": CONFIG,
                              "freeze": manifest_hash, "duration_limit": max_duration})
        old = store.run(run_id)
        if old and old["state"] == "DONE" and result_path(run_id).is_file():
            with store.connect(write=True) as db:
                db.execute("UPDATE highlight_runs SET source=?, source_signature=? WHERE id=?",
                           (path.name, signature, run_id))
            return get_run(run_id)
        if active:
            raise HTTPException(409, "Ya hay un análisis experimental en ejecución")
        with store.connect(write=True) as db:
            db.execute("INSERT OR REPLACE INTO highlight_runs(id,source,sha256,mode,state,source_signature) VALUES(?,?,?,?,?,?)",
                       (run_id, path.name, sha256, mode, "RUNNING", signature))
        task = asyncio.create_task(process(run_id, path, sha256, body.fresh))
        active.add(task)
        task.add_done_callback(active.discard)
        return get_run(run_id)

    @router.get("/runs/{run_id}")
    def status(run_id: str):
        return get_run(run_id)

    def get_source(run_id):
        row = get_run(run_id)
        path = sources().get(row["source"])
        if path is None:
            raise HTTPException(404, "VOD no disponible")
        if source_signature(path) != row["source_signature"]:
            raise HTTPException(409, "La fuente cambió. Vuelve a analizar el VOD.")
        return path

    @router.get("/runs/{run_id}/media")
    def media(run_id: str):
        return FileResponse(get_source(run_id), media_type="video/mp4", headers={"Cache-Control": "no-store"})

    @router.get("/runs/{run_id}/preview")
    async def preview(run_id: str, start: float = Query(ge=0), end: float = Query(gt=0)):
        data = get_result(run_id)
        if not 0 <= start < end <= data["duration"] or not .05 <= end - start <= 180:
            raise HTTPException(422, "La vista previa admite entre 0,05 y 180 segundos dentro del VOD")
        source = get_source(run_id)
        key = stable_hash({"start": start, "end": end, "format": "review_h264_aac_v1"})
        output = result_path(run_id).parent / "previews" / (key + ".mp4")
        if not output.is_file():
            async with preview_slot:
                try:
                    await orch.cpu_pool.run(render_preview, str(source), start, end - start, str(output))
                except Exception as exc:
                    LOGGER.exception("Fallo de preview %s", run_id)
                    raise HTTPException(422, "FFmpeg no pudo preparar este corte") from exc
        return FileResponse(output, media_type="video/mp4", headers={"Cache-Control": "no-store"})

    def ranked(data, ranking, profile):
        rows = data[ranking]
        if not profile:
            return rows
        with store.connect() as db:
            entry = db.execute("SELECT payload FROM highlight_profiles WHERE id=?", (profile,)).fetchone()
        if not entry:
            raise HTTPException(404, "Perfil desconocido")
        saved = json.loads(entry["payload"])
        categories = saved["candidate_categories"]
        weights = saved["weights"]
        def adjustment(row):
            return weights.get(categories.get(row["id"]), 0)
        ordered = sorted(({**row, "ajuste_personalizado": adjustment(row)} for row in rows),
                         key=lambda row: (-(row["puntuacion"] + row["ajuste_personalizado"]), row["puesto"]))
        return [{**row, "puesto_personalizado": number} for number, row in enumerate(ordered, 1)]

    @router.get("/runs/{run_id}/candidates")
    def candidates(run_id: str, ranking: Literal["v1", "v2"] = "v1",
                   budget: int = Query(12, ge=0, le=120), show_all: bool = False,
                   profile: str | None = None):
        data = get_result(run_id)
        ordered = ranked(data, ranking, profile)
        groups = visible_groups(data["v1"], ordered, data["duration"], budget)
        raw_count = len(ordered)
        selected = {member for group in groups for member in group["members"]}
        groups_by_candidate = {group["representative"]: group for group in groups}
        by_id = {row["id"]: row for row in data["v2"]}
        latest = {review["candidate"]: review for review in store.history(run_id)}
        return {**{k: v for k, v in data.items() if k not in ("v1", "v2")},
                "experimental_api_calls": 0,
                "total": raw_count, "visible_groups": len(groups), "hidden_candidates": raw_count - len(selected),
                "rows": [{**row, "v2_cut": by_id[row["id"]]["intervalo_corte_propuesto_seg"],
                          "review": latest.get(row["id"]), "group": groups_by_candidate.get(row["id"])}
                         for row in ordered if show_all or row["id"] in groups_by_candidate]}

    @router.get("/runs/{run_id}/frame/{second}")
    def frame(run_id: str, second: int):
        data = get_result(run_id)
        if data.get("frozen"):
            raise HTTPException(404, "Consulta el fotograma en el reproductor del VOD")
        path = result_path(run_id).parent / "frames" / f"{second:06d}.jpg"
        if not path.is_file():
            raise HTTPException(404, "Fotograma no disponible")
        return FileResponse(path, media_type="image/jpeg")

    @router.get("/runs/{run_id}/history/{candidate}")
    def history(run_id: str, candidate: str):
        get_run(run_id)
        return store.history(run_id, candidate)

    @router.post("/runs/{run_id}/reviews/{candidate}")
    def review(run_id: str, candidate: str, body: Review):
        data = get_result(run_id)
        row = next((r for r in data[body.version] if r["id"] == candidate), None)
        if not row:
            raise HTTPException(404, "Candidato desconocido")
        if body.segment and body.segment.end > data["duration"]:
            raise HTTPException(422, "El final excede la duración del VOD")
        payload = body.model_dump(exclude={"operation", "expected"})
        payload.update({"sha256": data["sha256"], "vod_id": data["vod_id"], "config": CONFIG,
                        "detector": data.get("frozen", {}).get(body.version, {}).get("version", CONFIG["version"]),
                        "signals": row["senales"],
                        "proposal": [row["inicio_seg"], row["fin_seg"]] if body.version == "v1"
                        else row["intervalo_corte_propuesto_seg"]})
        try:
            seq = store.save_review(run_id, candidate, body.operation, body.expected, payload)
        except ValueError as exc:
            raise HTTPException(409, str(exc)) from exc
        return {"seq": seq}

    @router.get("/runs/{run_id}/export")
    def export(run_id: str):
        data = get_result(run_id)
        return {"contract": "farmclips_highlights_review_v1", "source": get_run(run_id),
                "config": CONFIG, "result": data, "reviews": store.history(run_id)}

    @router.post("/feedback/import")
    def import_feedback():
        if freeze_root is None:
            raise HTTPException(409, "Configura el paquete de cierre")
        return import_history(store, freeze_root)

    @router.get("/feedback")
    def historical_feedback(candidate: str | None = None):
        query = "SELECT * FROM highlight_revisions WHERE run_id IS NULL"
        params = ()
        if candidate is not None:
            query += " AND candidate=?"
            params = (candidate,)
        with store.connect() as db:
            return [{**dict(row), "payload": json.loads(row["payload"])}
                    for row in db.execute(query + " ORDER BY seq", params)]

    @router.get("/profiles")
    def profiles():
        with store.connect() as db:
            return [json.loads(row["payload"]) for row in db.execute("SELECT payload FROM highlight_profiles ORDER BY rowid DESC")]

    @router.post("/profiles")
    def preview_profile():
        with store.connect(write=True) as db:
            # One vote per source and candidate, regardless of review count or run variant.
            latest = {}
            for row in db.execute("SELECT * FROM highlight_revisions WHERE run_id IS NOT NULL ORDER BY seq"):
                item = json.loads(row["payload"])
                latest[item["sha256"], row["candidate"]] = (row["seq"], row["candidate"], item)
            entries = sorted(latest.values())
            weights = calibrate([item for _, _, item in entries])
            if not weights or not any(weights.values()):
                return {"id": None, "reason": "Feedback insuficiente para ajustar el baseline",
                        "usable_labels": len(entries), "weights": weights}
            payload = {"algorithm": "category_calibration_v1", "weights": weights,
                       "candidate_categories": {candidate: item["category"] for _, candidate, item in entries
                                                if item.get("category") and item["category"] in weights},
                       "revision_ids": [seq for seq, _, _ in entries],
                       "scope": "comparación descriptiva sobre candidatos ya categorizados"}
            identifier = stable_hash(payload)
            payload["id"] = identifier
            db.execute("INSERT OR IGNORE INTO highlight_profiles VALUES(?,?)", (identifier, json.dumps(payload)))
            return payload

    app.include_router(router)


def import_history(store, root):
    try:
        index = json.loads((root / "manifiesto_congelacion.json").read_text())
        records = []
        for version, key, path in (
            ("v1", "decision", root / "referencias/fase_preintegracion_v1/revision_humana_recibida.json"),
            ("v2", "decision_v2", root / "revision_humana_v2_001.json"),
        ):
            sha = digest(path)
            if not any(row["sha256"] == sha and row.get("copia", "").endswith(path.name) for row in index["artefactos"]):
                raise ValueError(f"Hash no registrado para {version}")
            for row in json.loads(path.read_text())["candidatos"]:
                if row.get(key):
                    records.append((row["id"], f"revision_exportada_{version}", f"{sha}:{row['id']}", row))
        audit = root.parent / "auditoria_temporal_v1" / "analisis_gpt_auditados"
        paths = sorted(audit.glob("*.json"))
        if len(paths) == 12:
            for path in paths:
                clip_id = path.stem
                records.append((clip_id, "published_positive_example", f"published:{clip_id}",
                                {"clip_id": clip_id, "audit_sha256": digest(path), "reference": path.name}))
    except (OSError, KeyError, ValueError) as exc:
        raise HTTPException(422, "Paquete de feedback no válido") from exc
    with store.connect(write=True) as db:
        changes = db.total_changes
        db.executemany("INSERT OR IGNORE INTO highlight_revisions(candidate,provenance,operation,payload) VALUES(?,?,?,?)",
                       [(candidate, provenance, operation, json.dumps(payload, ensure_ascii=False))
                        for candidate, provenance, operation, payload in records])
        return {"imported": db.total_changes - changes, "available": len(records)}
