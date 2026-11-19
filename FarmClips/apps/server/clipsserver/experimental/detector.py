"""Local signal extraction and the frozen V1/V2 scoring formulas."""
import hashlib
import json
import math
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

from clipsmedia.ffmpeg import resolve_binary

VERSION = "farmclips_highlights_v1"
CONFIG = {
    "version": VERSION, "peso_acustico": .55, "peso_visual": .45,
    "radio_respaldo_acustico_seg": 4, "radio_nucleo_seg": 2,
    "busqueda_contexto_max_seg_por_lado": 12, "actividad_minima_db_sobre_pausa": 6,
    "percentil_pausa_rms": 25, "pausa_minima_seg": 2,
    "sample_rate": 4000, "seed_stride": 45, "center_separation": 15,
    "audio_track": "0:a:0", "video_track": "0:V:0",
}


def digest(path):
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(block)
    return sha.hexdigest()


def dump(path, data):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False, allow_nan=False), encoding="utf-8")
    temp.replace(path)


def capture(source, second, path):
    if not path.is_file():
        temporary = path.with_suffix(f".{uuid.uuid4().hex}.tmp.jpg")
        subprocess.run(
            [resolve_binary("ffmpeg"), "-nostdin", "-v", "error", "-ss", str(second),
             "-i", str(source), "-map", CONFIG["video_track"], "-frames:v", "1",
             "-vf", "scale=320:-2", "-threads", "1", "-q:v", "3", "-y", str(temporary)],
            check=True, capture_output=True, timeout=30,
        )
        temporary.replace(path)
    with Image.open(path) as image:
        return np.asarray(image.convert("RGB").resize((40, 24)), dtype=np.float32)[5:21, 9:32]


def percentile(sorted_values, x):
    return float(np.searchsorted(sorted_values, x, side="left") / len(sorted_values))


def detect(vid, source, duration, audio_path, folder, pool):
    wave = np.memmap(audio_path, dtype="<f4", mode="r")
    sample_count = len(wave) // 4000
    blocks = wave[:sample_count * 4000].reshape(-1, 4000)
    rms = np.sqrt(np.einsum("ij,ij->i", blocks, blocks) / 4000)
    db = 20 * np.log10(np.maximum(rms, 1e-6))
    if sample_count < 30:
        return [], db, np.array([])
    local = np.pad(db, 6, mode="edge")
    baseline = np.median(np.lib.stride_tricks.sliding_window_view(local, 13), axis=1)
    rise = np.maximum(db - baseline, 0)
    rms_rank = np.searchsorted(np.sort(db), db, side="left") / len(db)
    rise_rank = np.searchsorted(np.sort(rise), rise, side="left") / len(rise)
    acoustic = 0.4 * rms_rank + 0.6 * rise_rank

    # Cover the timeline at regular intervals and refine around local audio peaks.
    seeds = sorted(set(range(18, sample_count - 12, 45)) | {
        int(start + np.argmax(acoustic[start:min(start + 45, sample_count - 12)]))
        for start in range(12, sample_count - 12, 45)
    })

    def measure(second, offsets):
        timestamps = [second + offset for offset in offsets]
        paths = [folder / f"{t:06d}.jpg" for t in timestamps]
        frames = [capture(source, t, p) for t, p in zip(timestamps, paths)]
        deltas = [float(np.mean(np.abs(a-b)) / 255) for a, b in zip(frames, frames[1:])]
        return max(deltas), [
            {"seg_solicitado": t, "ruta": p.name,
             "examinada_por_gpt": False} for t, p in zip(timestamps, paths)
        ]

    coarse = list(pool.map(lambda second: measure(second, [-2, 2]), seeds))
    motion = np.sort([row[0] for row in coarse])
    rows = []
    for second, (delta, evidence) in zip(seeds, coarse):
        sound = float(np.max(acoustic[second-2:second+3]))
        visual = percentile(motion, delta)
        score = 0.55 * sound + 0.45 * visual
        kind = ("cambio_visual_y_acustico" if sound >= .75 and visual >= .75
                else "cambio_visual" if visual > sound else "actividad_acustica")
        rows.append({
            "id": f"{vid}_{second:06d}", "vod_id": vid,
            "inicio_seg": max(0, second-10), "fin_seg": min(duration, second+12),
            "centro_seg": second, "tipo_momento": kind, "puntuacion": round(score, 6),
            "confianza": "media_en_las_senales" if min(sound, visual) >= .75 else "baja",
            "explicacion": "55% actividad acústica relativa y 45% cambio visual relativo al mismo VOD",
            "senales": {"actividad_acustica": sound, "percentil_cambio_visual": visual,
                        "rms_dbfs_en_centro": float(db[second]),
                        "aumento_db_local_en_centro": float(rise[second]),
                        "diferencia_visual_muestreada": delta},
            "evidencia": evidence, "detalle_adaptativo": [],
            "decision_editorial": None
        })
    ranked = []
    for row in sorted(rows, key=lambda item: (-item["puntuacion"], item["centro_seg"])):
        if all(abs(row["centro_seg"]-other["centro_seg"]) >= 15 for other in ranked):
            ranked.append(row)
    for rank, row in enumerate(ranked, 1):
        row["puesto"] = rank
    fine = list(pool.map(lambda row: measure(row["centro_seg"], [-5,-1,0,1,5]), ranked[:12]))
    for row, (delta, evidence) in zip(ranked, fine):
        row["detalle_adaptativo"] = evidence
        row["senales"]["diferencia_visual_detalle"] = delta
    return ranked, db, rms_rank


def extend_edge(db, edge, direction, duration, config):
    index = int(edge)
    radius = config["busqueda_contexto_max_seg_por_lado"]
    pause = float(np.percentile(db, config["percentil_pausa_rms"]))
    active = pause + config["actividad_minima_db_sobre_pausa"]
    # Extend only if the edge is in an active stretch and a nearby pause is observable.
    if not 1 <= index < len(db)-1 or min(db[index-1:index+1]) < active:
        return edge
    width = config["pausa_minima_seg"]
    for distance in range(1, radius+1):
        target = index + direction*distance
        start = target-width if direction < 0 else target
        if start < 0 or start+width > len(db):
            break
        if np.all(db[start:start+width] <= pause):
            return min(duration, max(0, target))
    return edge


def adapt(rows, db, ranks, duration):
    for row in rows:
        center = row["centro_seg"]
        audio, visual = (row["senales"][key] for key in ("actividad_acustica", "percentil_cambio_visual"))
        local = float(np.median(ranks[center-4:center+5]))
        support = max(local, float(ranks[center]))
        sound_part = CONFIG["peso_acustico"] * audio
        visual_part = CONFIG["peso_visual"] * min(visual, support)
        cut = [extend_edge(db, edge, direction, duration, CONFIG)
               for edge, direction in ((row["inicio_seg"], -1), (row["fin_seg"], 1))]
        yield {
            **row,
            "puntuacion": round(sound_part + visual_part, 6),
            "intervalo_corte_propuesto_seg": cut,
            "nucleo_seg": [center - 2, center + 2],
            "factores": {"acustico": sound_part, "visual": visual_part, "respaldo_rms": support,
                         "visual_sin_limitar": visual, "rms_mediano_local": local},
            "explicacion": "Cambio visual limitado por el respaldo acústico local",
            "corte": {"metodo": "pausa_acustica", "confirmado_por_editor": False},
        }


def run_local(source, sha256, destination, max_duration):
    source, destination = Path(source), Path(destination)
    meta = json.loads(subprocess.check_output(
        [resolve_binary("ffprobe"), "-v", "error", "-show_format", "-show_streams", "-of", "json", str(source)],
        timeout=30,
    ))
    duration = float(meta["format"]["duration"])
    if not math.isfinite(duration) or not 0 < duration <= max_duration:
        raise ValueError("Duración fuera del límite local")
    streams = meta["streams"]
    if not {"audio", "video"} <= {stream["codec_type"] for stream in streams}:
        raise ValueError("El detector requiere audio y video")
    starts = [float(s.get("start_time", 0)) for s in streams if s["codec_type"] in ("audio", "video")]
    origin = float(meta["format"].get("start_time", 0))
    # Seeking and resampling must share the same origin for these formulas.
    if not math.isfinite(origin) or abs(origin) > .05 or any(
        not math.isfinite(start) or abs(start - origin) > .05 for start in starts
    ):
        raise ValueError("Origen de pistas no alineado. Hace falta un mapeo temporal verificado.")
    folder = destination.parent / "frames"
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        pcm = Path(tmp) / "audio.f32"
        subprocess.run(
            [resolve_binary("ffmpeg"), "-nostdin", "-v", "error", "-i", str(source),
             "-map", CONFIG["audio_track"], "-ac", "1", "-af", "aresample=4000:async=1:first_pts=0",
             "-f", "f32le", str(pcm)], check=True, capture_output=True, timeout=max(60, duration),
        )
        vid = "vod_" + sha256[:16]
        with ThreadPoolExecutor(max_workers=2) as pool:
            v1, db, ranks = detect(vid, source, duration, pcm, folder, pool)
        v2 = sorted(adapt(v1, db, ranks, duration), key=lambda row: (-row["puntuacion"], row["centro_seg"]))
    for rank, row in enumerate(v2, 1):
        row["puesto"] = rank
    if digest(source) != sha256:
        raise ValueError("El archivo cambió durante la extracción")
    dump(destination, {
        "vod_id": vid, "sha256": sha256, "duration": duration, "origin": origin,
        "coverage": {"audio": "RMS mono de la primera pista", "video": "Fotogramas muestreados",
                     "dialogue": None, "narrative": None}, "v1": v1, "v2": v2,
    })


def render_preview(source, start, duration, destination):
    """Encode only the selected review range with seekable AV."""
    destination = Path(destination)
    if destination.is_file():
        return
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=destination.parent) as tmp:
        preview = Path(tmp) / "preview.mp4"
        subprocess.run(
            [resolve_binary("ffmpeg"), "-nostdin", "-v", "error", "-ss", f"{start:.6f}", "-i", source,
             "-t", f"{duration:.6f}", "-map", CONFIG["video_track"], "-map", CONFIG["audio_track"],
             "-vf", "scale='min(960,iw)':-2", "-c:v", "libx264", "-preset", "ultrafast", "-threads", "2",
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", str(preview)],
            check=True, capture_output=True, timeout=max(30, duration * 2),
        )
        preview.replace(destination)
