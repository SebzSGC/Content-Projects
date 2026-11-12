"""Cálculos racionales de tiempo y conversión a ticks para FilmCraft y NLEs profesionales."""

from __future__ import annotations

from fractions import Fraction
from typing import Union

# Base de tiempo universal de FilmCraft (Premiere / FCP ticks: 254,016,000,000 ticks/seg)
TICKS_PER_SECOND: int = 254016000000


def seconds_to_fraction(seconds: Union[float, int, Fraction]) -> Fraction:
    """Convierte segundos a Fraction con precisión exacta."""
    if isinstance(seconds, Fraction):
        return seconds
    if isinstance(seconds, int):
        return Fraction(seconds, 1)
    # Redondeo de float a 6 decimales para evitar artefactos de representación IEEE-754
    return Fraction(round(seconds * 1_000_000), 1_000_000)


def seconds_to_ticks(
    seconds: Union[float, int, Fraction],
    fps: Union[Fraction, int, float] = Fraction(60, 1),
    snap_to_frame: bool = True,
) -> int:
    """Convierte un tiempo en segundos a ticks de FilmCraft.
    
    Si `snap_to_frame` es True, ajusta el instante al límite de frame más cercano
    según la tasa `fps` racional, garantizando que los cortes caigan en límites exactos.
    """
    frac_s = seconds_to_fraction(seconds)
    if not isinstance(fps, Fraction):
        fps = Fraction(fps).limit_denominator(1001)

    if snap_to_frame and fps > 0:
        # Calcular el número de frame más cercano
        frame_idx = round(float(frac_s * fps))
        frac_s = Fraction(frame_idx, fps)

    return int(frac_s * TICKS_PER_SECOND)


def ticks_to_seconds(ticks: int) -> float:
    """Convierte ticks de FilmCraft a segundos (float)."""
    return float(Fraction(ticks, TICKS_PER_SECOND))


def frame_to_ticks(frame: int, fps: Union[Fraction, int, float] = Fraction(60, 1)) -> int:
    """Convierte un número entero de frame a ticks."""
    if not isinstance(fps, Fraction):
        fps = Fraction(fps).limit_denominator(1001)
    return int((Fraction(frame, 1) / fps) * TICKS_PER_SECOND)


def ticks_to_frames(ticks: int, fps: Union[Fraction, int, float] = Fraction(60, 1)) -> int:
    """Convierte ticks a número de frames."""
    if not isinstance(fps, Fraction):
        fps = Fraction(fps).limit_denominator(1001)
    frac_s = Fraction(ticks, TICKS_PER_SECOND)
    return round(float(frac_s * fps))
