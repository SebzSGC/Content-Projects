"""Audio cross-correlation alignment (gameplay mix <-> camera mic) and full Step 1 media preparation."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf
from clipscore.domain import PreparedMedia, SilenceSpan, SyncResult

from .ffmpeg import detect_clean_game_audio_stream, extract_opus_mono, extract_wav16k, probe
from .silence import detect_silences, slice_opus_chunks

ENV_HZ = 100


def _read_window(path: str, start: float, duration: float) -> Tuple[np.ndarray, int]:
    with sf.SoundFile(path) as f:
        sr = f.samplerate
        f.seek(max(0, min(f.frames, int(start * sr))))
        data = f.read(int(duration * sr), dtype="float32", always_2d=True)
    return data.mean(axis=1), sr


def _wav_duration(path: str) -> float:
    info = sf.info(path)
    return info.frames / float(info.samplerate)


def _zscore(x: np.ndarray) -> np.ndarray:
    arr = np.asarray(x, dtype=np.float64)
    sd = arr.std()
    return (arr - arr.mean()) / sd if sd > 1e-9 else np.zeros_like(arr)


def onset_envelope(x: np.ndarray, sr: int, hz: int = ENV_HZ) -> np.ndarray:
    hop = max(1, sr // hz)
    n = len(x) // hop
    if n < 2:
        return np.zeros(0, dtype=np.float64)
    frames = x[: n * hop].reshape(n, hop)
    log_e = np.log(np.sqrt((frames ** 2).mean(axis=1)) + 1e-5)
    onset = np.maximum(0.0, np.diff(log_e, prepend=log_e[0]))
    return _zscore(onset)


def xcorr_lag(ref: np.ndarray, other: np.ndarray, min_lag: int, max_lag: int) -> Tuple[int, float]:
    if len(ref) == 0 or len(other) == 0 or max_lag < min_lag:
        return 0, 0.0
    size = 1
    while size < len(ref) + len(other):
        size *= 2
    corr = np.fft.irfft(np.conj(np.fft.rfft(ref, size)) * np.fft.rfft(other, size), size)
    lags = np.arange(min_lag, max_lag + 1)
    values = corr[lags % size]
    best = int(np.argmax(values))
    sd = values.std()
    conf = float((values[best] - values.mean()) / sd) if sd > 1e-9 else 0.0
    return int(lags[best]), conf


def _fit_linear(points: Sequence[Tuple[float, float, float]], min_conf: float = 5.5) -> Optional[Tuple[float, float, float]]:
    good = [p for p in points if p[2] >= min_conf]
    if not good:
        return None
    conf = float(np.mean([p[2] for p in good]))
    if len(good) == 1:
        t, ct, _ = good[0]
        return 1.0, ct - t, conf
    t = np.array([p[0] for p in good])
    ct = np.array([p[1] for p in good])
    w = np.array([p[2] for p in good])
    scale, shift = np.polyfit(t, ct, 1, w=w)
    if abs(scale - 1.0) > 0.002:
        shift, scale = float(np.median(ct - t)), 1.0
    return float(scale), float(shift), conf


def estimate_audio_sync(
    master_wav: str,
    camera_wav: str,
    window_sec: float = 40.0,
    first_max_lag_sec: float = 45.0,
    refine_lag_sec: float = 3.0,
    windows: int = 5,
    fast_initial_cap_sec: float = 600.0,
) -> SyncResult:
    """Align camera recording to gameplay master timeline via FFT cross-correlation of onset envelopes.

    For long recordings (> 10 min), runs a fast first-pass on the initial 10-minute acoustic window
    and returns early if alignment confidence is high (>= 7.5), avoiding full multi-hour disk seeks.
    """
    master_dur = _wav_duration(master_wav)
    camera_dur = _wav_duration(camera_wav)
    min_dur = min(master_dur, camera_dur)
    eff_win = min(window_sec, max(4.0, min_dur * 0.7))
    eff_lag = min(first_max_lag_sec, max(2.0, min_dur * 0.4))

    def _probe_starts(starts_seq: Sequence[float]) -> List[Tuple[float, float, float]]:
        pts: List[Tuple[float, float, float]] = []
        pred_shift: Optional[float] = None
        for t in starts_seq:
            ref_x, sr = _read_window(master_wav, t, eff_win)
            ref = onset_envelope(ref_x, sr)
            lag_sec = eff_lag if pred_shift is None else refine_lag_sec
            center = t if pred_shift is None else t + pred_shift
            cam_start = max(0.0, center - lag_sec)
            cam_x, csr = _read_window(camera_wav, cam_start, eff_win + 2 * lag_sec)
            other = onset_envelope(cam_x, csr)
            if len(other) < max(10, len(ref) // 3) or len(ref) < 10:
                continue
            lo = int(round((center - lag_sec - cam_start) * ENV_HZ))
            hi = int(round((center + lag_sec - cam_start) * ENV_HZ))
            k, conf = xcorr_lag(ref, other, lo, hi)
            cam_t = cam_start + k / ENV_HZ
            pts.append((t, cam_t, conf))
            if pred_shift is None and conf >= 5.5:
                pred_shift = cam_t - t
        return pts

    # Fast first-pass on initial 10-minute window for long VODs
    if min_dur > fast_initial_cap_sec and fast_initial_cap_sec > eff_win * 2.0:
        fast_usable = fast_initial_cap_sec - eff_win
        fast_starts = [float(fast_usable * f) for f in (0.05, 0.45, 0.85)]
        fast_pts = _probe_starts(fast_starts)
        fast_fit = _fit_linear(fast_pts, min_conf=7.5)
        if fast_fit is not None:
            f_scale, f_shift, f_conf = fast_fit
            samples = [{"t": round(p[0], 2), "camera_t": round(p[1], 2), "confidence": round(p[2], 2)} for p in fast_pts]
            return SyncResult(
                shift_sec=round(f_shift, 4),
                scale=round(f_scale, 6),
                method="audio_xcorr",
                confidence=round(min(1.0, f_conf / 14.0), 3),
                samples=samples,
            )

    if master_dur <= eff_win * 1.4:
        starts = [0.0]
    else:
        usable = max(0.1, min(master_dur, camera_dur + eff_lag) - eff_win)
        starts = [float(usable * f) for f in np.linspace(0.05, 0.90, windows)]

    points = _probe_starts(starts)
    fit = _fit_linear(points, min_conf=5.0)
    samples = [{"t": round(p[0], 2), "camera_t": round(p[1], 2), "confidence": round(p[2], 2)} for p in points]
    if fit is None:
        return SyncResult(shift_sec=0.0, scale=1.0, method="zero", confidence=0.0, samples=samples)
    scale, shift, conf = fit
    return SyncResult(
        shift_sec=round(shift, 4),
        scale=round(scale, 6),
        method="audio_xcorr",
        confidence=round(min(1.0, conf / 14.0), 3),
        samples=samples,
    )


def classify_recording_pair(paths: Sequence[Path]) -> Optional[Tuple[Path, Path]]:
    """Return (gameplay_path, camera_path) from 2 video files by name convention or resolution/audio."""
    videos = [p for p in paths if p.suffix.lower() in {".mp4", ".mkv", ".mov", ".webm"}]
    if len(videos) < 2:
        return None
    gameplay_cand: Optional[Path] = None
    camera_cand: Optional[Path] = None
    for p in videos:
        low = p.stem.lower()
        if any(k in low for k in ("gameplay", "game", "juego", "stream")):
            gameplay_cand = p
        elif any(k in low for k in ("camara", "cámara", "camera", "facecam", "webcam", "cam")):
            camera_cand = p
    if gameplay_cand and camera_cand and gameplay_cand != camera_cand:
        return gameplay_cand, camera_cand

    # Fallback: higher pixel count or higher fps is typically gameplay
    probed = [(p, probe(p)) for p in videos[:2]]
    probed.sort(key=lambda item: (item[1].width * item[1].height, item[1].fps), reverse=True)
    return probed[0][0], probed[1][0]


def prepare_session_media(
    session_id: str,
    gameplay_path: str | Path,
    camera_path: str | Path,
    work_dir: Path,
    manual_sync: Optional[SyncResult] = None,
    target_chunk_sec: float = 600.0,
) -> PreparedMedia:
    """Step 1 (CPU pool): probe streams, extract WAV16k + Opus, slice ~10m silence chunks, and align sync."""
    work_dir.mkdir(parents=True, exist_ok=True)
    gp = probe(gameplay_path)
    cm = probe(camera_path)
    if not gp.has_audio:
        raise ValueError("El archivo de gameplay no tiene pista de audio (debe llevar la mezcla del stream).")
    if not cm.has_audio:
        raise ValueError("El archivo de la cámara no tiene audio (debe llevar el micrófono del streamer).")

    game_wav = work_dir / "gameplay_16k.wav"
    cam_wav = work_dir / "camera_16k.wav"
    cam_opus = work_dir / "camera_16k.opus"

    if not game_wav.is_file():
        extract_wav16k(gp.path, game_wav, audio_track_index=0)
    if not cam_wav.is_file():
        extract_wav16k(cm.path, cam_wav, audio_track_index=0)
    if not cam_opus.is_file():
        extract_opus_mono(cm.path, cam_opus)

    if manual_sync is not None and manual_sync.method == "manual":
        sync = manual_sync
    else:
        sync = estimate_audio_sync(str(game_wav), str(cam_wav))

    cam_silences = detect_silences(cam_wav, noise_db=-36.0, min_silence_sec=0.35)
    chunks = slice_opus_chunks(
        cam_opus,
        work_dir / "opus_chunks",
        total_duration=cm.duration,
        silences=cam_silences,
        target_chunk_sec=target_chunk_sec,
    )

    # Map speech silences >= 0.65s from camera timeline to master timeline for jump cuts
    master_silences: List[SilenceSpan] = []
    for s in cam_silences:
        if s.duration >= 0.65:
            ms = max(0.0, sync.master_time(s.start))
            me = min(gp.duration, sync.master_time(s.end))
            if me - ms >= 0.65:
                master_silences.append(SilenceSpan(start=round(ms, 3), end=round(me, 3)))

    return PreparedMedia(
        session_id=session_id,
        gameplay=gp,
        camera=cm,
        camera_opus_path=str(cam_opus.resolve()),
        chunks=chunks,
        camera_wav16k=str(cam_wav.resolve()),
        gameplay_wav16k=str(game_wav.resolve()),
        gameplay_clean_audio_stream=detect_clean_game_audio_stream(gp),
        sync=sync,
        speech_silences_master=master_silences,
    )
