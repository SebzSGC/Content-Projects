"""Core domain models shared across packages and server."""

from __future__ import annotations

import time
import uuid
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional

import pyarrow as pa
import pyarrow.parquet as pq
from pydantic import BaseModel, Field


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class SessionState(str, Enum):
    NEW = "NEW"
    DOWNLOADED = "DOWNLOADED"
    PREPARED = "PREPARED"
    TRANSCRIBED = "TRANSCRIBED"
    CURATED = "CURATED"
    PLANNING = "PLANNING"
    RENDERING = "RENDERING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class AudioStreamMeta(BaseModel):
    index: int
    codec_name: str = "aac"
    channels: int = 2
    sample_rate: int = 48000
    title: str = ""


class StreamProbe(BaseModel):
    path: str
    duration: float
    width: int
    height: int
    fps: float
    has_audio: bool
    audio_streams: List[AudioStreamMeta] = Field(default_factory=list)


class SyncResult(BaseModel):
    """Linear alignment from gameplay master timeline to camera timeline: camera_t = master_t * scale + shift_sec."""

    shift_sec: float = 0.0
    scale: float = 1.0
    method: str = "none"  # audio_xcorr | manual | zero | none
    confidence: float = 0.0
    samples: List[Dict[str, float]] = Field(default_factory=list)

    def camera_time(self, master_t: float) -> float:
        return master_t * self.scale + self.shift_sec

    def master_time(self, camera_t: float) -> float:
        return (camera_t - self.shift_sec) / (self.scale if abs(self.scale) > 1e-6 else 1.0)


class AudioChunk(BaseModel):
    index: int
    start_cam_sec: float
    end_cam_sec: float
    path: str
    size_bytes: int = 0
    sha256: str = ""

    @property
    def duration(self) -> float:
        return max(0.0, self.end_cam_sec - self.start_cam_sec)


class SilenceSpan(BaseModel):
    start: float
    end: float

    @property
    def duration(self) -> float:
        return max(0.0, self.end - self.start)


class PreparedMedia(BaseModel):
    session_id: str
    gameplay: StreamProbe
    camera: StreamProbe
    camera_opus_path: str
    chunks: List[AudioChunk]
    camera_wav16k: str
    gameplay_wav16k: str
    gameplay_clean_audio_stream: Optional[int] = None
    sync: SyncResult
    speech_silences_master: List[SilenceSpan] = Field(default_factory=list)


class TranscriptWord(BaseModel):
    text: str
    start: float  # master timeline seconds
    end: float    # master timeline seconds
    prob: float = 1.0


class Utterance(BaseModel):
    id: str  # e.g. "u0001", "u0412"
    start: float
    end: float
    text: str
    words: List[TranscriptWord] = Field(default_factory=list)
    speaker: str = "STREAMER"


class SignalPeak(BaseModel):
    t: float
    score: float
    mic: float = 0.0
    game: float = 0.0
    motion: float = 0.0
    hud: float = 0.0


class SignalSeries(BaseModel):
    duration: float
    mic_loudness: List[float] = Field(default_factory=list)
    mic_burst: List[float] = Field(default_factory=list)
    game_loudness: List[float] = Field(default_factory=list)
    motion: List[float] = Field(default_factory=list)
    motion_cx: List[float] = Field(default_factory=list)
    hud_activity: List[float] = Field(default_factory=list)
    reaction: List[float] = Field(default_factory=list)
    excitement: List[float] = Field(default_factory=list)
    peaks: List[SignalPeak] = Field(default_factory=list)

    def to_parquet(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        n = len(self.excitement)
        table = pa.table(
            {
                "sec": list(range(n)),
                "mic_loudness": self.mic_loudness[:n] + [0.0] * max(0, n - len(self.mic_loudness)),
                "mic_burst": self.mic_burst[:n] + [0.0] * max(0, n - len(self.mic_burst)),
                "game_loudness": self.game_loudness[:n] + [0.0] * max(0, n - len(self.game_loudness)),
                "motion": self.motion[:n] + [0.0] * max(0, n - len(self.motion)),
                "motion_cx": self.motion_cx[:n] + [0.5] * max(0, n - len(self.motion_cx)),
                "hud_activity": self.hud_activity[:n] + [0.0] * max(0, n - len(self.hud_activity)),
                "reaction": self.reaction[:n] + [0.0] * max(0, n - len(self.reaction)),
                "excitement": self.excitement[:n],
            },
            metadata={
                b"duration": str(self.duration).encode("utf-8"),
                b"peaks_json": (
                    "[" + ",".join(p.model_dump_json() for p in self.peaks) + "]"
                ).encode("utf-8"),
            },
        )
        pq.write_table(table, str(path))
        return path

    @classmethod
    def from_parquet(cls, path: Path) -> "SignalSeries":
        import json

        table = pq.read_table(str(path))
        meta = table.schema.metadata or {}
        duration = float(meta.get(b"duration", b"0").decode("utf-8"))
        peaks_raw = json.loads(meta.get(b"peaks_json", b"[]").decode("utf-8"))
        cols = table.to_pydict()
        exc = cols.get("excitement", [])
        return cls(
            duration=duration or float(len(exc)),
            mic_loudness=cols.get("mic_loudness", []),
            mic_burst=cols.get("mic_burst", []),
            game_loudness=cols.get("game_loudness", []),
            motion=cols.get("motion", []),
            motion_cx=cols.get("motion_cx", []),
            hud_activity=cols.get("hud_activity", [0.0] * len(exc)),
            reaction=cols.get("reaction", []),
            excitement=exc,
            peaks=[SignalPeak.model_validate(p) for p in peaks_raw],
        )


class EmojiSuggestion(BaseModel):
    word: str
    emoji: str  # Unicode emoji or hex id ("1f631" or "😱")


class CuratedClip(BaseModel):
    id: str
    start_id: str
    end_id: str
    start: float
    end: float
    hook: str = ""
    overlay_title: str
    post_title: str
    hashtags: List[str] = Field(default_factory=list)
    emphasis_words: List[str] = Field(default_factory=list)
    emojis: List[EmojiSuggestion] = Field(default_factory=list)
    llm_score: float = 0.0
    signal_score: float = 0.0
    final_score: float = 0.0
    reason: str = ""
    reaction_peaks: List[float] = Field(default_factory=list)
    created_at: float = Field(default_factory=time.time)

    @property
    def duration(self) -> float:
        return round(max(0.0, self.end - self.start), 3)

    def padded_range(self, margin_sec: float = 2.0, max_duration: Optional[float] = None) -> tuple[float, float]:
        a = max(0.0, self.start - margin_sec)
        b = self.end + margin_sec
        if max_duration is not None:
            b = min(max_duration, b)
        return round(a, 3), round(b, 3)


class FaceTrajectory(BaseModel):
    """Per-frame MediaPipe face measurements over a clip's padded camera segment."""

    fps: float = 15.0
    width: int = 640
    height: int = 360
    master_start: float = 0.0
    master_end: float = 0.0
    t_master: List[float] = Field(default_factory=list)
    present: List[bool] = Field(default_factory=list)
    cx: List[float] = Field(default_factory=list)
    cy: List[float] = Field(default_factory=list)
    size: List[float] = Field(default_factory=list)
    confidence: List[float] = Field(default_factory=list)

    def to_parquet(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        table = pa.table(
            {
                "t_master": self.t_master,
                "present": self.present,
                "cx": self.cx,
                "cy": self.cy,
                "size": self.size,
                "confidence": self.confidence,
            },
            metadata={
                b"fps": str(self.fps).encode("utf-8"),
                b"width": str(self.width).encode("utf-8"),
                b"height": str(self.height).encode("utf-8"),
                b"master_start": str(self.master_start).encode("utf-8"),
                b"master_end": str(self.master_end).encode("utf-8"),
            },
        )
        pq.write_table(table, str(path))
        return path

    @classmethod
    def from_parquet(cls, path: Path) -> "FaceTrajectory":
        table = pq.read_table(str(path))
        meta = table.schema.metadata or {}
        cols = table.to_pydict()
        return cls(
            fps=float(meta.get(b"fps", b"15.0").decode("utf-8")),
            width=int(meta.get(b"width", b"640").decode("utf-8")),
            height=int(meta.get(b"height", b"360").decode("utf-8")),
            master_start=float(meta.get(b"master_start", b"0.0").decode("utf-8")),
            master_end=float(meta.get(b"master_end", b"0.0").decode("utf-8")),
            t_master=cols.get("t_master", []),
            present=cols.get("present", []),
            cx=cols.get("cx", []),
            cy=cols.get("cy", []),
            size=cols.get("size", []),
            confidence=cols.get("confidence", []),
        )
