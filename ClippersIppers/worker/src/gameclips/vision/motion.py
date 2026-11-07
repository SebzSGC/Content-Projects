"""Gameplay motion and scene cuts per second (OpenCV, on the clean gameplay proxy)."""

from __future__ import annotations

from typing import Callable, Dict, List

import numpy as np


def motion_series(gameplay_proxy: str, progress: Callable[[float, str], None]) -> Dict[str, List[float]]:
    import cv2

    cap = cv2.VideoCapture(gameplay_proxy)
    fps = cap.get(cv2.CAP_PROP_FPS) or 10.0
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    per_frame: List[float] = []
    cuts: List[float] = []
    prev_gray = None
    prev_hist = None
    i = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        small = cv2.resize(frame, (160, 90))
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [16, 16], [0, 180, 0, 256])
        cv2.normalize(hist, hist)
        if prev_gray is None:
            per_frame.append(0.0)
            cuts.append(0.0)
        else:
            per_frame.append(float(np.mean(cv2.absdiff(gray, prev_gray))) / 255.0)
            cuts.append(1.0 if cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA) > 0.55 else 0.0)
        prev_gray, prev_hist = gray, hist
        i += 1
        if i % 500 == 0:
            progress(min(1.0, i / total), "Analizando movimiento del juego")
    cap.release()

    step = max(1, int(round(fps)))
    seconds = len(per_frame) // step
    motion = [float(np.mean(per_frame[s * step : (s + 1) * step])) for s in range(seconds)]
    scene = [float(max(cuts[s * step : (s + 1) * step])) for s in range(seconds)]
    return {"motion": motion, "scene_cut": scene}
