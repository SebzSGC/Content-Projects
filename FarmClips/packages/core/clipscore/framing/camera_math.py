"""Smart crop math: gap interpolation (<1s / >1s), One Euro smoothing filter, central deadzone, and Ramer-Douglas-Peucker simplification."""

from __future__ import annotations

import math
from typing import List, Optional, Sequence, Tuple

from ..domain import FaceTrajectory

FACE_TARGET_Y = 0.44
FACE_TARGET_FILL = 0.40
MAX_AUTO_ZOOM = 2.0


class OneEuroFilter:
    """1€ Filter (Casiez et al., CHI 2012) for jitter-free stationary tracking and responsive motion."""

    def __init__(self, min_cutoff: float = 0.8, beta: float = 0.4, d_cutoff: float = 1.0):
        self.min_cutoff = min_cutoff
        self.beta = beta
        self.d_cutoff = d_cutoff
        self._x_prev: Optional[float] = None
        self._dx_prev: float = 0.0
        self._t_prev: Optional[float] = None

    @staticmethod
    def _alpha(dt: float, cutoff: float) -> float:
        tau = 1.0 / (2.0 * math.pi * max(1e-4, cutoff))
        return 1.0 / (1.0 + tau / max(1e-4, dt))

    def __call__(self, t: float, x: float) -> float:
        if self._t_prev is None or self._x_prev is None:
            self._t_prev = t
            self._x_prev = x
            self._dx_prev = 0.0
            return x
        dt = max(1e-3, t - self._t_prev)
        dx = (x - self._x_prev) / dt
        a_d = self._alpha(dt, self.d_cutoff)
        dx_hat = a_d * dx + (1.0 - a_d) * self._dx_prev
        cutoff = self.min_cutoff + self.beta * abs(dx_hat)
        a = self._alpha(dt, cutoff)
        x_hat = a * x + (1.0 - a) * self._x_prev
        self._x_prev = x_hat
        self._dx_prev = dx_hat
        self._t_prev = t
        return x_hat


def fill_face_gaps(
    t_series: Sequence[float],
    present: Sequence[bool],
    cx: Sequence[float],
    cy: Sequence[float],
    size: Sequence[float],
    max_interp_gap_sec: float = 1.0,
    center_cx: float = 0.5,
    center_cy: float = 0.45,
    default_size: float = 0.34,
) -> Tuple[List[float], List[float], List[float]]:
    """Interpolate gaps <= 1.0s; if face is missing > 1.0s, ease back to camera center."""
    n = len(t_series)
    if n == 0:
        return [], [], []
    if not any(present):
        return [center_cx] * n, [center_cy] * n, [default_size] * n

    out_cx = list(cx)
    out_cy = list(cy)
    out_sz = list(size)

    i = 0
    while i < n:
        if present[i]:
            i += 1
            continue
        j = i
        while j < n and not present[j]:
            j += 1
        gap_start_t = t_series[i - 1] if i > 0 else t_series[0]
        gap_end_t = t_series[j] if j < n else t_series[-1]
        gap_dur = gap_end_t - gap_start_t

        start_vals = (out_cx[i - 1], out_cy[i - 1], out_sz[i - 1]) if i > 0 else (center_cx, center_cy, default_size)
        end_vals = (out_cx[j], out_cy[j], out_sz[j]) if j < n else (center_cx, center_cy, default_size)

        if gap_dur <= max_interp_gap_sec and i > 0 and j < n:
            for k in range(i, j):
                u = (t_series[k] - gap_start_t) / max(1e-4, gap_dur)
                out_cx[k] = start_vals[0] + (end_vals[0] - start_vals[0]) * u
                out_cy[k] = start_vals[1] + (end_vals[1] - start_vals[1]) * u
                out_sz[k] = start_vals[2] + (end_vals[2] - start_vals[2]) * u
        else:
            # Missing > 1s: return to center smoothly
            for k in range(i, j):
                dt_from_loss = t_series[k] - gap_start_t
                blend_in = min(1.0, dt_from_loss / 0.45)
                cx_k = start_vals[0] + (center_cx - start_vals[0]) * blend_in
                cy_k = start_vals[1] + (center_cy - start_vals[1]) * blend_in
                sz_k = start_vals[2] + (default_size - start_vals[2]) * blend_in
                if j < n:
                    dt_to_reappear = gap_end_t - t_series[k]
                    if dt_to_reappear < 0.35:
                        u_out = 1.0 - (dt_to_reappear / 0.35)
                        cx_k = cx_k + (end_vals[0] - cx_k) * u_out
                        cy_k = cy_k + (end_vals[1] - cy_k) * u_out
                        sz_k = sz_k + (end_vals[2] - sz_k) * u_out
                out_cx[k], out_cy[k], out_sz[k] = cx_k, cy_k, sz_k
        i = j

    return out_cx, out_cy, out_sz


def apply_deadzone_series(
    cx: Sequence[float],
    cy: Sequence[float],
    deadzone_x: float = 0.055,
    deadzone_y: float = 0.045,
) -> Tuple[List[float], List[float]]:
    """Operator-style deadzone: camera anchor does not pan until face drifts past deadzone."""
    if not cx:
        return [], []
    anchor_x = cx[0]
    anchor_y = cy[0]
    res_x: List[float] = []
    res_y: List[float] = []
    for x, y in zip(cx, cy):
        dx = x - anchor_x
        dy = y - anchor_y
        if abs(dx) > deadzone_x:
            anchor_x += dx - math.copysign(deadzone_x, dx)
        if abs(dy) > deadzone_y:
            anchor_y += dy - math.copysign(deadzone_y, dy)
        res_x.append(round(max(0.15, min(0.85, anchor_x)), 4))
        res_y.append(round(max(0.15, min(0.85, anchor_y)), 4))
    return res_x, res_y


def ramer_douglas_peucker(
    points: Sequence[Tuple[float, float, float, float]],
    epsilon: float = 0.015,
) -> List[Tuple[float, float, float, float]]:
    """Simplify 4D trajectory (t, cx, cy, zoom) to sparse keyframes preserving spatial & zoom excursions."""
    if len(points) <= 2:
        return list(points)

    t0, x0, y0, z0 = points[0]
    t1, x1, y1, z1 = points[-1]
    dt = max(1e-6, t1 - t0)

    max_dist = -1.0
    index = 0
    for i in range(1, len(points) - 1):
        ti, xi, yi, zi = points[i]
        u = (ti - t0) / dt
        px = x0 + (x1 - x0) * u
        py = y0 + (y1 - y0) * u
        pz = z0 + (z1 - z0) * u
        # Weight zoom excursions alongside normalized spatial excursions
        dist = math.sqrt((xi - px) ** 2 + (yi - py) ** 2 + (0.35 * (zi - pz)) ** 2)
        if dist > max_dist:
            max_dist = dist
            index = i

    if max_dist > epsilon:
        left = ramer_douglas_peucker(points[: index + 1], epsilon)
        right = ramer_douglas_peucker(points[index:], epsilon)
        return left[:-1] + right
    return [points[0], points[-1]]


def build_base_camera_keyframes(
    face: Optional[FaceTrajectory],
    clip_duration: float,
    master_to_clip_fn,
    epsilon: float = 0.016,
) -> List[Tuple[float, float, float, float]]:
    """Turn raw MediaPipe FaceTrajectory into sparse smoothed (clip_t, cx, cy, base_zoom) keyframes."""
    if face is None or len(face.t_master) < 2:
        return [(0.0, 0.5, 0.45, 1.0), (round(clip_duration, 3), 0.5, 0.45, 1.0)]

    cx_g, cy_g, sz_g = fill_face_gaps(face.t_master, face.present, face.cx, face.cy, face.size)

    fx = OneEuroFilter(min_cutoff=0.7, beta=0.35)
    fy = OneEuroFilter(min_cutoff=0.7, beta=0.35)
    fs = OneEuroFilter(min_cutoff=0.4, beta=0.15)

    sm_cx = [fx(t, x) for t, x in zip(face.t_master, cx_g)]
    sm_cy = [fy(t, y) for t, y in zip(face.t_master, cy_g)]
    sm_sz = [fs(t, s) for t, s in zip(face.t_master, sz_g)]

    dz_cx, dz_cy = apply_deadzone_series(sm_cx, sm_cy)

    mapped: List[Tuple[float, float, float, float]] = []
    for tm, x, y, s in zip(face.t_master, dz_cx, dz_cy, sm_sz):
        ct = master_to_clip_fn(tm)
        if ct is None:
            continue
        auto_z = 1.0
        if s > 0.05:
            auto_z = max(1.0, min(MAX_AUTO_ZOOM, FACE_TARGET_FILL / max(0.18, s)))
            # Keep modest base zoom so impact zoom (1.25x) has room
            auto_z = min(1.35, auto_z)
        if not mapped or ct > mapped[-1][0] + 1e-3:
            mapped.append((round(ct, 3), round(x, 4), round(y, 4), round(auto_z, 3)))

    if not mapped:
        return [(0.0, 0.5, 0.45, 1.0), (round(clip_duration, 3), 0.5, 0.45, 1.0)]

    if mapped[0][0] > 0.0:
        mapped.insert(0, (0.0, mapped[0][1], mapped[0][2], mapped[0][3]))
    if mapped[-1][0] < clip_duration:
        mapped.append((round(clip_duration, 3), mapped[-1][1], mapped[-1][2], mapped[-1][3]))

    return ramer_douglas_peucker(mapped, epsilon=epsilon)
