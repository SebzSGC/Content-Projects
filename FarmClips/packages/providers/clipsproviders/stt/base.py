"""Common Speech-to-Text adapter contract and word-timestamp normalization."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from clipscore.domain import TranscriptWord
from pydantic import BaseModel, Field


class SttResult(BaseModel):
    provider: str
    model: str
    words: List[TranscriptWord] = Field(default_factory=list)
    raw_response: Dict[str, Any] = Field(default_factory=dict)
    units_billed_sec: float = 0.0
    cost_usd: float = 0.0
    latency_ms: int = 0


class SttAdapter(ABC):
    provider_name: str = "base"
    model_name: str = "base"
    # Real providers transcribe whatever audio they get; recorded fixtures replay fixed timestamps and must
    # receive the original chunk.
    accepts_speech_only_audio: bool = True

    @abstractmethod
    async def transcribe_chunk(
        self,
        audio_path: Path,
        duration_sec: float,
        language: str = "es",
        keyterms: Sequence[str] = (),
    ) -> SttResult:
        """Transcribe a single Opus/WAV mono chunk and return chunk-relative word timestamps."""

    async def aclose(self) -> None:
        return None


def offset_and_map_words_to_master(
    chunk_words: Sequence[TranscriptWord],
    chunk_start_cam_sec: float,
    master_time_fn,
) -> List[TranscriptWord]:
    """Shift chunk-relative word timestamps by chunk_start_cam_sec and map from camera timeline to master timeline."""
    out: List[TranscriptWord] = []
    for w in chunk_words:
        cam_s = chunk_start_cam_sec + w.start
        cam_e = chunk_start_cam_sec + w.end
        ms = max(0.0, float(master_time_fn(cam_s)))
        me = max(ms + 0.03, float(master_time_fn(cam_e)))
        out.append(TranscriptWord(text=w.text, start=round(ms, 3), end=round(me, 3), prob=w.prob))
    return out
