"""Split the stream mix into ``vocals`` (streamer + game voices) and
``accompaniment`` (music, SFX, engine...) with Demucs.

Demucs can't tell *whose* voice it is — that's resolved later in
``speakers.py`` — but Whisper and the laughter detector work far better on the
isolated vocals, and the accompaniment stem gives a clean game-intensity signal.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Tuple

from .. import ffmpeg
from ..config import get_settings


def separate(mix_hq_wav: str, out_dir: Path) -> Tuple[Path, Path]:
    """Returns 16 kHz mono ``(vocals, accompaniment)``; falls back to the mix
    for both when Demucs is disabled."""
    s = get_settings()
    vocals16 = out_dir / "vocals16k.wav"
    accomp16 = out_dir / "accomp16k.wav"
    if vocals16.exists() and accomp16.exists():
        return vocals16, accomp16
    if not s.use_demucs:
        ffmpeg.resample_wav(Path(mix_hq_wav), vocals16, 16000)
        ffmpeg.resample_wav(Path(mix_hq_wav), accomp16, 16000)
        return vocals16, accomp16

    demucs_out = out_dir / "demucs"
    cmd = [
        sys.executable, "-m", "demucs",
        "--two-stems", "vocals",
        "-n", s.demucs_model,
        "-d", s.torch_device,
        "-o", str(demucs_out),
        mix_hq_wav,
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError("Demucs falló:\n" + "\n".join(proc.stderr.strip().splitlines()[-10:]))
    stem_dir = demucs_out / s.demucs_model / Path(mix_hq_wav).stem
    ffmpeg.resample_wav(stem_dir / "vocals.wav", vocals16, 16000)
    ffmpeg.resample_wav(stem_dir / "no_vocals.wav", accomp16, 16000)
    return vocals16, accomp16
