"""Pydantic v2 domain models matching the VidForge JSON Schemas."""

from __future__ import annotations

from typing import Any, Literal
from pydantic import BaseModel, Field


class Rational(BaseModel):
    num: int = Field(default=60, ge=1)
    den: int = Field(default=1, ge=1)

    @property
    def float_val(self) -> float:
        return self.num / self.den


class CanvasConfig(BaseModel):
    width: int = Field(default=1920, ge=16, le=7680)
    height: int = Field(default=1080, ge=16, le=4320)
    fps: Rational = Field(default_factory=lambda: Rational(num=60, den=1))
    background: str = "#000000"


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    language: str = "es"
    width: int = 1920
    height: int = 1080
    fps: int = 60
    style_guide: str = "Cinematográfico, iluminación dramática, 4k, ultra detallado"


class CharacterModel(BaseModel):
    tag: str
    name: str
    description: str = ""
    reference_asset_ids: list[str] = Field(default_factory=list)


class BeatModel(BaseModel):
    id: str
    index: int
    text: str
    char_range: list[int] = Field(default_factory=lambda: [0, 0])
    tags: list[str] = Field(default_factory=list)
    visual_prompt: str = ""
    media_kind: Literal["image", "video", "stock", "motion", "any"] = "image"
    time_range_us: list[int] | None = None


class ScriptModel(BaseModel):
    schema_version: str = "script/1"
    text: str = ""
    characters: list[CharacterModel] = Field(default_factory=list)
    beats: list[BeatModel] = Field(default_factory=list)


class WordTiming(BaseModel):
    i: int
    text: str
    start_us: int
    end_us: int
    confidence: float = 0.95
    source: Literal["asr", "aligned", "interpolated"] = "asr"


class TranscriptSegment(BaseModel):
    id: str
    word_range: list[int]
    start_us: int
    end_us: int
    text: str
    beat_id: str | None = None


class TranscriptModel(BaseModel):
    schema_version: str = "transcript/1"
    id: str
    audio_asset_id: str
    audio_sha256: str = ""
    language: str = "es"
    engine: dict[str, Any] = Field(default_factory=lambda: {"name": "faster-whisper", "model": "base"})
    mode: Literal["transcribe", "align"] = "align"
    duration_us: int
    words: list[WordTiming]
    segments: list[TranscriptSegment]


class KenBurnsEffect(BaseModel):
    type: Literal["ken_burns"] = "ken_burns"
    zoom_from: float = 1.03
    zoom_to: float = 1.10
    pan: Literal["none", "left_right", "right_left", "top_bottom", "bottom_top"] = "none"
    easing: Literal["linear", "ease_in_out"] = "linear"


class TransitionSpec(BaseModel):
    kind: Literal["cut", "xfade", "gl"] = "xfade"
    name: str = "fade"
    duration_us: int = 500_000
    anchor: Literal["start", "center"] = "start"


class MotionSpec(BaseModel):
    template_id: str
    template_version: str = "1.0.0"
    props: dict[str, Any] = Field(default_factory=dict)
    render_asset_id: str | None = None
    fullscreen: bool = False


class SubtitleClipSpec(BaseModel):
    text: str
    style_id: str = "default"
    word_range: list[int] = Field(default_factory=list)
    mode: Literal["block", "karaoke", "word_pop"] = "karaoke"


class ClipModel(BaseModel):
    id: str
    asset_id: str | None = None
    start_us: int = Field(ge=0)
    duration_us: int = Field(ge=1)
    source_in_us: int = 0
    volume_db: float = 0.0
    effects: list[KenBurnsEffect] = Field(default_factory=list)
    transition_in: TransitionSpec | None = None
    motion: MotionSpec | None = None
    subtitle: SubtitleClipSpec | None = None


class TrackModel(BaseModel):
    id: str
    kind: Literal["video", "overlay", "motion", "audio", "subtitle"]
    name: str
    muted: bool = False
    locked: bool = False
    clips: list[ClipModel] = Field(default_factory=list)


class SubtitleStyleModel(BaseModel):
    id: str = "default"
    font_family: str = "Segoe UI"
    font_size: int = 56
    primary_color: str = "#FFFFFF"
    highlight_color: str = "#38BDF8"
    outline: float = 4.0
    shadow: float = 2.0
    position: Literal["bottom", "middle", "top"] = "bottom"
    max_chars_per_line: int = 38
    uppercase: bool = True


class TimelineModel(BaseModel):
    schema_version: str = "timeline/1"
    revision: int = 1
    canvas: CanvasConfig = Field(default_factory=CanvasConfig)
    duration_us: int = 0
    subtitle_styles: list[SubtitleStyleModel] = Field(default_factory=lambda: [SubtitleStyleModel()])
    tracks: list[TrackModel] = Field(default_factory=list)
