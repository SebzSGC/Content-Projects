"""Facecam tracking with MediaPipe Face Landmarker (camera timeline).

One model gives everything the pipeline needs from the camera:
* face box → reframing so the streamer stays centered (like the reference Short)
* ``jawOpen`` blendshape → who is talking (lip activity) and lip-sync alignment
* smile / surprise blendshapes → visual reaction signal, robust to game audio
"""

from __future__ import annotations

from typing import Callable

from ..config import get_settings
from ..domain import FaceTrack

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/face_landmarker/float16/1/face_landmarker.task"
)


def track_faces(camera_proxy: str, progress: Callable[[float, str], None]) -> FaceTrack:
    import cv2
    import mediapipe as mp
    from mediapipe.tasks.python import BaseOptions, vision

    s = get_settings()
    if s.face_landmarker_model is None or not s.face_landmarker_model.exists():
        raise RuntimeError(
            "Falta el modelo de MediaPipe. Descárgalo de "
            f"{MODEL_URL} y define CLIPS_FACE_LANDMARKER_MODEL con su ruta."
        )
    options = vision.FaceLandmarkerOptions(
        base_options=BaseOptions(model_asset_path=str(s.face_landmarker_model)),
        running_mode=vision.RunningMode.VIDEO,
        num_faces=1,
        output_face_blendshapes=True,
    )
    cap = cv2.VideoCapture(camera_proxy)
    fps = cap.get(cv2.CAP_PROP_FPS) or s.proxy_fps
    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 1
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    track = FaceTrack(fps=fps, width=width, height=height)

    with vision.FaceLandmarker.create_from_options(options) as landmarker:
        i = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            t = i / fps
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            res = landmarker.detect_for_video(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb), int(t * 1000))
            track.t.append(round(t, 3))
            if res.face_landmarks:
                pts = res.face_landmarks[0]
                xs = [p.x for p in pts]
                ys = [p.y for p in pts]
                shapes = {c.category_name: c.score for c in (res.face_blendshapes[0] if res.face_blendshapes else [])}
                track.present.append(True)
                track.cx.append((min(xs) + max(xs)) / 2)
                track.cy.append((min(ys) + max(ys)) / 2)
                track.size.append(max(ys) - min(ys))
                track.jaw_open.append(shapes.get("jawOpen", 0.0))
                track.smile.append((shapes.get("mouthSmileLeft", 0.0) + shapes.get("mouthSmileRight", 0.0)) / 2)
                track.surprise.append(
                    (shapes.get("browInnerUp", 0.0) + (shapes.get("eyeWideLeft", 0.0) + shapes.get("eyeWideRight", 0.0)) / 2) / 2
                )
            else:
                track.present.append(False)
                for series in (track.cx, track.cy, track.size, track.jaw_open, track.smile, track.surprise):
                    series.append(series[-1] if series else 0.0)
            i += 1
            if i % 200 == 0:
                progress(min(1.0, i / total), f"Siguiendo la cara {i}/{total}")
    cap.release()
    return track
