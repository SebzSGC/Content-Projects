"""Cálculos de ducking y niveles de audio para FilmCraft."""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from typing import List, Tuple, Union

from .timebase import seconds_to_ticks


@dataclass
class VolumeKeyframe:
    """Keyframe de nivel de volumen en decibelios."""
    time_ticks: int
    level_db: float
    interp: str = "Linear"


def merge_voice_spans(
    spans: List[Tuple[float, float]],
    min_gap_s: float = 0.25,
) -> List[Tuple[float, float]]:
    """Fusiona tramos de voz separados por silencios menores a `min_gap_s`."""
    if not spans:
        return []
    sorted_spans = sorted(spans, key=lambda s: s[0])
    merged: List[Tuple[float, float]] = []
    cur_start, cur_end = sorted_spans[0]

    for s, e in sorted_spans[1:]:
        if s <= cur_end + min_gap_s:
            cur_end = max(cur_end, e)
        else:
            merged.append((cur_start, cur_end))
            cur_start, cur_end = s, e
    merged.append((cur_start, cur_end))
    return merged


def generate_ducking_keyframes(
    voice_spans: List[Tuple[float, float]],
    duck_gain_db: float = -18.0,
    base_gain_db: float = 0.0,
    attack_s: float = 0.050,
    release_s: float = 0.200,
    fps: Union[Fraction, int, float] = Fraction(60, 1),
) -> List[VolumeKeyframe]:
    """Genera la envolvente de keyframes de volumen para atenuar el audio durante la voz."""
    merged = merge_voice_spans(voice_spans, min_gap_s=release_s + 0.05)
    keyframes: List[VolumeKeyframe] = []

    for start_s, end_s in merged:
        # Inicio del ataque (volumen base antes de bajar)
        t_pre = max(0.0, start_s - attack_s)
        # Final del ataque (volumen atenuado)
        t_duck = start_s
        # Inicio de la relajación (sigue atenuado hasta que termina la frase)
        t_hold = end_s
        # Final de la relajación (volumen base restablecido)
        t_post = end_s + release_s

        k_pre = seconds_to_ticks(t_pre, fps=fps)
        k_duck = seconds_to_ticks(t_duck, fps=fps)
        k_hold = seconds_to_ticks(t_hold, fps=fps)
        k_post = seconds_to_ticks(t_post, fps=fps)

        keyframes.append(VolumeKeyframe(time_ticks=k_pre, level_db=base_gain_db))
        keyframes.append(VolumeKeyframe(time_ticks=k_duck, level_db=duck_gain_db))
        keyframes.append(VolumeKeyframe(time_ticks=k_hold, level_db=duck_gain_db))
        keyframes.append(VolumeKeyframe(time_ticks=k_post, level_db=base_gain_db))

    return keyframes
