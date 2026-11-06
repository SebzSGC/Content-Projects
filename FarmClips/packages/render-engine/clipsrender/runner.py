"""Async FFmpeg render executor with `-progress pipe:1`, NVENC -> libx264 fallback, and hash cache."""

from __future__ import annotations

import asyncio
import shutil
import subprocess
import threading
from pathlib import Path
from typing import Callable, List, Optional, Protocol

from clipscore.domain import SyncResult
from clipseditplan import EditPlan
from clipsmedia.ffmpeg import FfmpegError, resolve_binary
from clipsstyles import StylePreset, get_fonts_dir

from .ass_compiler import compile_ass
from .fast_compositor import measure_plan_loudnorm_pass1, render_fast_affine_sync
from .filtergraph import CompiledRenderCommand, RenderQuality, compile_ffmpeg_plan

ProgressCallback = Callable[[float, str], None]


class RenderBackend(Protocol):
    """Decoupled render backend interface so rendering can move to a remote GPU machine without touching orchestrator."""

    async def render_plan(
        self,
        plan: EditPlan,
        preset: StylePreset,
        gameplay_path: Path,
        camera_path: Path,
        sync: SyncResult,
        out_dir: Path,
        quality: RenderQuality = "final",
        clean_game_audio_stream: Optional[int] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Path: ...


def nvenc_encoder_args(quality: RenderQuality) -> List[str]:
    if quality == "draft":
        return ["-c:v", "h264_nvenc", "-preset", "p1", "-rc", "vbr", "-cq", "26", "-b:v", "0"]
    return ["-c:v", "h264_nvenc", "-preset", "p3", "-rc", "vbr", "-cq", "20", "-b:v", "0"]


def libx264_encoder_args(quality: RenderQuality) -> List[str]:
    if quality == "draft":
        return ["-c:v", "libx264", "-preset", "veryfast", "-crf", "25"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "19"]


def _run_ffmpeg_with_progress_sync(
    cmd: List[str],
    duration_sec: float,
    timeout_sec: float,
    emit_progress: Optional[Callable[[float], None]],
) -> None:
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    stderr_lines: List[str] = []

    def _drain_stderr() -> None:
        assert proc.stderr is not None
        for line in proc.stderr:
            stderr_lines.append(line.rstrip())
            if len(stderr_lines) > 40:
                stderr_lines.pop(0)

    err_thread = threading.Thread(target=_drain_stderr, daemon=True)
    err_thread.start()

    try:
        assert proc.stdout is not None
        for raw_line in proc.stdout:
            line = raw_line.strip()
            if line.startswith("out_time_us=") and emit_progress and duration_sec > 0:
                try:
                    us = int(line.split("=", 1)[1])
                    frac = max(0.0, min(0.99, (us / 1_000_000.0) / duration_sec))
                    emit_progress(frac)
                except ValueError:
                    pass
        proc.wait(timeout=timeout_sec)
    except subprocess.TimeoutExpired as exc:
        proc.kill()
        raise FfmpegError(f"Timeout de renderizado ({timeout_sec:.0f}s) excedido.") from exc
    finally:
        err_thread.join(timeout=2.0)

    if proc.returncode != 0:
        tail = "\n".join(stderr_lines[-18:])
        raise FfmpegError(f"FFmpeg render falló ({proc.returncode}):\n{tail}")


class LocalFfmpegRenderBackend:
    def __init__(
        self,
        use_nvenc: bool = True,
        cache_dir: Optional[Path] = None,
        use_fast_affine: bool = True,
        two_pass_loudnorm: bool = True,
    ) -> None:
        self.use_nvenc = use_nvenc
        self.cache_dir = cache_dir
        self.use_fast_affine = use_fast_affine
        self.two_pass_loudnorm = two_pass_loudnorm

    async def render_plan(
        self,
        plan: EditPlan,
        preset: StylePreset,
        gameplay_path: Path,
        camera_path: Path,
        sync: SyncResult,
        out_dir: Path,
        quality: RenderQuality = "final",
        clean_game_audio_stream: Optional[int] = None,
        on_progress: Optional[ProgressCallback] = None,
    ) -> Path:
        out_dir.mkdir(parents=True, exist_ok=True)
        render_key = plan.plan_hash(style_hash=preset.content_hash(), quality=quality)
        final_mp4 = out_dir / f"{plan.clip_id or 'clip'}_{quality}_{render_key[:10]}.mp4"

        if self.cache_dir is not None:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            cached_mp4 = self.cache_dir / f"render_{render_key}.mp4"
            if cached_mp4.is_file() and cached_mp4.stat().st_size > 1024:
                if cached_mp4.resolve() != final_mp4.resolve():
                    shutil.copy2(cached_mp4, final_mp4)
                if on_progress:
                    on_progress(1.0, "Clip recuperado de caché por hash")
                return final_mp4
        else:
            cached_mp4 = None

        if final_mp4.is_file() and final_mp4.stat().st_size > 1024:
            if on_progress:
                on_progress(1.0, "Clip ya renderizado")
            return final_mp4

        render_w = 540 if quality == "draft" else plan.output.w
        render_h = 960 if quality == "draft" else plan.output.h

        ass_path = out_dir / f"{render_key}.ass"
        ass_text = compile_ass(plan, preset, render_w, render_h)
        ass_path.write_text(ass_text, encoding="utf-8")

        # Optional 2-pass linear EBU R128 loudness measurement on final exports (<0.4s audio-only pass)
        loudnorm_stats = None
        if quality == "final" and self.two_pass_loudnorm:
            if on_progress:
                on_progress(0.02, "Midiendo sonoridad EBU R128 (-14 LUFS lineal, pasada 1)")
            loudnorm_stats = await asyncio.to_thread(
                measure_plan_loudnorm_pass1,
                plan,
                preset,
                gameplay_path,
                camera_path,
                sync,
                clean_game_audio_stream,
            )

        compiled: CompiledRenderCommand = compile_ffmpeg_plan(
            plan=plan,
            preset=preset,
            gameplay_path=gameplay_path,
            camera_path=camera_path,
            sync=sync,
            ass_path=ass_path,
            fonts_dir=get_fonts_dir(),
            quality=quality,
            clean_game_audio_stream=clean_game_audio_stream,
            loudnorm_stats=loudnorm_stats,
        )

        # Always persist .ffscript for auditability / standalone FFmpeg debugging
        ffscript_path = out_dir / f"{render_key}.ffscript"
        ffscript_path.write_text(compiled.filtergraph, encoding="utf-8")

        tmp_mp4 = final_mp4.with_suffix(".rendering.mp4")
        timeout_sec = max(90.0, compiled.duration * 8.0)

        loop = asyncio.get_running_loop()

        def _emit(frac: float) -> None:
            if on_progress:
                loop.call_soon_threadsafe(on_progress, frac, f"Codificando {quality} ({int(frac * 100)}%)")

        if on_progress:
            mode_lbl = "warpAffine C++" if self.use_fast_affine else "FFmpeg filtergraph"
            on_progress(0.04, f"Iniciando render {quality} ({render_w}x{render_h}, {mode_lbl})")

        if self.use_fast_affine:
            async def _run_fast(enc_flags: List[str]) -> None:
                await asyncio.to_thread(
                    render_fast_affine_sync,
                    plan,
                    preset,
                    gameplay_path,
                    camera_path,
                    sync,
                    ass_path,
                    get_fonts_dir(),
                    tmp_mp4,
                    enc_flags,
                    quality,
                    clean_game_audio_stream,
                    loudnorm_stats,
                    timeout_sec,
                    _emit,
                )

            if self.use_nvenc:
                try:
                    await _run_fast(nvenc_encoder_args(quality))
                except FfmpegError:
                    tmp_mp4.unlink(missing_ok=True)
                    if on_progress:
                        on_progress(0.06, "NVENC no disponible o ocupado; reintentando con libx264")
                    await _run_fast(libx264_encoder_args(quality))
            else:
                await _run_fast(libx264_encoder_args(quality))
        else:
            inline_fg = compiled.filtergraph.replace("\n", "")
            fg_args = (
                ["-filter_complex", inline_fg]
                if len(inline_fg) < 16_000
                else ["-/filter_complex", str(ffscript_path)]
            )

            def _make_cmd(encoder_flags: List[str]) -> List[str]:
                return [
                    resolve_binary("ffmpeg"),
                    "-hide_banner",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-y",
                    "-progress",
                    "pipe:1",
                    "-nostats",
                    *compiled.input_args,
                    *fg_args,
                    *compiled.output_args,
                    *encoder_flags,
                    str(tmp_mp4),
                ]

            if self.use_nvenc:
                try:
                    await asyncio.to_thread(
                        _run_ffmpeg_with_progress_sync,
                        _make_cmd(nvenc_encoder_args(quality)),
                        compiled.duration,
                        timeout_sec,
                        _emit,
                    )
                except FfmpegError:
                    tmp_mp4.unlink(missing_ok=True)
                    if on_progress:
                        on_progress(0.05, "NVENC no disponible o ocupado; reintentando con libx264")
                    await asyncio.to_thread(
                        _run_ffmpeg_with_progress_sync,
                        _make_cmd(libx264_encoder_args(quality)),
                        compiled.duration,
                        timeout_sec,
                        _emit,
                    )
            else:
                await asyncio.to_thread(
                    _run_ffmpeg_with_progress_sync,
                    _make_cmd(libx264_encoder_args(quality)),
                    compiled.duration,
                    timeout_sec,
                    _emit,
                )

        tmp_mp4.replace(final_mp4)
        if cached_mp4 is not None and cached_mp4.resolve() != final_mp4.resolve():
            shutil.copy2(final_mp4, cached_mp4)
        if on_progress:
            on_progress(1.0, "Render completado")
        return final_mp4
