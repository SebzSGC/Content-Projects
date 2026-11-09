"""Async API Pool: STT & LLM routers with rate limiters, circuit breakers, 413 chunk resplit, raw archiving, and hash cache."""

from __future__ import annotations

import asyncio
import hashlib
import json
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from clipscore.domain import AudioChunk, SilenceSpan, SyncResult, TranscriptWord
from clipsmedia.silence import remap_packed_words, resplit_chunk_finer, write_speech_only_opus
from clipsproviders.http import FailoverRouter, PayloadTooLargeError
from clipsproviders.llm import (
    CURATION_PROMPT_VERSION,
    CurationEnvelope,
    GeminiAdapter,
    LlmAdapter,
    LlmCurationResult,
    OpenAICompatibleAdapter,
    RawLlmCallOutput,
    RecordedLlmFixtureAdapter,
)
from clipsproviders.stt import (
    DeepgramNova3Adapter,
    GroqWhisperAdapter,
    RecordedSttFixtureAdapter,
    SttAdapter,
    offset_and_map_words_to_master,
)

from ..config import ServerSettings
from ..orchestrator.db import OrchestratorDB, stable_hash


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(1024 * 256)
            if not b:
                break
            h.update(b)
    return h.hexdigest()[:24]


class ApiPool:
    def __init__(self, settings: ServerSettings, db: OrchestratorDB) -> None:
        self.settings = settings
        self.db = db
        self.raw_dir = settings.data_dir / "raw_api"
        self.norm_dir = settings.data_dir / "artifacts"
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        self.norm_dir.mkdir(parents=True, exist_ok=True)
        self._download_sem = asyncio.Semaphore(6)

        self.stt_router = self._build_stt_router()
        self.llm_router = self._build_llm_router()

    def _make_stt(self, name: str) -> Optional[SttAdapter]:
        if name == "fixture":
            fix_dir = self.settings.fixtures_dir or Path("tests/fixtures/api").resolve()
            return RecordedSttFixtureAdapter(fix_dir / "deepgram_nova3.json")
        if name == "deepgram":
            return DeepgramNova3Adapter(
                api_key=self.settings.deepgram_api_key or None,
                model=self.settings.deepgram_model,
            )
        if name == "groq":
            return GroqWhisperAdapter(
                api_key=self.settings.groq_api_key or None,
                model=self.settings.groq_stt_model,
            )
        return None

    def _build_stt_router(self) -> FailoverRouter[SttAdapter]:
        primary = self._make_stt(self.settings.stt_primary) or DeepgramNova3Adapter(
            api_key=self.settings.deepgram_api_key or None,
            model=self.settings.deepgram_model,
        )
        backup = self._make_stt(self.settings.stt_backup) if self.settings.stt_backup != self.settings.stt_primary else None
        return FailoverRouter(primary=primary, backup=backup)

    def _make_llm(self, name: str) -> Optional[LlmAdapter]:
        if name == "fixture":
            fix_dir = self.settings.fixtures_dir or Path("tests/fixtures/api").resolve()
            return RecordedLlmFixtureAdapter(fix_dir / "gemini_curate.json")
        if name == "gemini":
            return GeminiAdapter(
                api_key=self.settings.gemini_api_key or None,
                model=self.settings.llm_model,
            )
        if name == "openai_compat":
            oa_model = (
                self.settings.llm_model
                if (self.settings.llm_primary == "openai_compat" and not self.settings.llm_model.startswith("gemini"))
                else self.settings.llm_backup_model
            )
            return OpenAICompatibleAdapter(
                api_key=self.settings.openai_api_key or self.settings.groq_api_key or None,
                model=oa_model,
                base_url=self.settings.llm_backup_base_url,
            )
        return None

    def _build_llm_router(self) -> FailoverRouter[LlmAdapter]:
        primary = self._make_llm(self.settings.llm_primary) or GeminiAdapter(
            api_key=self.settings.gemini_api_key or None,
            model=self.settings.llm_model,
        )
        backup = self._make_llm(self.settings.llm_backup) if self.settings.llm_backup != self.settings.llm_primary else None
        return FailoverRouter(primary=primary, backup=backup)

    def reload_settings(self, new_settings: ServerSettings) -> None:
        """Hot-reload settings and rebuild STT/LLM routers in memory without restarting the server."""
        self.settings = new_settings
        self.stt_router = self._build_stt_router()
        self.llm_router = self._build_llm_router()

    async def run_download(self, fn: Callable[[], Awaitable[Path]]) -> Path:
        async with self._download_sem:
            return await fn()

    @staticmethod
    def _chunk_speech_ratio(chunk: AudioChunk, silences: Sequence[SilenceSpan]) -> float:
        """Compute active speech fraction in [0.0, 1.0] for an AudioChunk using pre-detected camera silences."""
        if chunk.duration <= 0.0 or not silences:
            return 1.0
        c_start = chunk.start_cam_sec
        c_end = chunk.end_cam_sec
        silent_sec = 0.0
        for s in silences:
            ov_s = max(c_start, s.start)
            ov_e = min(c_end, s.end)
            if ov_e > ov_s:
                silent_sec += ov_e - ov_s
        return max(0.0, min(1.0, 1.0 - (silent_sec / chunk.duration)))

    async def transcribe_chunk_cached(
        self,
        session_id: str,
        chunk: AudioChunk,
        sync: SyncResult,
        language: str,
        keyterms: Sequence[str],
        silences: Sequence[SilenceSpan],
        chunks_work_dir: Path,
    ) -> List[TranscriptWord]:
        """Transcribe one Opus chunk (cached by audio SHA-256; skips silent/AFK chunks; splits finer on 413)."""
        audio_p = Path(chunk.path)
        audio_digest = chunk.sha256 or _file_sha256(audio_p)
        task_hash = stable_hash(
            {
                "kind": "stt_chunk",
                "audio_sha256": audio_digest,
                "language": language,
                "keyterms": list(keyterms),
                "stt_primary": self.stt_router.primary.provider_name,
            }
        )

        # Principle #4: Never pay twice — check cached normalized words first
        cached_path = self.db.get_artifact_path(task_hash)
        if cached_path is not None:
            raw_words = json.loads(cached_path.read_text(encoding="utf-8"))
            chunk_words = [TranscriptWord.model_validate(w) for w in raw_words]
            return offset_and_map_words_to_master(chunk_words, chunk.start_cam_sec, sync.master_time)

        # VAD / Silence Pre-Filter: skip external STT billing if chunk (>=10s) is >=97% silence (AFK / BRB)
        if chunk.duration >= 10.0 and self._chunk_speech_ratio(chunk, silences) < 0.03:
            norm_file = self.norm_dir / f"stt_words_{task_hash}.json"
            norm_file.write_text("[]", encoding="utf-8")
            self.db.put_artifact(task_hash, "stt_words", norm_file)
            return []

        self.db.assert_within_budget(self.settings.max_budget_usd)
        tid = self.db.start_task(session_id, "stt_chunk", task_hash)

        # Billing is per second sent: upload only the speech (long silences cut out) and map timestamps back.
        speech_only = None
        if self.settings.stt_speech_only:
            try:
                speech_only = await asyncio.to_thread(
                    write_speech_only_opus, chunk, silences, chunks_work_dir / "speech_only"
                )
            except Exception:  # never lose a transcript over an optimization: send the original chunk
                speech_only = None
        sent_packed = {"value": False}

        def _transcribe(adapter: SttAdapter):
            use_packed = speech_only is not None and adapter.accepts_speech_only_audio
            sent_packed["value"] = use_packed
            return adapter.transcribe_chunk(
                audio_path=speech_only.path if use_packed else audio_p,
                duration_sec=speech_only.duration if use_packed else chunk.duration,
                language=language,
                keyterms=keyterms,
            )

        try:
            res = await self.stt_router.call(_transcribe)
        except PayloadTooLargeError:
            self.db.finish_task(tid, state="DONE", error="413 -> resplitting finer")
            sub_chunks = resplit_chunk_finer(chunk, chunks_work_dir, silences)
            sub_results = await asyncio.gather(
                *(
                    self.transcribe_chunk_cached(
                        session_id, sc, sync, language, keyterms, silences, chunks_work_dir
                    )
                    for sc in sub_chunks
                )
            )
            merged: List[TranscriptWord] = []
            for sr in sub_results:
                merged.extend(sr)
            return sorted(merged, key=lambda w: (w.start, w.end))
        except Exception as exc:
            self.db.finish_task(tid, state="FAILED", error=str(exc))
            raise

        # Persist raw API response BEFORE normalized artifact
        raw_file = self.raw_dir / f"stt_{task_hash}.raw.json"
        raw_file.write_text(json.dumps(res.raw_response, ensure_ascii=False, indent=2), encoding="utf-8")
        words = res.words
        if sent_packed["value"] and speech_only is not None:
            # The raw response is in packed time: keep the segment map next to it so it can be re-normalized.
            (self.raw_dir / f"stt_{task_hash}.packmap.json").write_text(
                json.dumps([s._asdict() for s in speech_only.segments]), encoding="utf-8"
            )
            words = remap_packed_words(res.words, speech_only.segments)
        self.db.record_api_call(
            session_id=session_id,
            task_hash=task_hash,
            provider=res.provider,
            model=res.model,
            kind="stt",
            raw_response_path=raw_file,
            units_billed=res.units_billed_sec,
            cost_usd=res.cost_usd,
            latency_ms=res.latency_ms,
        )

        norm_file = self.norm_dir / f"stt_words_{task_hash}.json"
        norm_file.write_text(
            json.dumps([w.model_dump(mode="json") for w in words], ensure_ascii=False, indent=1),
            encoding="utf-8",
        )
        self.db.put_artifact(task_hash, "stt_words", norm_file)
        self.db.finish_task(tid, state="DONE")

        return offset_and_map_words_to_master(words, chunk.start_cam_sec, sync.master_time)

    async def curate_window_cached(
        self,
        session_id: str,
        timeline_text: str,
        title: str,
        min_len: float,
        max_len: float,
        max_clips: int = 12,
    ) -> List[Dict[str, Any]]:
        """Curate compact timeline via LLM (cached by timeline + prompt version + model; raw saved before validation)."""
        task_hash = stable_hash(
            {
                "kind": "llm_curate",
                "timeline_sha256": hashlib.sha256(timeline_text.encode("utf-8")).hexdigest()[:24],
                "title": title,
                "min_len": min_len,
                "max_len": max_len,
                "prompt_version": CURATION_PROMPT_VERSION,
                "llm_primary": self.llm_router.primary.provider_name,
                "llm_model": self.settings.llm_model,
            }
        )

        cached_path = self.db.get_artifact_path(task_hash)
        if cached_path is not None:
            env = CurationEnvelope.model_validate_json(cached_path.read_text(encoding="utf-8"))
            return [c.model_dump(mode="json") for c in env.clips]

        self.db.assert_within_budget(self.settings.max_budget_usd)
        tid = self.db.start_task(session_id, "llm_curate", task_hash)
        call_counter = 0

        def _archive_raw(raw_call: RawLlmCallOutput) -> None:
            nonlocal call_counter
            call_counter += 1
            raw_file = self.raw_dir / f"llm_{task_hash}_{call_counter}.raw.json"
            raw_file.write_text(
                json.dumps(
                    {"raw_text": raw_call.raw_text, "payload": raw_call.raw_payload},
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
            self.db.record_api_call(
                session_id=session_id,
                task_hash=task_hash,
                provider=raw_call.provider,
                model=raw_call.model,
                kind="llm",
                raw_response_path=raw_file,
                units_billed=float(raw_call.input_tokens + raw_call.output_tokens),
                input_tokens=raw_call.input_tokens,
                output_tokens=raw_call.output_tokens,
                cost_usd=raw_call.cost_usd,
                latency_ms=raw_call.latency_ms,
            )

        try:
            res: LlmCurationResult = await self.llm_router.call(
                lambda adapter: adapter.curate_timeline(
                    timeline_text=timeline_text,
                    title=title,
                    min_len=min_len,
                    max_len=max_len,
                    max_clips=max_clips,
                    on_raw_call=_archive_raw,
                )
            )
        except Exception as exc:
            self.db.finish_task(tid, state="FAILED", error=str(exc))
            raise

        norm_file = self.norm_dir / f"llm_curated_{task_hash}.json"
        norm_file.write_text(res.envelope.model_dump_json(indent=2), encoding="utf-8")
        self.db.put_artifact(task_hash, "llm_curated", norm_file)
        self.db.finish_task(tid, state="DONE")
        return [c.model_dump(mode="json") for c in res.envelope.clips]

    async def aclose(self) -> None:
        await self.stt_router.primary.aclose()
        if self.stt_router.backup:
            await self.stt_router.backup.aclose()
        await self.llm_router.primary.aclose()
        if self.llm_router.backup:
            await self.llm_router.backup.aclose()
