"""Where to crop each panel of the 9:16 frame (pure math, unit-tested)."""

from __future__ import annotations

from statistics import median
from typing import Optional, Tuple

from ..domain import FaceTrack, PixelRect, SyncResult

# The face sits at ~45% from the top of the camera panel, like the reference Short.
FACE_Y = 0.45
# Target face height relative to the panel; auto-zoom stops at MAX_ZOOM.
FACE_FILL = 0.42
MAX_ZOOM = 2.2


def _even(v: float) -> int:
    i = int(round(v))
    return i - i % 2


def fit_aspect(width: int, height: int, aspect: float) -> Tuple[int, int]:
    """Largest ``aspect`` (w/h) box that fits in ``width`` × ``height``."""
    w = min(float(width), height * aspect)
    return _even(w), _even(w / aspect)


def face_stats(face: Optional[FaceTrack], sync: SyncResult, start: float, end: float) -> Optional[Tuple[float, float, float]]:
    """Median face center/size (normalized to the camera region) over a clip."""
    if face is None:
        return None
    a = max(0, int(sync.camera_time(start) * face.fps))
    b = min(len(face.present), int(sync.camera_time(end) * face.fps) + 1)
    idx = [i for i in range(a, b) if face.present[i]]
    if len(idx) < max(3, (b - a) // 4):
        return None
    return median(face.cx[i] for i in idx), median(face.cy[i] for i in idx), median(face.size[i] for i in idx)


def camera_crop(
    region: PixelRect,
    panel_aspect: float,
    stats: Optional[Tuple[float, float, float]],
    extra_zoom: float = 1.0,
) -> PixelRect:
    """Crop inside the camera ``region`` (source pixels) framing the face."""
    base_w, base_h = fit_aspect(region.w, region.h, panel_aspect)
    zoom = 1.0
    cx, cy = 0.5, 0.45
    if stats is not None:
        cx, cy, size = stats
        face_px = size * region.h
        if face_px > 0:
            zoom = max(1.0, min(MAX_ZOOM, (FACE_FILL * base_h) / face_px))
    zoom *= extra_zoom
    w, h = _even(base_w / zoom), _even(base_h / zoom)
    x = region.x + cx * region.w - w / 2
    y = region.y + cy * region.h - FACE_Y * h
    x = max(region.x, min(region.x + region.w - w, x))
    y = max(region.y, min(region.y + region.h - h, y))
    return PixelRect(_even(x), _even(y), w, h)


def gameplay_crop(region: PixelRect, panel_aspect: float, focus_x: float = 0.5) -> PixelRect:
    w, h = fit_aspect(region.w, region.h, panel_aspect)
    x = region.x + focus_x * region.w - w / 2
    x = max(region.x, min(region.x + region.w - w, x))
    y = region.y + (region.h - h) / 2
    return PixelRect(_even(x), _even(y), w, h)


def panel_heights(height: int, camera_ratio: float) -> Tuple[int, int]:
    cam_h = _even(height * camera_ratio)
    return cam_h, height - cam_h
