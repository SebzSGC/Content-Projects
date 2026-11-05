"""Domain objects shared by every pipeline stage.

Plain dataclasses (no pydantic) so the pure logic modules stay importable
without the heavy ML stack. Every object round-trips through ``to_dict`` /
``from_dict`` for JSON persistence.

Time convention: the **master timeline** is the gameplay recording (it carries
the mixed audio). Camera timestamps are derived with ``SyncResult.camera_time``.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any, Dict, List, Optional, Type, TypeVar

T = TypeVar("T")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def to_dict(obj: Any) -> Any:
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "__dataclass_fields__"):
        return {k: to_dict(v) for k, v in asdict(obj).items()}
    if isinstance(obj, dict):
        return {k: to_dict(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [to_dict(v) for v in obj]
    return obj


def _from(cls: Type[T], data: Optional[Dict[str, Any]]) -> Optional[T]:
    if data is None:
        return None
    names = {f.name for f in fields(cls)}  # type: ignore[arg-type]
    return cls(**{k: v for k, v in data.items() if k in names})


class SourceMode(str, Enum):
    """``split``: camera and gameplay are separate files (audio mixed in gameplay).
    ``composite``: a single stream with the facecam burned in (Kick VOD, OBS output)."""

    SPLIT = "split"
    COMPOSITE = "composite"


class Speaker(str, Enum):
    STREAMER = "STREAMER"
    GAME = "GAME"
    UNKNOWN = "UNKNOWN"


@dataclass
class Rect:
    """Normalized rectangle (0..1) relative to the frame it applies to."""

    x: float
    y: float
    w: float
    h: float

    def to_pixels(self, width: int, height: int) -> "PixelRect":
        x = int(round(self.x * width))
        y = int(round(self.y * height))
        w = int(round(self.w * width))
        h = int(round(self.h * height))
        w = max(2, min(w, width - x))
        h = max(2, min(h, height - y))
        return PixelRect(x, y, w - w % 2, h - h % 2)

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["Rect"]:
        return _from(cls, data)


@dataclass
class PixelRect:
    x: int
    y: int
    w: int
    h: int


@dataclass
class LayoutPreset:
    """Where the facecam and the game live inside a composite frame."""

    camera: Rect
    gameplay: Rect

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> Optional["LayoutPreset"]:
        if data is None:
            return None
        return cls(camera=Rect.from_dict(data["camera"]), gameplay=Rect.from_dict(data["gameplay"]))  # type: ignore[arg-type]


@dataclass
class SessionSpec:
    id: str
    mode: SourceMode
    title: str
    gameplay_path: Optional[str] = None  # composite file when mode == composite
    camera_path: Optional[str] = None
    kick_url: Optional[str] = None
    layout: Optional[LayoutPreset] = None
    # Region of the *gameplay* frame where the game prints its own dialogue.
    game_subtitles_region: Optional[Rect] = None
    language: Optional[str] = "es"
    voiceprint: Optional[str] = None  # enrolled streamer voice name
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SessionSpec":
        return cls(
            id=data["id"],
            mode=SourceMode(data["mode"]),
            title=data.get("title", ""),
            gameplay_path=data.get("gameplay_path"),
            camera_path=data.get("camera_path"),
            kick_url=data.get("kick_url"),
            layout=LayoutPreset.from_dict(data.get("layout")),
            game_subtitles_region=Rect.from_dict(data.get("game_subtitles_region")),
            language=data.get("language"),
            voiceprint=data.get("voiceprint"),
            created_at=data.get("created_at", time.time()),
        )


@dataclass
class StreamInfo:
    path: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool


@dataclass
class MediaManifest:
    """Normalized inputs every later stage works on, whatever the source was."""

    mode: SourceMode
    gameplay: StreamInfo  # master timeline (mixed audio lives here)
    camera: StreamInfo  # same file as gameplay in composite mode
    camera_crop: Optional[Rect]  # crop inside ``camera.path`` (composite only)
    gameplay_crop: Optional[Rect]  # crop inside ``gameplay.path`` (composite only)
    mix_wav: str  # 16 kHz mono, master timeline
    mix_hq_wav: str  # 44.1 kHz stereo, for source separation
    camera_wav: Optional[str]  # 16 kHz mono, camera timeline (split mode, if the cam has audio)
    camera_proxy: str  # 480p / 10 fps, camera already cropped
    gameplay_proxy: str  # 480p / 10 fps, gameplay already cropped
    proxy_fps: float
    kick_url: Optional[str] = None

    @property
    def duration(self) -> float:
        return self.gameplay.duration

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MediaManifest":
        return cls(
            mode=SourceMode(data["mode"]),
            gameplay=StreamInfo(**data["gameplay"]),
            camera=StreamInfo(**data["camera"]),
            camera_crop=Rect.from_dict(data.get("camera_crop")),
            gameplay_crop=Rect.from_dict(data.get("gameplay_crop")),
            mix_wav=data["mix_wav"],
            mix_hq_wav=data["mix_hq_wav"],
            camera_wav=data.get("camera_wav"),
            camera_proxy=data["camera_proxy"],
            gameplay_proxy=data["gameplay_proxy"],
            proxy_fps=data["proxy_fps"],
            kick_url=data.get("kick_url"),
        )


@dataclass
class SyncResult:
    """Linear map from master time to camera time: ``camera_t = t * scale + shift``."""

    shift_sec: float = 0.0
    scale: float = 1.0
    method: str = "none"  # none | audio_xcorr | lipsync | manual
    confidence: float = 0.0
    samples: List[Dict[str, float]] = field(default_factory=list)

    def camera_time(self, master_t: float) -> float:
        return master_t * self.scale + self.shift_sec

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "SyncResult":
        return _from(cls, data) or cls()


@dataclass
class Word:
    text: str
    start: float
    end: float
    prob: float = 1.0


@dataclass
class Utterance:
    id: str
    start: float
    end: float
    text: str
    words: List[Word] = field(default_factory=list)
    speaker: Speaker = Speaker.UNKNOWN
    speaker_confidence: float = 0.0
    source: str = "asr"  # asr | ocr
    evidence: Dict[str, Optional[float]] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Utterance":
        return cls(
            id=data["id"],
            start=data["start"],
            end=data["end"],
            text=data["text"],
            words=[Word(**w) for w in data.get("words", [])],
            speaker=Speaker(data.get("speaker", "UNKNOWN")),
            speaker_confidence=data.get("speaker_confidence", 0.0),
            source=data.get("source", "asr"),
            evidence=data.get("evidence", {}),
        )


@dataclass
class OcrLine:
    start: float
    end: float
    text: str


@dataclass
class FaceTrack:
    """Per-frame facecam measurements on the camera proxy (camera timeline)."""

    fps: float
    width: int  # proxy frame size, for normalizing
    height: int
    t: List[float] = field(default_factory=list)
    present: List[bool] = field(default_factory=list)
    cx: List[float] = field(default_factory=list)  # normalized face center
    cy: List[float] = field(default_factory=list)
    size: List[float] = field(default_factory=list)  # normalized face height
    jaw_open: List[float] = field(default_factory=list)
    smile: List[float] = field(default_factory=list)
    surprise: List[float] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FaceTrack":
        return _from(cls, data)  # type: ignore[return-value]


@dataclass
class SignalTimeline:
    """Per-second series on the master timeline, every value in 0..1."""

    duration: float
    series: Dict[str, List[float]] = field(default_factory=dict)
    peaks: List[Dict[str, float]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SignalTimeline":
        return _from(cls, data)  # type: ignore[return-value]


@dataclass
class Candidate:
    id: str
    start: float
    end: float
    overlay_title: str
    post_title: str
    hashtags: List[str] = field(default_factory=list)
    reason: str = ""
    llm_score: float = 0.0  # 0..100
    signal_score: float = 0.0  # 0..1
    verify_score: Optional[float] = None  # 0..100
    final_score: float = 0.0  # 0..100
    reaction_peak: Optional[float] = None  # master time of the strongest reaction
    verified: bool = False
    verification_notes: str = ""

    @property
    def duration(self) -> float:
        return self.end - self.start

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Candidate":
        return _from(cls, data)  # type: ignore[return-value]


@dataclass
class RenderOptions:
    captions: str = "streamer"  # streamer | all | none
    title_duration_sec: float = 25.0
    camera_ratio: float = 0.4  # share of the 9:16 frame used by the facecam panel
    gameplay_focus_x: float = 0.5  # horizontal center of the gameplay crop
    punch_in: bool = True  # zoom on the face at the reaction peak
    voice_boost: bool = True
    width: int = 1080
    height: int = 1920

    @classmethod
    def from_dict(cls, data: Optional[Dict[str, Any]]) -> "RenderOptions":
        return _from(cls, data) or cls()


@dataclass
class RenderedClip:
    id: str
    candidate_id: str
    start: float
    end: float
    overlay_title: str
    path: str
    created_at: float = field(default_factory=time.time)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RenderedClip":
        return _from(cls, data)  # type: ignore[return-value]
