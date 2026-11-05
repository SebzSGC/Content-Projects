"""Sync tests on synthetic signals (needs numpy + soundfile)."""

from __future__ import annotations

import pytest

np = pytest.importorskip("numpy")
sf = pytest.importorskip("soundfile")

from gameclips import sync  # noqa: E402
from gameclips.domain import FaceTrack  # noqa: E402


def _bursty_audio(seconds: float, sr: int, seed: int = 1):
    rng = np.random.default_rng(seed)
    n = int(seconds * sr)
    x = rng.normal(0, 0.01, n).astype(np.float32)
    t = 0.0
    while t < seconds - 1:
        t += rng.uniform(0.2, 1.5)
        a = int(t * sr)
        length = int(rng.uniform(0.05, 0.4) * sr)
        x[a : a + length] += rng.normal(0, 0.3, len(x[a : a + length])).astype(np.float32)
    return x


def test_xcorr_recovers_known_lag():
    rng = np.random.default_rng(0)
    ref = rng.normal(size=2000)
    other = np.concatenate([rng.normal(size=137), ref, rng.normal(size=300)])
    k, conf = sync.xcorr_lag(ref, other, 0, 400)
    assert k == 137 and conf > 6


def test_audio_sync_offset_and_drift(tmp_path):
    sr = 16000
    master = _bursty_audio(600, sr)
    # Camera starts 2.35 s after the master and runs 100 ppm fast.
    offset, scale = 2.35, 1.0001
    t_cam = np.arange(int((600 - offset) * sr)) / sr
    src_t = t_cam / scale + offset
    camera = np.interp(src_t, np.arange(len(master)) / sr, master).astype(np.float32)
    m_path, c_path = tmp_path / "m.wav", tmp_path / "c.wav"
    sf.write(m_path, master, sr)
    sf.write(c_path, camera, sr)

    result = sync.estimate_audio_sync(str(m_path), str(c_path))
    assert result.method == "audio_xcorr"
    # camera_t = t * scale - offset * scale
    for t in (60.0, 300.0, 540.0):
        expected = (t - offset) * scale
        assert abs(result.camera_time(t) - expected) < 0.03


def test_lipsync_recovers_offset():
    fps = 10.0
    rng = np.random.default_rng(3)
    n = int(900 * fps)
    # Speech comes in bursts; silence in between.
    talking = np.repeat(rng.random(n // 20) > 0.5, 20)[:n]
    voice = np.where(talking, 0.2 + rng.random(n), 1e-3)
    shift = 7  # camera frame i shows what the master had at i - 7 → camera_t = t + 0.7
    jaw = np.zeros(n)
    for i in range(shift, n):
        jaw[i] = (i % 2) * min(1.0, voice[i - shift])
    face = FaceTrack(fps=fps, width=640, height=480, jaw_open=jaw.tolist(), present=[True] * n)
    result = sync.estimate_lipsync(face, voice)
    assert result.method == "lipsync"
    assert abs(result.camera_time(400.0) - 400.7) <= 0.15
