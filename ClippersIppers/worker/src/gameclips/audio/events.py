"""Per-second audio signals.

* PANNs (CNN14, AudioSet labels) on the **vocals** stem → laughter / screaming.
* PANNs on the **accompaniment** stem → game events (crashes, explosions...).
* RMS loudness of the full mix.

All series are raw probabilities / dB; ``signals.py`` normalizes them.
"""

from __future__ import annotations

from pathlib import Path
from typing import Callable, Dict, List

import numpy as np

from .. import ffmpeg
from ..config import get_settings

PANNS_SR = 32000

LAUGH = ["Laughter", "Baby laughter", "Giggle", "Snicker", "Belly laugh", "Chuckle, chortle"]
SCREAM = ["Screaming", "Shout", "Yell", "Whoop", "Battle cry", "Children shouting", "Cheering"]
GAME = [
    "Explosion", "Gunshot, gunfire", "Machine gun", "Burst, pop", "Boom", "Smash, crash",
    "Breaking", "Shatter", "Glass", "Skidding", "Tire squeal", "Vehicle horn, car horn, honking",
    "Thump, thud", "Bang",
]


def _per_second_probs(wav16: Path, tmp_dir: Path, groups: Dict[str, List[str]], progress: Callable[[float], None]) -> Dict[str, List[float]]:
    import soundfile as sf
    from panns_inference import AudioTagging, labels

    wav32 = ffmpeg.resample_wav(wav16, tmp_dir / f"{wav16.stem}_32k.wav", PANNS_SR)
    idx = {name: [labels.index(l) for l in group if l in labels] for name, group in groups.items()}
    tagger = AudioTagging(checkpoint_path=None, device=get_settings().torch_device)
    out: Dict[str, List[float]] = {name: [] for name in groups}
    total = sf.info(str(wav32)).frames / PANNS_SR
    batch_sec = 64
    done = 0.0
    with sf.SoundFile(str(wav32)) as f:
        for block in f.blocks(blocksize=PANNS_SR * batch_sec, dtype="float32", always_2d=True):
            mono = block.mean(axis=1)
            n = int(np.ceil(len(mono) / PANNS_SR))
            mono = np.pad(mono, (0, n * PANNS_SR - len(mono)))
            clipwise, _emb = tagger.inference(mono.reshape(n, PANNS_SR))
            for name, cols in idx.items():
                out[name].extend(clipwise[:, cols].max(axis=1).tolist() if cols else [0.0] * n)
            done += n
            progress(min(1.0, done / max(total, 1.0)))
    wav32.unlink(missing_ok=True)
    return out


def detect_events(vocals16: Path, accomp16: Path, tmp_dir: Path, progress: Callable[[float, str], None]) -> Dict[str, List[float]]:
    voice = _per_second_probs(vocals16, tmp_dir, {"laughter": LAUGH, "scream": SCREAM}, lambda p: progress(0.5 * p, "Risas y gritos"))
    game = _per_second_probs(accomp16, tmp_dir, {"game_events": GAME}, lambda p: progress(0.5 + 0.5 * p, "Eventos del juego"))
    return {**voice, **game}


def loudness_db(wav16: str) -> List[float]:
    import soundfile as sf

    values: List[float] = []
    with sf.SoundFile(wav16) as f:
        sr = f.samplerate
        for block in f.blocks(blocksize=sr, dtype="float32", always_2d=True):
            rms = float(np.sqrt((block.mean(axis=1) ** 2).mean())) if len(block) else 0.0
            values.append(20.0 * np.log10(rms + 1e-6))
    return values
