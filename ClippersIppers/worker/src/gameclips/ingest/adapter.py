"""Source adapter: turns any input into the same ``MediaManifest``.

* split     — camera.mkv + gameplay.mkv (mixed audio in the gameplay file)
* composite — one file with the facecam burned in (local .mp4/.mkv or Kick)

Later stages never look at the original inputs again; they use the proxies and
WAVs listed in the manifest. Rendering asks ``MediaResolver`` for full-quality
inputs, which for Kick downloads only the needed range.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from .. import ffmpeg
from ..config import get_settings
from ..domain import MediaManifest, Rect, SessionSpec, SourceMode, StreamInfo
from ..storage import SessionStore
from . import kick

ProgressFn = Callable[[float, str], None]


class SourceError(ValueError):
    pass


def _check_file(path: Optional[str], label: str) -> str:
    if not path:
        raise SourceError(f"Falta la ruta del archivo de {label}.")
    p = Path(path).expanduser()
    if not p.is_file():
        raise SourceError(f"No existe el archivo de {label}: {p}")
    return str(p.resolve())


def validate_spec(spec: SessionSpec, require_layout: bool) -> None:
    if spec.mode == SourceMode.SPLIT:
        _check_file(spec.gameplay_path, "gameplay")
        _check_file(spec.camera_path, "cámara")
        return
    if spec.kick_url:
        if not kick.is_kick_url(spec.kick_url):
            raise SourceError("El link no parece un VOD o clip de Kick.")
    else:
        _check_file(spec.gameplay_path, "video")
    if require_layout and spec.layout is None:
        raise SourceError("El modo compuesto necesita el layout (dónde está la facecam y el juego).")


def resolve_gameplay_path(spec: SessionSpec, store: SessionStore, progress: ProgressFn) -> str:
    """Local path of the master file; downloads the Kick VOD (low-res) once."""
    if spec.mode == SourceMode.COMPOSITE and spec.kick_url:
        progress(0.0, "Descargando VOD de Kick (calidad de análisis)")
        local = kick.download_for_analysis(spec.kick_url, store.downloads, lambda p, m: progress(p, f"Descargando Kick {m}"))
        return str(local)
    return _check_file(spec.gameplay_path, "gameplay")


def prepare_media(spec: SessionSpec, store: SessionStore, progress: ProgressFn) -> MediaManifest:
    s = get_settings()
    validate_spec(spec, require_layout=True)
    store.ensure()

    gameplay_path = resolve_gameplay_path(spec, store, lambda p, m: progress(0.4 * p, m))
    gameplay = ffmpeg.probe(gameplay_path)
    if not gameplay.has_audio:
        raise SourceError("El archivo de gameplay no tiene audio: debe traer la mezcla del stream.")

    camera_crop: Optional[Rect] = None
    gameplay_crop: Optional[Rect] = None
    if spec.mode == SourceMode.SPLIT:
        camera = ffmpeg.probe(_check_file(spec.camera_path, "cámara"))
    else:
        assert spec.layout is not None
        camera = gameplay
        camera_crop, gameplay_crop = spec.layout.camera, spec.layout.gameplay

    progress(0.45, "Extrayendo audio")
    mix_wav = ffmpeg.extract_audio(gameplay.path, store.proxies / "mix16k.wav", 16000, 1)
    mix_hq = ffmpeg.extract_audio(gameplay.path, store.proxies / "mix44k.wav", 44100, 2)
    camera_wav: Optional[Path] = None
    if spec.mode == SourceMode.SPLIT and camera.has_audio:
        camera_wav = ffmpeg.extract_audio(camera.path, store.proxies / "camera16k.wav", 16000, 1)

    progress(0.6, "Generando proxy de la cámara")
    cam_proxy = ffmpeg.make_video_proxy(camera, store.proxies / "camera_proxy.mp4", s.proxy_height, s.proxy_fps, camera_crop)
    progress(0.8, "Generando proxy del gameplay")
    game_proxy = ffmpeg.make_video_proxy(gameplay, store.proxies / "gameplay_proxy.mp4", s.proxy_height, s.proxy_fps, gameplay_crop)

    manifest = MediaManifest(
        mode=spec.mode,
        gameplay=gameplay,
        camera=camera,
        camera_crop=camera_crop,
        gameplay_crop=gameplay_crop,
        mix_wav=str(mix_wav),
        mix_hq_wav=str(mix_hq),
        camera_wav=str(camera_wav) if camera_wav else None,
        camera_proxy=str(cam_proxy),
        gameplay_proxy=str(game_proxy),
        proxy_fps=s.proxy_fps,
        kick_url=spec.kick_url,
    )
    progress(1.0, "Medios listos")
    return manifest


@dataclass
class RenderInput:
    """A full-quality input for a time range: ``path`` starts at ``base_time``
    on its own timeline (0 for local files, the section start for Kick)."""

    path: str
    info: StreamInfo
    base_time: float = 0.0


class MediaResolver:
    def __init__(self, manifest: MediaManifest, store: SessionStore):
        self.m = manifest
        self.store = store

    def gameplay(self, start: float, end: float, progress: Optional[ProgressFn] = None) -> RenderInput:
        if self.m.kick_url:
            pad = 3.0
            a = max(0.0, start - pad)
            path = kick.download_section(
                self.m.kick_url,
                a,
                end + pad,
                self.store.downloads,
                (lambda p, msg: progress(p, f"Descargando tramo en alta calidad {msg}")) if progress else None,
            )
            return RenderInput(str(path), ffmpeg.probe(str(path)), base_time=a)
        return RenderInput(self.m.gameplay.path, self.m.gameplay)

    def camera(self, cam_start: float, cam_end: float) -> RenderInput:
        # Only reached in split mode; composite uses the gameplay input for both panels.
        return RenderInput(self.m.camera.path, self.m.camera)
