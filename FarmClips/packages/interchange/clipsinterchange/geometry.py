"""Cálculos geométricos para proyectar encuadres del EditPlan v2 en FilmCraft."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple


@dataclass
class MotionTransform:
    """Parámetros para el efecto de movimiento ('motion') en FilmCraft."""
    position_x: float      # Posición X en el lienzo (pixels)
    position_y: float      # Posición Y en el lienzo (pixels)
    scale_pct: float       # Escala uniforme (100.0 = 100%)
    anchor_x: float        # Punto de anclaje X en la fuente (pixels)
    anchor_y: float        # Punto de anclaje Y en la fuente (pixels)
    opacity_pct: float     # Opacidad (100.0 = visible, 0.0 = oculto)


@dataclass
class LayoutRegions:
    """Regiones del lienzo (x, y, w, h) para cámara y gameplay según el layout."""
    camera: Optional[Tuple[int, int, int, int]]
    gameplay: Optional[Tuple[int, int, int, int]]


def get_layout_regions(
    layout: str,
    camera_ratio: float = 0.38,
    canvas_w: int = 1080,
    canvas_h: int = 1920,
) -> LayoutRegions:
    """Calcula las cajas rectangulares (x, y, w, h) para cámara y gameplay."""
    if layout == "camera_full":
        return LayoutRegions(
            camera=(0, 0, canvas_w, canvas_h),
            gameplay=None,
        )
    elif layout == "gameplay_full":
        return LayoutRegions(
            camera=None,
            gameplay=(0, 0, canvas_w, canvas_h),
        )
    else:  # "split" por defecto
        ratio = max(0.20, min(0.80, float(camera_ratio)))
        cam_h = int(round(canvas_h * ratio))
        game_h = canvas_h - cam_h
        return LayoutRegions(
            camera=(0, 0, canvas_w, cam_h),
            gameplay=(0, cam_h, canvas_w, game_h),
        )


def compute_motion_transform(
    source_w: int,
    source_h: int,
    region: Optional[Tuple[int, int, int, int]],
    cx: float = 0.5,
    cy: float = 0.5,
    zoom: float = 1.0,
    anchor_y: float = 0.44,
) -> MotionTransform:
    """Calcula la transformación de `motion` que emula exactamente `fast_compositor.py`.
    
    Alinea la posición del centro de la fuente escalada en el lienzo para que la
    porción recortada quede exactamente dentro de la región especificada.
    """
    sw = max(1.0, float(source_w))
    sh = max(1.0, float(source_h))
    anchor_src_x = sw / 2.0
    anchor_src_y = sh / 2.0

    if region is None:
        # Pista oculta en este tramo
        return MotionTransform(
            position_x=sw / 2.0,
            position_y=sh / 2.0,
            scale_pct=100.0,
            anchor_x=anchor_src_x,
            anchor_y=anchor_src_y,
            opacity_pct=0.0,
        )

    rx, ry, tw, th = region
    # Cálculo idéntico a fast_compositor.compute_cover_affine_matrix
    base_s = max(float(tw) / sw, float(th) / sh)
    s = base_s * max(1.0, float(zoom))
    scale_pct = s * 100.0

    scaled_w = sw * s
    scaled_h = sh * s

    # Desplazamientos de recorte con límites
    crop_x = min(max(0.0, scaled_w * cx - float(tw) * 0.50), max(0.0, scaled_w - float(tw)))
    crop_y = min(max(0.0, scaled_h * cy - float(th) * anchor_y), max(0.0, scaled_h - float(th)))

    # Posición en el lienzo de FilmCraft donde situar el ancla (centro)
    pos_x = float(rx) - crop_x + (scaled_w / 2.0)
    pos_y = float(ry) - crop_y + (scaled_h / 2.0)

    return MotionTransform(
        position_x=round(pos_x, 2),
        position_y=round(pos_y, 2),
        scale_pct=round(scale_pct, 2),
        anchor_x=round(anchor_src_x, 2),
        anchor_y=round(anchor_src_y, 2),
        opacity_pct=100.0,
    )
