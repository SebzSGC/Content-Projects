"""Orchestrates the stages. Each stage writes its artifact and is skipped on the
next run unless ``force`` is set, so a failed analysis resumes where it stopped.

    ingest → media → separation → face → sync → transcription → ocr → motion
           → audio events → speakers → signals → selection (LLM) → verification (LLM)

Rendering is a separate job per clip.
"""

from __future__ import annotations

import base64
import tempfile
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from . import ffmpeg
from .config import get_settings
from .domain import (
    Candidate,
    MediaManifest,
    PixelRect,
    RenderedClip,
    RenderOptions,
    SessionSpec,
    SourceMode,
    SyncResult,
    Utterance,
    new_id,
)
from .ingest.adapter import MediaResolver, prepare_media, resolve_gameplay_path
from .render import ass as ass_mod
from .render import compose, framing
from .selection import candidates as cand
from .storage import SessionStore, read_json

ProgressFn = Callable[[str, float, str], None]


class Stage:
    """Maps a stage's own 0..1 progress into its slice of the whole job."""

    def __init__(self, report: ProgressFn, name: str, lo: float, hi: float):
        self.report, self.name, self.lo, self.hi = report, name, lo, hi

    def __call__(self, p: float, message: str = "") -> None:
        self.report(self.name, self.lo + (self.hi - self.lo) * max(0.0, min(1.0, p)), message)


# ---------------------------------------------------------------------------
# Ingest: only what's needed to show frames for the layout picker.
# ---------------------------------------------------------------------------


def ingest(session_id: str, report: ProgressFn) -> Dict[str, Any]:
    store = SessionStore(session_id).ensure()
    spec = store.spec()
    path = resolve_gameplay_path(spec, store, lambda p, m: report("ingest", 0.9 * p, m))
    info = ffmpeg.probe(path)
    result: Dict[str, Any] = {"gameplay": info}
    if spec.mode == SourceMode.SPLIT and spec.camera_path:
        result["camera"] = ffmpeg.probe(spec.camera_path)
    store.save("source.json", result)
    report("ingest", 1.0, "Fuente lista")
    return {"duration": info.duration}


def source_paths(store: SessionStore) -> Dict[str, str]:
    if not store.has("source.json"):
        return {}
    data = read_json(store.path("source.json"))
    return {k: v["path"] for k, v in data.items()}


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze(session_id: str, report: ProgressFn, force: bool = False) -> Dict[str, Any]:
    s = get_settings()
    store = SessionStore(session_id).ensure()
    spec = store.spec()

    def fresh(name: str) -> bool:
        return force or not store.has(name)

    # 1. Media ---------------------------------------------------------------
    if fresh("media.json"):
        store.save("media.json", prepare_media(spec, store, Stage(report, "media", 0.0, 0.12)))
    manifest = store.manifest()
    assert manifest is not None

    # 2. Source separation ----------------------------------------------------
    sep = Stage(report, "separation", 0.12, 0.25)
    sep(0.0, "Separando voces del resto del audio (Demucs)")
    from .audio.separation import separate

    vocals16, accomp16 = separate(manifest.mix_hq_wav, store.proxies)

    # 3. Face tracking (camera timeline) ---------------------------------------
    if fresh("face.json"):
        from .vision.face import track_faces

        store.save("face.json", track_faces(manifest.camera_proxy, Stage(report, "face", 0.25, 0.40)))
    face = store.face()

    # 4. Sync ------------------------------------------------------------------
    current = store.sync()
    if current.method != "manual" and (force or not store.has("sync.json")):
        store.save("sync.json", _estimate_sync(manifest, str(vocals16), face, Stage(report, "sync", 0.40, 0.43)))
    sync = store.sync()

    # 5. Transcription ---------------------------------------------------------
    if fresh("transcript_raw.json"):
        from .audio.transcribe import transcribe

        utts = transcribe(str(vocals16), manifest.duration, spec.language, Stage(report, "transcription", 0.43, 0.62))
        store.save("transcript_raw.json", utts)

    # 6. Game dialogue OCR -----------------------------------------------------
    if spec.game_subtitles_region and fresh("ocr.json"):
        from .vision.ocr import read_game_dialogue

        lines = read_game_dialogue(
            manifest.gameplay_proxy, spec.game_subtitles_region, spec.language, Stage(report, "ocr", 0.62, 0.67)
        )
        store.save("ocr.json", lines)

    # 7. Gameplay motion -------------------------------------------------------
    if fresh("motion.json"):
        from .vision.motion import motion_series

        store.save("motion.json", motion_series(manifest.gameplay_proxy, Stage(report, "motion", 0.67, 0.72)))

    # 8. Audio events + loudness -----------------------------------------------
    if fresh("audio_events.json"):
        from .audio.events import detect_events, loudness_db

        events = detect_events(vocals16, accomp16, store.proxies, Stage(report, "audio_events", 0.72, 0.82))
        events["loudness_db"] = loudness_db(manifest.mix_wav)
        store.save("audio_events.json", events)

    # 9. Speakers --------------------------------------------------------------
    st = Stage(report, "speakers", 0.82, 0.85)
    st(0.0, "Identificando quién habla")
    from .speakers import label_speakers

    raw = [Utterance.from_dict(u) for u in read_json(store.path("transcript_raw.json"))]
    voice_scores: Dict[str, Optional[float]] = {}
    if spec.voiceprint:
        from .audio.voiceprint import score_utterances

        voice_scores = score_utterances(spec.voiceprint, str(vocals16), raw)
    transcript = label_speakers(raw, manifest.duration, face, sync, voice_scores, store.ocr())
    store.save("transcript.json", transcript)

    # 10. Signals --------------------------------------------------------------
    Stage(report, "signals", 0.85, 0.87)(0.0, "Combinando señales")
    from .signals import build_timeline

    audio_events = read_json(store.path("audio_events.json"))
    timeline = build_timeline(
        manifest.duration,
        audio_events,
        audio_events.get("loudness_db", []),
        read_json(store.path("motion.json")),
        face,
        sync,
    )
    store.save("signals.json", timeline)

    # 11. Story selection (LLM) -------------------------------------------------
    sel = Stage(report, "selection", 0.87, 0.95)
    found = _select(spec, transcript, timeline, manifest.duration, sel)
    store.save("candidates.json", found)

    # 12. Verification (LLM, multimodal) -----------------------------------------
    verified = _verify(store, manifest, sync, transcript, timeline, found, Stage(report, "verification", 0.95, 1.0))
    store.save("candidates.json", verified)
    report("done", 1.0, f"{len(verified)} clips candidatos")
    return {"candidates": len(verified)}


def _estimate_sync(manifest: MediaManifest, vocals16: str, face, stage: Stage) -> SyncResult:
    if manifest.mode == SourceMode.COMPOSITE:
        return SyncResult(method="composite", confidence=1.0)
    from . import sync as sync_mod

    result = SyncResult()
    if manifest.camera_wav:
        stage(0.1, "Sincronizando por audio")
        result = sync_mod.estimate_audio_sync(manifest.mix_wav, manifest.camera_wav)
    if result.confidence < 0.4 and face is not None:
        stage(0.5, "Sincronizando por labios")
        lips = sync_mod.estimate_lipsync(face, sync_mod.voice_energy_series(vocals16, face.fps))
        if lips.confidence > result.confidence:
            result = lips
    stage(1.0, f"Sincronización: {result.method} (confianza {result.confidence:.2f})")
    return result


def _select(spec: SessionSpec, transcript, timeline, duration: float, stage: Stage) -> List[Candidate]:
    from .selection.llm import LlmError, select_stories

    s = get_settings()
    windows = cand.build_windows(transcript, timeline, duration)
    found: List[Candidate] = []
    errors: List[str] = []
    for i, (_a, _b, text) in enumerate(windows):
        stage(i / max(1, len(windows)), f"La IA busca historias ({i + 1}/{len(windows)})")
        try:
            stories = select_stories(text, spec.title)
        except LlmError as exc:
            errors.append(str(exc))
            continue
        for story in stories:
            try:
                start, end = cand.parse_time(story["start"]), cand.parse_time(story["end"])
            except (KeyError, ValueError):
                continue
            if end <= start:
                continue
            start, end = cand.snap_to_utterances(start, end, transcript, duration, s.min_clip_sec, s.max_clip_sec)
            llm_score = float(max(0, min(100, int(story.get("score", 0)))))
            sig = cand.signal_score(start, end, timeline)
            found.append(
                Candidate(
                    id=new_id("cand"),
                    start=start,
                    end=end,
                    overlay_title=str(story.get("overlay_title", "")).strip(),
                    post_title=str(story.get("post_title", "")).strip(),
                    hashtags=[h.lstrip("#").strip() for h in story.get("hashtags", []) if h.strip()],
                    reason=str(story.get("reason", "")).strip(),
                    llm_score=llm_score,
                    signal_score=sig,
                    final_score=cand.final_score(llm_score, sig, None),
                    reaction_peak=cand.reaction_peak(start, end, timeline),
                )
            )
    if windows and not found and errors:
        raise RuntimeError(f"La selección con IA falló: {errors[0]}")
    return cand.dedupe(found)[:40]


def _keyframes(manifest: MediaManifest, sync: SyncResult, c: Candidate, count: int = 5) -> List[str]:
    times = [c.start + (c.end - c.start) * (i + 0.5) / count for i in range(count)]
    if c.reaction_peak is not None:
        times = sorted(set(times + [c.reaction_peak]))
    images: List[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(times):
            for name, src, ts in (
                ("cam", manifest.camera_proxy, sync.camera_time(t)),
                ("game", manifest.gameplay_proxy, t),
            ):
                out = Path(tmp) / f"{i:02d}_{name}.jpg"
                try:
                    ffmpeg.extract_frame(src, ts, out, width=512)
                    images.append(base64.standard_b64encode(out.read_bytes()).decode("ascii"))
                except ffmpeg.FfmpegError:
                    continue
    return images


def _verify(store: SessionStore, manifest: MediaManifest, sync: SyncResult, transcript, timeline, found: List[Candidate], stage: Stage) -> List[Candidate]:
    from .selection.llm import LlmError, verify_candidate

    s = get_settings()
    ranked = sorted(found, key=lambda c: c.final_score, reverse=True)
    top = ranked[: s.verify_top_k]
    for i, c in enumerate(top):
        stage(i / max(1, len(top)), f"La IA revisa el clip {i + 1}/{len(top)}")
        excerpt = "\n".join(cand.utterance_line(u) for u in transcript if u.end > c.start and u.start < c.end)
        proposal = {
            "inicio": cand.fmt_time(c.start),
            "fin": cand.fmt_time(c.end),
            "overlay_title": c.overlay_title,
            "post_title": c.post_title,
            "hashtags": c.hashtags,
            "por_que": c.reason,
        }
        try:
            v = verify_candidate(_keyframes(manifest, sync, c), excerpt, proposal)
        except LlmError as exc:
            c.verification_notes = f"Sin verificar: {exc}"
            continue
        trim_a = max(-5.0, min(5.0, float(v.get("trim_start_sec", 0.0))))
        trim_b = max(-5.0, min(5.0, float(v.get("trim_end_sec", 0.0))))
        c.start, c.end = cand.snap_to_utterances(
            c.start + trim_a, c.end + trim_b, transcript, manifest.duration, s.min_clip_sec, s.max_clip_sec
        )
        score = float(max(0, min(100, int(v.get("score", 0)))))
        if not v.get("understandable_alone", True):
            score *= 0.6
        c.verify_score = score
        c.overlay_title = (v.get("overlay_title") or c.overlay_title).strip()
        c.post_title = (v.get("post_title") or c.post_title).strip()
        c.hashtags = [h.lstrip("#").strip() for h in (v.get("hashtags") or c.hashtags) if h.strip()]
        c.verification_notes = str(v.get("notes", "")).strip()
        c.verified = True
        c.signal_score = cand.signal_score(c.start, c.end, timeline)
        c.reaction_peak = cand.reaction_peak(c.start, c.end, timeline)
        c.final_score = cand.final_score(c.llm_score, c.signal_score, c.verify_score)
    return sorted(ranked, key=lambda c: c.final_score, reverse=True)


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def render(
    session_id: str,
    candidate_id: str,
    report: ProgressFn,
    options: Optional[RenderOptions] = None,
    start: Optional[float] = None,
    end: Optional[float] = None,
    overlay_title: Optional[str] = None,
) -> Dict[str, Any]:
    s = get_settings()
    opts = options or RenderOptions()
    store = SessionStore(session_id).ensure()
    spec = store.spec()
    manifest = store.manifest()
    if manifest is None:
        raise RuntimeError("La sesión no está analizada.")
    candidate = next((c for c in store.candidates() if c.id == candidate_id), None)
    if candidate is None:
        raise KeyError(f"Candidato {candidate_id} no existe")
    a = candidate.start if start is None else max(0.0, start)
    b = candidate.end if end is None else min(manifest.duration, end)
    if b - a < 1.0:
        raise ValueError("El clip es demasiado corto.")
    title = candidate.overlay_title if overlay_title is None else overlay_title
    sync = store.sync()
    face = store.face()

    report("render", 0.05, "Preparando fuentes")
    resolver = MediaResolver(manifest, store)
    game_in = resolver.gameplay(a, b, lambda p, m: report("render", 0.05 + 0.3 * p, m))

    cam_h, game_h = framing.panel_heights(opts.height, opts.camera_ratio)
    cam_aspect = opts.width / cam_h
    game_aspect = opts.width / game_h
    if manifest.mode == SourceMode.SPLIT:
        cam_info = manifest.camera
        cam_region = PixelRect(0, 0, cam_info.width, cam_info.height)
        game_region = PixelRect(0, 0, game_in.info.width, game_in.info.height)
    else:
        assert spec.layout is not None
        cam_region = spec.layout.camera.to_pixels(game_in.info.width, game_in.info.height)
        game_region = spec.layout.gameplay.to_pixels(game_in.info.width, game_in.info.height)

    stats = framing.face_stats(face, sync, a, b)
    cam_crop = framing.camera_crop(cam_region, cam_aspect, stats)
    zoom_crop: Optional[PixelRect] = None
    punch: Optional[tuple] = None
    if opts.punch_in and candidate.reaction_peak is not None and a <= candidate.reaction_peak <= b:
        zoom_crop = framing.camera_crop(cam_region, cam_aspect, stats, extra_zoom=1.35)
        p = candidate.reaction_peak - a
        punch = (max(0.0, p - 0.2), min(b - a, p + 1.6))
    game_crop = framing.gameplay_crop(game_region, game_aspect, opts.gameplay_focus_x)

    clip_id = new_id("clip")
    ass_path = store.clips_dir / f"{clip_id}.ass"
    ass_path.write_text(
        ass_mod.build_ass(a, b, store.transcript(), title, opts, cam_h, cam_h, game_h, s.title_font, s.caption_font),
        encoding="utf-8",
    )

    cam_t = sync.camera_time(a)
    spec_c = compose.ComposeSpec(
        split_mode=manifest.mode == SourceMode.SPLIT,
        duration=b - a,
        gameplay_path=game_in.path,
        gameplay_seek=max(0.0, a - game_in.base_time),
        camera_path=manifest.camera.path if manifest.mode == SourceMode.SPLIT else None,
        camera_seek=max(0.0, cam_t),
        camera_scale=sync.scale,
        camera_lead_pad=max(0.0, -cam_t),
        camera_crop=cam_crop,
        camera_zoom_crop=zoom_crop,
        punch_window=punch,
        gameplay_crop=game_crop,
        camera_height=cam_h,
        gameplay_height=game_h,
        fps=min(60.0, round(game_in.info.fps)) or 30.0,
        ass_path=str(ass_path),
        fonts_dir=str(s.fonts_dir) if s.fonts_dir else None,
        options=opts,
    )
    out = store.clips_dir / f"{clip_id}.mp4"
    report("render", 0.4, "Renderizando con FFmpeg")
    try:
        ffmpeg.run(compose.build_args(spec_c, ffmpeg.video_encoder_args(), out))
    except ffmpeg.FfmpegError:
        if not s.use_nvenc:
            raise
        report("render", 0.6, "NVENC no disponible, usando codificador por software")
        ffmpeg.run(compose.build_args(spec_c, ffmpeg.software_encoder_args(), out))

    clip = RenderedClip(id=clip_id, candidate_id=candidate.id, start=a, end=b, overlay_title=title, path=str(out))
    store.add_clip(clip)
    report("render", 1.0, "Clip listo")
    return {"clip_id": clip_id}
