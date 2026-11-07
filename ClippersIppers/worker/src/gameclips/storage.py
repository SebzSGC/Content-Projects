"""On-disk layout of a session. Every stage writes one JSON artifact so the
pipeline can resume and the UI can read partial results.

    <data_dir>/sessions/<id>/
        session.json      SessionSpec
        media.json        MediaManifest
        sync.json         SyncResult
        transcript.json   [Utterance] (with speaker labels once fused)
        ocr.json          [OcrLine]
        face.json         FaceTrack
        signals.json      SignalTimeline
        candidates.json   [Candidate]
        clips.json        [RenderedClip]
        proxies/          wav + low-res mp4 used for analysis
        downloads/        Kick VOD and high-res sections
        clips/            rendered mp4 + ass
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, List, Optional, TypeVar

from .config import get_settings
from .domain import (
    Candidate,
    FaceTrack,
    MediaManifest,
    OcrLine,
    RenderedClip,
    SessionSpec,
    SignalTimeline,
    SyncResult,
    Utterance,
    to_dict,
)

T = TypeVar("T")


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".tmp_", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(to_dict(data), fh, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


class SessionStore:
    def __init__(self, session_id: str, root: Optional[Path] = None):
        base = root or get_settings().data_dir
        self.id = session_id
        self.dir = base / "sessions" / session_id
        self.proxies = self.dir / "proxies"
        self.downloads = self.dir / "downloads"
        self.clips_dir = self.dir / "clips"

    @staticmethod
    def list_ids(root: Optional[Path] = None) -> List[str]:
        base = (root or get_settings().data_dir) / "sessions"
        if not base.exists():
            return []
        return sorted(p.name for p in base.iterdir() if (p / "session.json").exists())

    def ensure(self) -> "SessionStore":
        for d in (self.dir, self.proxies, self.downloads, self.clips_dir):
            d.mkdir(parents=True, exist_ok=True)
        return self

    def path(self, name: str) -> Path:
        return self.dir / name

    def has(self, name: str) -> bool:
        return self.path(name).exists()

    def _load(self, name: str, parse: Callable[[Any], T]) -> Optional[T]:
        p = self.path(name)
        return parse(read_json(p)) if p.exists() else None

    def save(self, name: str, data: Any) -> None:
        write_json(self.path(name), data)

    # Typed accessors -----------------------------------------------------
    def spec(self) -> SessionSpec:
        spec = self._load("session.json", SessionSpec.from_dict)
        if spec is None:
            raise FileNotFoundError(f"Session {self.id} not found")
        return spec

    def manifest(self) -> Optional[MediaManifest]:
        return self._load("media.json", MediaManifest.from_dict)

    def sync(self) -> SyncResult:
        return self._load("sync.json", SyncResult.from_dict) or SyncResult()

    def transcript(self) -> List[Utterance]:
        return self._load("transcript.json", lambda d: [Utterance.from_dict(u) for u in d]) or []

    def ocr(self) -> List[OcrLine]:
        return self._load("ocr.json", lambda d: [OcrLine(**x) for x in d]) or []

    def face(self) -> Optional[FaceTrack]:
        return self._load("face.json", FaceTrack.from_dict)

    def signals(self) -> Optional[SignalTimeline]:
        return self._load("signals.json", SignalTimeline.from_dict)

    def candidates(self) -> List[Candidate]:
        return self._load("candidates.json", lambda d: [Candidate.from_dict(c) for c in d]) or []

    def clips(self) -> List[RenderedClip]:
        return self._load("clips.json", lambda d: [RenderedClip.from_dict(c) for c in d]) or []

    def add_clip(self, clip: RenderedClip) -> None:
        clips = [c for c in self.clips() if c.id != clip.id]
        clips.append(clip)
        self.save("clips.json", clips)
