"""Align the camera recording to the master (gameplay) timeline.

1. ``audio_xcorr`` — when the camera file carries a copy of the stream mix, the
   two audio tracks are the same signal: cross-correlating onset envelopes
   gives the offset to ~10 ms. Several windows across the VOD fit a linear
   model so slow drift (dropped frames, clock skew) is corrected too.
2. ``lipsync``     — when the camera has no audio, correlate mouth movement
   (MediaPipe ``jawOpen``) with the energy of the isolated vocals.
3. ``manual``      — set from the UI; always wins.
"""

from __future__ import annotations

from typing import List, Optional, Sequence, Tuple

import numpy as np

from .domain import FaceTrack, SyncResult

ENV_HZ = 100  # audio envelope rate (10 ms resolution)


def read_window(path: str, start: float, duration: float) -> Tuple[np.ndarray, int]:
    import soundfile as sf

    with sf.SoundFile(path) as f:
        sr = f.samplerate
        f.seek(max(0, int(start * sr)))
        data = f.read(int(duration * sr), dtype="float32", always_2d=True)
    return data.mean(axis=1), sr


def wav_duration(path: str) -> float:
    import soundfile as sf

    info = sf.info(path)
    return info.frames / float(info.samplerate)


def onset_envelope(x: np.ndarray, sr: int, hz: int = ENV_HZ) -> np.ndarray:
    hop = max(1, sr // hz)
    n = len(x) // hop
    if n < 2:
        return np.zeros(0, dtype=np.float32)
    frames = x[: n * hop].reshape(n, hop)
    log_e = np.log(np.sqrt((frames ** 2).mean(axis=1)) + 1e-5)
    onset = np.maximum(0.0, np.diff(log_e, prepend=log_e[0]))
    return zscore(onset)


def zscore(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=np.float64)
    sd = x.std()
    return (x - x.mean()) / sd if sd > 1e-9 else np.zeros_like(x)


def xcorr_lag(ref: np.ndarray, other: np.ndarray, min_lag: int, max_lag: int) -> Tuple[int, float]:
    """Best ``k`` in ``[min_lag, max_lag]`` with ``other[n + k] ≈ ref[n]``.

    Returns ``(k, confidence)``; confidence is the peak's z-score among all
    tested lags (> ~6 is a clear, unambiguous match)."""
    if len(ref) == 0 or len(other) == 0:
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


def fit_linear(points: Sequence[Tuple[float, float, float]], min_conf: float) -> Optional[Tuple[float, float, float]]:
    """Weighted fit ``camera_t = scale * t + shift`` over ``(t, camera_t, conf)``."""
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
    if abs(scale - 1.0) > 0.002:  # >2000 ppm is not clock drift, it's a bad match
        shift, scale = float(np.median(ct - t)), 1.0
    return float(scale), float(shift), conf


def _window_starts(duration: float, window: float, count: int) -> List[float]:
    if duration <= window * 1.5:
        return [0.0]
    usable = duration - window
    return [usable * f for f in np.linspace(0.05, 0.95, count)]


def estimate_audio_sync(
    master_wav: str,
    camera_wav: str,
    window_sec: float = 45.0,
    first_max_lag_sec: float = 60.0,
    refine_lag_sec: float = 3.0,
    windows: int = 5,
) -> SyncResult:
    master_dur = wav_duration(master_wav)
    camera_dur = wav_duration(camera_wav)
    points: List[Tuple[float, float, float]] = []
    predicted_shift: Optional[float] = None

    for t in _window_starts(min(master_dur, camera_dur + first_max_lag_sec), window_sec, windows):
        ref_x, sr = read_window(master_wav, t, window_sec)
        ref = onset_envelope(ref_x, sr)
        lag_sec = first_max_lag_sec if predicted_shift is None else refine_lag_sec
        center = t if predicted_shift is None else t + predicted_shift
        cam_start = max(0.0, center - lag_sec)
        cam_x, csr = read_window(camera_wav, cam_start, window_sec + 2 * lag_sec)
        other = onset_envelope(cam_x, csr)
        if len(other) < len(ref) // 2:
            continue
        lo = int(round((center - lag_sec - cam_start) * ENV_HZ))
        hi = int(round((center + lag_sec - cam_start) * ENV_HZ))
        k, conf = xcorr_lag(ref, other, lo, hi)
        cam_t = cam_start + k / ENV_HZ
        points.append((t, cam_t, conf))
        if predicted_shift is None and conf >= 6.0:
            predicted_shift = cam_t - t

    fit = fit_linear(points, min_conf=6.0)
    samples = [{"t": p[0], "camera_t": p[1], "confidence": p[2]} for p in points]
    if fit is None:
        return SyncResult(method="none", confidence=0.0, samples=samples)
    scale, shift, conf = fit
    return SyncResult(shift_sec=shift, scale=scale, method="audio_xcorr", confidence=min(1.0, conf / 15.0), samples=samples)


def voice_energy_series(vocals_wav: str, fps: float) -> np.ndarray:
    """Vocal energy sampled at ``fps`` on the master timeline (streamed in blocks)."""
    import soundfile as sf

    out: List[np.ndarray] = []
    with sf.SoundFile(vocals_wav) as f:
        hop = max(1, int(round(f.samplerate / fps)))
        for block in f.blocks(blocksize=hop * 600, dtype="float32", always_2d=True):
            mono = block.mean(axis=1)
            n = len(mono) // hop
            if n:
                out.append(np.sqrt((mono[: n * hop].reshape(n, hop) ** 2).mean(axis=1)))
    return np.concatenate(out) if out else np.zeros(0)


def estimate_lipsync(
    face: FaceTrack,
    voice_energy: np.ndarray,
    window_sec: float = 120.0,
    max_lag_sec: float = 5.0,
    windows: int = 5,
) -> SyncResult:
    fps = face.fps
    jaw = np.array(face.jaw_open, dtype=np.float64)
    present = np.array(face.present, dtype=bool)
    mouth = np.abs(np.diff(jaw, prepend=jaw[:1] if len(jaw) else jaw))
    mouth[~present] = 0.0
    mouth = zscore(mouth)
    voice = zscore(np.log(voice_energy + 1e-5))
    duration = len(voice) / fps
    points: List[Tuple[float, float, float]] = []
    win = int(window_sec * fps)
    lag = int(max_lag_sec * fps)

    for t in _window_starts(duration, window_sec, windows):
        i = int(t * fps)
        ref = voice[i : i + win]
        lo_i = max(0, i - lag)
        other = mouth[lo_i : i + win + lag]
        if len(other) < win // 2 or len(ref) < win // 2:
            continue
        k, conf = xcorr_lag(ref, other, (i - lag) - lo_i, (i + lag) - lo_i)
        points.append((t, (lo_i + k) / fps, conf))

    fit = fit_linear(points, min_conf=4.0)
    samples = [{"t": p[0], "camera_t": p[1], "confidence": p[2]} for p in points]
    if fit is None:
        return SyncResult(method="none", confidence=0.0, samples=samples)
    scale, shift, conf = fit
    return SyncResult(shift_sec=shift, scale=scale, method="lipsync", confidence=min(1.0, conf / 12.0), samples=samples)
