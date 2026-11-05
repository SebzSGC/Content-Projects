"""Streamer voiceprint (ECAPA-TDNN, SpeechBrain).

Enroll once with ~30 s of the streamer talking alone; every utterance is then
scored by cosine similarity. Helps label speech when the face is not visible.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

from .. import ffmpeg
from ..config import get_settings
from ..domain import Utterance


def voiceprint_dir() -> Path:
    d = get_settings().data_dir / "voiceprints"
    d.mkdir(parents=True, exist_ok=True)
    return d


def list_voiceprints() -> List[str]:
    return sorted(p.stem for p in voiceprint_dir().glob("*.npy"))


@lru_cache(maxsize=1)
def _encoder():
    from speechbrain.inference.speaker import EncoderClassifier

    s = get_settings()
    return EncoderClassifier.from_hparams(
        source="speechbrain/spkrec-ecapa-voxceleb",
        savedir=str(s.data_dir / "models" / "spkrec-ecapa-voxceleb"),
        run_opts={"device": s.torch_device},
    )


def _embed(samples: np.ndarray) -> np.ndarray:
    import torch

    with torch.no_grad():
        emb = _encoder().encode_batch(torch.from_numpy(samples).float().unsqueeze(0))
    vec = emb.squeeze().cpu().numpy()
    return vec / (np.linalg.norm(vec) + 1e-9)


def enroll(name: str, audio_path: Path) -> Path:
    import soundfile as sf

    wav = ffmpeg.extract_audio(str(audio_path), voiceprint_dir() / f"{name}_enroll16k.wav", 16000, 1)
    samples, _ = sf.read(str(wav), dtype="float32")
    out = voiceprint_dir() / f"{name}.npy"
    np.save(out, _embed(samples))
    wav.unlink(missing_ok=True)
    return out


def score_utterances(name: str, vocals16: str, utterances: List[Utterance]) -> Dict[str, Optional[float]]:
    """Cosine similarity (−1..1) of each utterance to the enrolled voice."""
    import soundfile as sf

    path = voiceprint_dir() / f"{name}.npy"
    if not path.exists():
        return {}
    ref = np.load(path)
    scores: Dict[str, Optional[float]] = {}
    with sf.SoundFile(vocals16) as f:
        sr = f.samplerate
        for u in utterances:
            if u.end - u.start < 0.8:  # too short for a stable embedding
                scores[u.id] = None
                continue
            f.seek(int(u.start * sr))
            chunk = f.read(int((u.end - u.start) * sr), dtype="float32")
            scores[u.id] = float(np.dot(ref, _embed(chunk)))
    return scores
