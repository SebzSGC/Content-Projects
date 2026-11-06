"""EditPlan v2 Pydantic contracts, timeline mapping helpers, and deterministic hashing."""

from __future__ import annotations

import hashlib
import json
from typing import List, Literal, Optional, Tuple

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

EaseKind = Literal["linear", "inOutSine", "outBack", "outCubic"]
LayoutKind = Literal["split", "camera_full", "gameplay_full"]


class SourcePlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session: str
    ranges: List[Tuple[float, float]] = Field(min_length=1)

    @field_validator("ranges")
    @classmethod
    def _validate_ranges(cls, v: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
        prev_end = -1.0
        cleaned: List[Tuple[float, float]] = []
        for a, b in v:
            a_f, b_f = round(float(a), 3), round(float(b), 3)
            if b_f <= a_f:
                raise ValueError(f"Rango inválido en EditPlan.source.ranges: [{a_f}, {b_f}]")
            if a_f < prev_end - 1e-4:
                raise ValueError("Los rangos de EditPlan.source.ranges deben ir ordenados y sin solape.")
            prev_end = b_f
            cleaned.append((a_f, b_f))
        return cleaned


class OutputPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    w: int = Field(default=1080, ge=240, le=4320)
    h: int = Field(default=1920, ge=240, le=4320)
    fps: int = Field(default=60, ge=15, le=120)
    style: str = "hormozi-gaming"


class LayoutEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t: float = Field(ge=0.0)
    kind: LayoutKind = "split"
    camera_ratio: Optional[float] = Field(default=None, ge=0.2, le=0.8)
    until: Optional[float] = Field(default=None, ge=0.0)

    @model_validator(mode="after")
    def _check_window(self) -> "LayoutEvent":
        if self.kind == "split" and self.camera_ratio is None:
            self.camera_ratio = 0.4
        if self.until is not None and self.until <= self.t:
            raise ValueError("LayoutEvent.until debe ser mayor que t")
        return self


class CropKeyframe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t: float = Field(ge=0.0)
    cx: float = Field(default=0.5, ge=0.0, le=1.0)
    cy: float = Field(default=0.45, ge=0.0, le=1.0)
    zoom: float = Field(default=1.0, ge=1.0, le=3.5)
    ease: Optional[EaseKind] = None


class CaptionWord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    w: str
    s: float = Field(ge=0.0)
    e: float = Field(ge=0.0)
    emphasis: Optional[bool] = None

    @model_validator(mode="after")
    def _check_word_times(self) -> "CaptionWord":
        if self.e < self.s:
            raise ValueError(f"CaptionWord '{self.w}' tiene fin ({self.e}) menor que inicio ({self.s})")
        return self


class EmojiCue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    at: float = Field(ge=0.0)


class CaptionGroup(BaseModel):
    model_config = ConfigDict(extra="forbid")

    words: List[CaptionWord] = Field(min_length=1)
    emoji: Optional[EmojiCue] = None


class CaptionsPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preset: str = "hormozi"
    groups: List[CaptionGroup] = Field(default_factory=list)


class OverlayItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["title", "badge"] = "title"
    text: str
    start: float = Field(default=0.0, ge=0.0)
    end: float = Field(default=3.0, ge=0.0)


class SfxCue(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t: float = Field(ge=0.0)
    id: str = "boom"
    gain_db: float = Field(default=-4.0, ge=-30.0, le=12.0)


class AudioPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mic_gain_db: float = Field(default=2.0, ge=-24.0, le=24.0)
    duck_game_db: float = Field(default=-9.0, ge=-36.0, le=0.0)
    sfx: List[SfxCue] = Field(default_factory=list)


class GameplayCropKeyframe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    t: float = Field(ge=0.0)
    cx: float = Field(default=0.5, ge=0.0, le=1.0)
    cy: float = Field(default=0.5, ge=0.0, le=1.0)
    zoom: float = Field(default=1.0, ge=1.0, le=2.5)


class EditPlan(BaseModel):
    """Declarative EditPlan v2 compiled by clipsrender and previewed live in apps/web."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[2] = 2
    clip_id: Optional[str] = None
    candidate_id: Optional[str] = None
    source: SourcePlan
    output: OutputPlan = Field(default_factory=OutputPlan)
    layout: List[LayoutEvent] = Field(
        default_factory=lambda: [LayoutEvent(t=0.0, kind="split", camera_ratio=0.4)]
    )
    camera_crop: List[CropKeyframe] = Field(
        default_factory=lambda: [CropKeyframe(t=0.0, cx=0.5, cy=0.45, zoom=1.0)]
    )
    gameplay_crop: Optional[List[GameplayCropKeyframe]] = None
    captions: CaptionsPlan = Field(default_factory=CaptionsPlan)
    overlays: List[OverlayItem] = Field(default_factory=list)
    audio: AudioPlan = Field(default_factory=AudioPlan)

    def total_duration(self) -> float:
        return round(sum(b - a for a, b in self.source.ranges), 3)

    def master_to_clip_time(self, master_t: float) -> Optional[float]:
        """Map a timestamp on the master VOD to its post-jump-cut clip second (or None if cut)."""
        acc = 0.0
        for a, b in self.source.ranges:
            if a - 1e-3 <= master_t <= b + 1e-3:
                clamped = max(a, min(b, master_t))
                return round(acc + (clamped - a), 3)
            acc += b - a
        return None

    def master_to_nearest_clip_time(self, master_t: float) -> float:
        """Map master VOD timestamp to clip time, clamping cut-out silence points to seam."""
        acc = 0.0
        for a, b in self.source.ranges:
            if master_t < a:
                return round(acc, 3)
            if master_t <= b:
                return round(acc + (master_t - a), 3)
            acc += b - a
        return round(acc, 3)

    def clip_to_master_time(self, clip_t: float) -> Tuple[int, float]:
        """Map clip second to (range_index, master_t)."""
        t = max(0.0, clip_t)
        acc = 0.0
        for idx, (a, b) in enumerate(self.source.ranges):
            seg_len = b - a
            if t <= acc + seg_len or idx == len(self.source.ranges) - 1:
                local = max(0.0, min(seg_len, t - acc))
                return idx, round(a + local, 3)
            acc += seg_len
        return 0, round(self.source.ranges[0][0], 3)

    def plan_hash(self, style_hash: str = "", quality: str = "final") -> str:
        payload = self.model_dump(mode="json", exclude_none=True)
        blob = json.dumps({"plan": payload, "style_hash": style_hash, "quality": quality}, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:24]
