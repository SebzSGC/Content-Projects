"""Lightweight CPU signal analysis: track loudness, streamer vocal bursts, 100Hz onset envelope, and optional 2fps OpenCV gameplay motion."""

from __future__ import annotations

import math
from statistics import median
from typing import Dict, List, Optional, Sequence, Tuple

import numpy as np
import soundfile as sf

from ..domain import SignalPeak, SignalSeries, TranscriptWord


def _clamp01(v: float) -> float:
    return max(0.0, min(1.0, float(v)))


def robust_norm(values: Sequence[float]) -> List[float]:
    """Normalize per-second series to 0..1 relative to VOD median/MAD baseline."""
    if not values:
        return []
    med = median(values)
    mad = median(abs(v - med) for v in values) * 1.4826
    scale = mad if mad > 1e-9 else (max(values) - med) / 3.0 or 1.0
    return [_clamp01(1.0 / (1.0 + math.exp(-1.6 * ((v - med) / scale - 1.4)))) for v in values]


def find_peaks(values: Sequence[float], threshold: float = 0.55, min_distance: int = 12, limit: int = 80) -> List[int]:
    order = sorted(range(len(values)), key=lambda i: values[i], reverse=True)
    chosen: List[int] = []
    for i in order:
        if values[i] < threshold or len(chosen) >= limit:
            break
        if all(abs(i - j) >= min_distance for j in chosen):
            chosen.append(i)
    return sorted(chosen)


def analyze_wav_per_second(wav_path: str) -> Tuple[List[float], List[float]]:
    """Return (rms_db_per_sec, burst_energy_per_sec) streamed in blocks without loading full WAV in RAM."""
    rms_db: List[float] = []
    bursts: List[float] = []
    with sf.SoundFile(wav_path) as f:
        sr = f.samplerate
        for block in f.blocks(blocksize=sr, dtype="float32", always_2d=True):
            mono = block.mean(axis=1)
            if len(mono) == 0:
                continue
            rms = float(np.sqrt(np.mean(mono * mono) + 1e-12))
            db = 20.0 * math.log10(max(rms, 1e-6))
            rms_db.append(db)
            # Sub-frame 50ms energy peakiness captures laughter/scream bursts cleanly
            sub = max(1, sr // 20)
            k = len(mono) // sub
            if k >= 2:
                sub_rms = np.sqrt((mono[: k * sub].reshape(k, sub) ** 2).mean(axis=1) + 1e-12)
                p95 = float(np.percentile(sub_rms, 95))
                bursts.append(20.0 * math.log10(max(p95, 1e-6)))
            else:
                bursts.append(db)
    return rms_db, bursts


def compute_mic_envelope_100hz(
    camera_wav_path: str,
    start_sec: float,
    end_sec: float,
    hz: int = 100,
) -> Tuple[np.ndarray, float]:
    """Return 100 Hz onset attack curve of camera mic in [start_sec, end_sec] for caption attack snapping."""
    s0 = max(0.0, start_sec - 0.25)
    dur = max(0.1, end_sec - s0 + 0.25)
    with sf.SoundFile(camera_wav_path) as f:
        sr = f.samplerate
        f.seek(min(f.frames, int(s0 * sr)))
        samples = f.read(int(dur * sr), dtype="float32", always_2d=True).mean(axis=1)
    hop = max(1, sr // hz)
    n = len(samples) // hop
    if n < 3:
        return np.zeros(0, dtype=np.float32), s0
    frames = samples[: n * hop].reshape(n, hop)
    energy = np.sqrt((frames * frames).mean(axis=1) + 1e-10)
    log_e = np.log(energy + 1e-5)
    attack = np.maximum(0.0, np.diff(log_e, prepend=log_e[0])).astype(np.float32)
    return attack, s0


def snap_word_starts_to_attack(
    words: Sequence[TranscriptWord],
    attack_100hz: Optional[np.ndarray],
    env_start_sec: float,
    max_shift_sec: float = 0.12,
    hz: int = 100,
) -> List[TranscriptWord]:
    """Adjust drifted STT word start times to nearest mic energy attack (pure NumPy, no ML)."""
    if attack_100hz is None or len(attack_100hz) < 5 or not words:
        return list(words)

    max_atk = float(np.max(attack_100hz))
    if max_atk <= 0.04:
        return list(words)
    thresh = max(0.05, float(np.percentile(attack_100hz, 75)) * 1.15)

    snapped: List[TranscriptWord] = []
    radius = max(1, int(round(max_shift_sec * hz)))
    prev_end = 0.0
    for idx, w in enumerate(words):
        center = int(round((w.start - env_start_sec) * hz))
        lo = max(0, center - radius)
        hi = min(len(attack_100hz), center + radius + 1)
        new_start = w.start
        if hi > lo:
            window = attack_100hz[lo:hi]
            best_rel = int(np.argmax(window))
            if float(window[best_rel]) >= thresh:
                candidate_t = env_start_sec + (lo + best_rel) / float(hz)
                new_start = max(prev_end, min(w.end - 0.04, candidate_t))
        new_end = max(new_start + 0.04, w.end)
        if idx + 1 < len(words) and new_end > words[idx + 1].start:
            new_end = max(new_start + 0.04, words[idx + 1].start)
        prev_end = new_end
        snapped.append(TranscriptWord(text=w.text, start=round(new_start, 3), end=round(new_end, 3), prob=w.prob))
    return snapped


def compute_gameplay_motion_2fps(gameplay_video_path: str, sample_fps: float = 2.0) -> Dict[str, List[float]]:
    """OpenCV pass at 2 fps on tiny 160x90 frames: returns per-second motion, horizontal centroid, and HUD/killfeed transients."""
    import cv2

    cap = cv2.VideoCapture(gameplay_video_path)
    src_fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    stride = max(1, int(round(src_fps / max(0.5, sample_fps))))

    frame_motion: List[Tuple[int, float, float, float]] = []
    prev_gray = None
    frame_idx = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        if frame_idx % stride == 0:
            ok2, frame = cap.retrieve()
            if ok2 and frame is not None:
                small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
                gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
                sec = int(frame_idx / src_fps)
                if prev_gray is None:
                    frame_motion.append((sec, 0.0, 0.5, 0.0))
                else:
                    diff = cv2.absdiff(gray, prev_gray).astype(np.float32) / 255.0
                    mot = float(diff.mean())
                    col_energy = diff.mean(axis=0)
                    total = float(col_energy.sum())
                    if total > 1e-4:
                        xs = np.linspace(0.0, 1.0, len(col_energy), dtype=np.float32)
                        cx = float((col_energy * xs).sum() / total)
                    else:
                        cx = 0.5

                    # Lightweight HUD / Killfeed transient detector (zero extra video decode):
                    # Top-right killfeed ROI (x: 68..99%, y: 2..28%) + Center crosshair/hitmarker ROI (x: 44..56%, y: 42..58%)
                    kf_gray = gray[2:25, 108:158].astype(np.float32) / 255.0
                    kf_edge = float(np.percentile(np.abs(np.diff(kf_gray, axis=1)), 90))
                    kf_trans = float(np.percentile(diff[2:25, 108:158], 90)) * (0.45 + kf_edge)
                    hm_trans = float(np.percentile(diff[38:52, 70:90], 92))
                    bg_mot = float(diff[30:84, 8:102].mean())
                    hud_val = max(0.0, 0.65 * kf_trans + 0.35 * hm_trans - 0.20 * bg_mot)
                    frame_motion.append((sec, mot, cx, hud_val))
                prev_gray = gray
        frame_idx += 1
    cap.release()

    if not frame_motion:
        return {"motion": [], "motion_cx": [], "hud_activity": []}
    max_sec = frame_motion[-1][0] + 1
    buckets_m: List[List[float]] = [[] for _ in range(max_sec)]
    buckets_cx: List[List[float]] = [[] for _ in range(max_sec)]
    buckets_hud: List[List[float]] = [[] for _ in range(max_sec)]
    for s, m, cx, hud_v in frame_motion:
        if 0 <= s < max_sec:
            buckets_m[s].append(m)
            buckets_cx[s].append(cx)
            buckets_hud[s].append(hud_v)
    motion = [round(float(np.mean(b)) if b else 0.0, 4) for b in buckets_m]
    motion_cx = [round(float(np.mean(b)) if b else 0.5, 4) for b in buckets_cx]
    hud_activity = [round(float(np.max(b)) if b else 0.0, 4) for b in buckets_hud]
    return {"motion": motion, "motion_cx": motion_cx, "hud_activity": hud_activity}


def build_signal_series(
    duration: float,
    camera_wav16k: str,
    gameplay_wav16k: str,
    sync_shift_sec: float = 0.0,
    sync_scale: float = 1.0,
    gameplay_video_path: Optional[str] = None,
    enable_motion: bool = True,
) -> SignalSeries:
    """Compute per-second track volume, reaction bursts, optional 2fps motion + HUD killfeed, and excitement peaks."""
    n = max(1, int(math.ceil(duration)))
    cam_db_raw, cam_burst_raw = analyze_wav_per_second(camera_wav16k)
    game_db_raw, _ = analyze_wav_per_second(gameplay_wav16k)

    # Align camera per-second series onto master gameplay timeline
    cam_db_aligned: List[float] = []
    cam_burst_aligned: List[float] = []
    for s in range(n):
        cam_s = int(round(s * sync_scale + sync_shift_sec))
        if 0 <= cam_s < len(cam_db_raw):
            cam_db_aligned.append(cam_db_raw[cam_s])
            cam_burst_aligned.append(cam_burst_raw[cam_s])
        else:
            cam_db_aligned.append(-65.0)
            cam_burst_aligned.append(-65.0)

    game_db_aligned = (game_db_raw[:n] + [-65.0] * max(0, n - len(game_db_raw)))[:n]

    mic_loud = robust_norm(cam_db_aligned)
    mic_burst = robust_norm(cam_burst_aligned)
    game_loud = robust_norm(game_db_aligned)

    if enable_motion and gameplay_video_path:
        mot_res = compute_gameplay_motion_2fps(gameplay_video_path)
        mot_raw = (mot_res["motion"][:n] + [0.0] * max(0, n - len(mot_res["motion"])))[:n]
        mot_cx = (mot_res["motion_cx"][:n] + [0.5] * max(0, n - len(mot_res["motion_cx"])))[:n]
        hud_raw = (mot_res.get("hud_activity", [])[:n] + [0.0] * max(0, n - len(mot_res.get("hud_activity", []))))[:n]
        mot = robust_norm(mot_raw)
        hud = robust_norm(hud_raw) if any(v > 1e-5 for v in hud_raw) else [0.0] * n
    else:
        mot = [0.0] * n
        mot_cx = [0.5] * n
        hud = [0.0] * n

    reaction = [round(_clamp01(0.65 * mic_burst[i] + 0.35 * mic_loud[i]), 3) for i in range(n)]
    game_act = [round(_clamp01(max(game_loud[i], 0.8 * mot[i], 0.85 * hud[i])), 3) for i in range(n)]
    setup_payoff = [reaction[i] * max(game_act[max(0, i - 5) : i + 1]) for i in range(n)]

    raw_exc = [
        _clamp01(0.55 * reaction[i] + 0.25 * game_act[i] + 0.20 * setup_payoff[i])
        for i in range(n)
    ]
    excitement = [
        round(max(raw_exc[max(0, i - 1) : min(n, i + 2)]), 3)
        for i in range(n)
    ]

    min_dist = 8 if n < 180 else 18
    # Weight dilated excitement with raw_exc slightly so plateaus center on the true transient second
    rank_series = [excitement[i] + 0.001 * raw_exc[i] for i in range(n)]
    peak_indices = find_peaks(rank_series, threshold=0.52, min_distance=min_dist, limit=80)
    peaks = [
        SignalPeak(
            t=float(i),
            score=round(excitement[i], 3),
            mic=round(max(reaction[max(0, i - 1) : min(n, i + 2)]), 3),
            game=round(max(game_loud[max(0, i - 1) : min(n, i + 2)]), 3),
            motion=round(max(mot[max(0, i - 1) : min(n, i + 2)]), 3),
            hud=round(max(hud[max(0, i - 1) : min(n, i + 2)]), 3),
        )
        for i in peak_indices
    ]

    return SignalSeries(
        duration=duration,
        mic_loudness=[round(x, 3) for x in mic_loud],
        mic_burst=[round(x, 3) for x in mic_burst],
        game_loudness=[round(x, 3) for x in game_loud],
        motion=[round(x, 3) for x in mot],
        motion_cx=[round(x, 3) for x in mot_cx],
        hud_activity=[round(x, 3) for x in hud],
        reaction=reaction,
        excitement=excitement,
        peaks=peaks,
    )
