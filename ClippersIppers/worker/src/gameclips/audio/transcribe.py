"""Word-level transcription with faster-whisper on the isolated vocals."""

from __future__ import annotations

from typing import Callable, List, Optional

from ..config import get_settings
from ..domain import Utterance, Word, new_id


def transcribe(
    wav_path: str,
    duration: float,
    language: Optional[str],
    progress: Callable[[float, str], None],
) -> List[Utterance]:
    from faster_whisper import WhisperModel

    s = get_settings()
    model = WhisperModel(s.whisper_model, device=s.whisper_device, compute_type=s.whisper_compute_type)
    segments, _info = model.transcribe(
        wav_path,
        language=language or None,
        word_timestamps=True,
        vad_filter=True,  # Silero VAD: no hallucinated text over game music
        condition_on_previous_text=False,  # avoids repetition loops on long VODs
        beam_size=5,
    )
    utterances: List[Utterance] = []
    for seg in segments:
        words = [
            Word(text=w.word.strip(), start=float(w.start), end=float(w.end), prob=float(w.probability))
            for w in (seg.words or [])
            if w.word.strip()
        ]
        text = seg.text.strip()
        if not text:
            continue
        utterances.append(
            Utterance(
                id=new_id("u"),
                start=float(words[0].start if words else seg.start),
                end=float(words[-1].end if words else seg.end),
                text=text,
                words=words,
            )
        )
        if duration > 0:
            progress(min(1.0, seg.end / duration), f"Transcribiendo {int(seg.end // 60)}:{int(seg.end % 60):02d}")
    return utterances
