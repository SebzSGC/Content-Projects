"""Render pipeline: Ken Burns, exact xfade chaining, Node sidecar (HTML/SVG & WebGL), ASS burn-in, and NVENC/x264 encoding."""

from __future__ import annotations

import json
import shutil
import uuid
from pathlib import Path
from typing import Any, Callable

from vidforge.domain.models import ClipModel, TimelineModel, TranscriptModel
from vidforge.infra.db import db
from vidforge.infra.hw import detect_hardware
from vidforge.infra.paths import (
    SIDECAR_SCRIPT,
    TEMP_DIR,
    TEMPLATES_DIR,
    get_chrome_path,
    get_ffmpeg_path,
    get_node_path,
)
from vidforge.infra.procs import run_ffmpeg_with_progress, run_hidden, spawn_hidden
from vidforge.services.asr import export_ass
from vidforge.services.media_gen import generate_visual_image


def compute_xfade_schedule(
    slot_durations_us: list[int],
    transition_durations_us: list[int],
) -> tuple[list[int], list[int], int]:
    """
    Given n logical slot durations s_0..s_{n-1} and n-1 transition durations t_1..t_{n-1}:
    Returns (clip_durations_d, xfade_offsets, total_duration_us) such that:
      d_i = s_i + t_{i+1} (for i < n-1) and d_{n-1} = s_{n-1}
      offset_k = sum_{i < k} s_i
      total_duration = sum(d_i) - sum(t_k) == sum(s_i)
    """
    n = len(slot_durations_us)
    if n == 0:
        return [], [], 0
    if len(transition_durations_us) != n - 1:
        raise ValueError("transition_durations_us must have length len(slot_durations_us) - 1")

    clamped_t: list[int] = []
    for k, t_val in enumerate(transition_durations_us):
        max_allowed = min(slot_durations_us[k], slot_durations_us[k + 1]) // 2
        clamped_t.append(max(0, min(int(t_val), max_allowed)))

    clip_d: list[int] = []
    for i in range(n):
        ext = clamped_t[i] if i < n - 1 else 0
        clip_d.append(int(slot_durations_us[i]) + ext)

    offsets: list[int] = []
    running = 0
    for k in range(n - 1):
        running += int(slot_durations_us[k])
        offsets.append(running)

    total_us = sum(clip_d) - sum(clamped_t)
    return clip_d, offsets, total_us


def render_motion_scene_via_sidecar(
    template_id: str,
    props: dict[str, Any],
    duration_us: int,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
    alpha: bool = True,
    on_progress: Callable[[float], None] | None = None,
) -> Path:
    template_dir = TEMPLATES_DIR / template_id
    if not template_dir.exists():
        raise FileNotFoundError(f"Template not found: {template_id}")

    job_id = f"sc_{uuid.uuid4().hex[:8]}"
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    hw = detect_hardware()
    req = {
        "protocol": "vidforge.render/1",
        "job_id": job_id,
        "task": {
            "kind": "template",
            "template_dir": str(template_dir.resolve()),
            "props": props,
            "duration_us": int(duration_us),
        },
        "output": {
            "path": str(output_path.resolve()),
            "format": "webm_vp9_alpha" if alpha else "mp4_h264",
            "width": width,
            "height": height,
            "fps": {"num": fps, "den": 1},
            "encoder": hw["preferred_encoder"],
        },
        "runtime": {
            "chrome_path": get_chrome_path(),
            "ffmpeg_path": get_ffmpeg_path(),
            "work_dir": str(work_dir.resolve()),
            "gpu": bool(hw["encoders"]["h264_nvenc"]),
            "timeout_s": 300,
        },
    }
    req_file = work_dir / "request.json"
    req_file.write_text(json.dumps(req, indent=2), encoding="utf-8")

    proc = spawn_hidden([get_node_path(), str(SIDECAR_SCRIPT), "--request", str(req_file)], cwd=work_dir)
    last_err = ""
    try:
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("type") == "progress" and on_progress:
                total = max(1, int(ev.get("total", 1)))
                frame = int(ev.get("frame", 0))
                on_progress(min(0.99, frame / total))
            elif ev.get("type") == "error":
                last_err = ev.get("message", "Unknown sidecar error")
        rc = proc.wait(timeout=300)
        if rc != 0:
            stderr_txt = proc.stderr.read() if proc.stderr else ""
            raise RuntimeError(f"Sidecar failed (rc={rc}): {last_err or stderr_txt[-400:]}")
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)

    return output_path


def render_gl_transition_via_sidecar(
    transition_name: str,
    frames_a_dir: Path,
    frames_b_dir: Path,
    frame_count: int,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    fps: int = 30,
) -> Path:
    job_id = f"gl_{uuid.uuid4().hex[:8]}"
    work_dir = TEMP_DIR / job_id
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    hw = detect_hardware()
    req = {
        "protocol": "vidforge.render/1",
        "job_id": job_id,
        "task": {
            "kind": "gl_transition",
            "transition": transition_name,
            "frames_a_dir": str(frames_a_dir.resolve()),
            "frames_b_dir": str(frames_b_dir.resolve()),
            "frame_count": frame_count,
        },
        "output": {
            "path": str(output_path.resolve()),
            "format": "mp4_h264",
            "width": width,
            "height": height,
            "fps": {"num": fps, "den": 1},
            "encoder": hw["preferred_encoder"],
        },
        "runtime": {
            "chrome_path": get_chrome_path(),
            "ffmpeg_path": get_ffmpeg_path(),
            "work_dir": str(work_dir.resolve()),
            "gpu": True,
            "timeout_s": 180,
        },
    }
    req_file = work_dir / "request.json"
    req_file.write_text(json.dumps(req, indent=2), encoding="utf-8")
    res = run_hidden([get_node_path(), str(SIDECAR_SCRIPT), "--request", str(req_file)], cwd=work_dir, timeout=180.0)
    shutil.rmtree(work_dir, ignore_errors=True)
    if res.returncode != 0:
        raise RuntimeError(f"GL transition sidecar failed: {res.stdout[-300:]} {res.stderr[-300:]}")
    return output_path


def _prepare_single_clip_segment(
    clip: ClipModel,
    target_duration_us: int,
    out_clip_path: Path,
    width: int,
    height: int,
    fps: int,
    encoder: str,
    idx: int,
) -> Path:
    ff = get_ffmpeg_path()
    dur_s = max(0.2, target_duration_us / 1_000_000.0)
    total_frames = max(2, int(round(dur_s * fps)))

    asset = db.get_asset(clip.asset_id) if clip.asset_id else None
    source_path = Path(asset["file_path"]) if (asset and Path(asset["file_path"]).exists()) else None
    if source_path is None:
        fallback_img = out_clip_path.with_suffix(".fallback.png")
        generate_visual_image(f"Escena #{idx + 1}", fallback_img, width=width, height=height, beat_index=idx)
        source_path = fallback_img

    is_image = source_path.suffix.lower() in (".png", ".jpg", ".jpeg", ".webp", ".bmp")
    v_enc = (
        ["-c:v", "h264_nvenc", "-preset", "p3", "-cq", "20"]
        if encoder == "h264_nvenc"
        else ["-c:v", "libx264", "-preset", "ultrafast", "-crf", "20"]
    )

    if is_image:
        kb = clip.effects[0] if clip.effects else None
        z_from = kb.zoom_from if kb else 1.03
        z_diff = (kb.zoom_to - kb.zoom_from) if kb else 0.07
        pan = kb.pan if kb else "none"
        if pan == "left_right":
            x_expr = f"(iw-iw/zoom)*(on/{total_frames})"
            y_expr = "ih/2-(ih/zoom/2)"
        elif pan == "right_left":
            x_expr = f"(iw-iw/zoom)*(1-on/{total_frames})"
            y_expr = "ih/2-(ih/zoom/2)"
        else:
            x_expr = "iw/2-(iw/zoom/2)"
            y_expr = "ih/2-(ih/zoom/2)"

        # Overscale by 1.5x before zoompan to prevent rounding jitter while keeping speed fast
        pre_w = int(width * 1.5)
        pre_h = int(height * 1.5)
        vf = (
            f"scale={pre_w}:{pre_h}:force_original_aspect_ratio=increase,crop={pre_w}:{pre_h},"
            f"zoompan=z='{z_from:.3f}+{z_diff:.3f}*on/{total_frames}':"
            f"x='{x_expr}':y='{y_expr}':d={total_frames}:s={width}x{height}:fps={fps},"
            f"setsar=1,format=yuv420p"
        )
        args = [
            ff,
            "-y",
            "-loop",
            "1",
            "-i",
            str(source_path),
            "-vf",
            vf,
            "-t",
            f"{dur_s:.4f}",
            *v_enc,
            "-pix_fmt",
            "yuv420p",
            str(out_clip_path),
        ]
    else:
        vf = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
            f"setsar=1,fps={fps},tpad=stop_mode=clone:stop_duration={dur_s:.4f},format=yuv420p"
        )
        args = [
            ff,
            "-y",
            "-i",
            str(source_path),
            "-vf",
            vf,
            "-t",
            f"{dur_s:.4f}",
            "-an",
            *v_enc,
            "-pix_fmt",
            "yuv420p",
            str(out_clip_path),
        ]

    res = run_hidden(args, timeout=180.0)
    if res.returncode != 0:
        raise RuntimeError(f"Clip preparation failed for {clip.id}: {res.stderr[-400:]}")
    return out_clip_path


def render_timeline_to_mp4(
    timeline: TimelineModel,
    output_path: Path,
    transcript: TranscriptModel | None = None,
    burn_subtitles: bool = True,
    render_motion_overlays: bool = True,
    on_progress: Callable[[float, str], None] | None = None,
) -> Path:
    """Renders a multi-track TimelineModel into the final MP4 with xfade, motion overlays, ASS subtitles and audio."""
    ff = get_ffmpeg_path()
    hw = detect_hardware()
    encoder = hw["preferred_encoder"]
    width = timeline.canvas.width
    height = timeline.canvas.height
    fps = int(round(timeline.canvas.fps.float_val))

    work_dir = TEMP_DIR / f"render_{uuid.uuid4().hex[:8]}"
    work_dir.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        video_track = next((t for t in timeline.tracks if t.kind == "video"), None)
        v_clips = video_track.clips if video_track else []
        if not v_clips:
            v_clips = [
                ClipModel(
                    id="default_clip",
                    start_us=0,
                    duration_us=max(1_000_000, timeline.duration_us),
                )
            ]

        slot_durations = [c.duration_us for c in v_clips]
        trans_durations = [
            (c.transition_in.duration_us if (c.transition_in and c.transition_in.kind != "cut") else 0)
            for c in v_clips[1:]
        ]
        clip_d_us, offsets_us, total_us = compute_xfade_schedule(slot_durations, trans_durations)

        prepared_clips: list[Path] = []
        for idx, (clip, d_us) in enumerate(zip(v_clips, clip_d_us)):
            if on_progress:
                on_progress(0.05 + 0.40 * (idx / len(v_clips)), f"Preparando clip {idx + 1}/{len(v_clips)}")
            c_path = work_dir / f"prep_{idx:03d}.mp4"
            _prepare_single_clip_segment(clip, d_us, c_path, width, height, fps, encoder, idx)
            prepared_clips.append(c_path)

        # Chain clips with xfade in chunks of up to 12 clips
        if on_progress:
            on_progress(0.50, "Encadenando transiciones xfade")

        visual_master = work_dir / "visual_master.mp4"
        if len(prepared_clips) == 1:
            shutil.copy2(prepared_clips[0], visual_master)
        else:
            inputs: list[str] = []
            for p in prepared_clips:
                inputs.extend(["-i", str(p)])
            filter_parts: list[str] = []
            prev_label = "[0:v]"
            for k in range(len(prepared_clips) - 1):
                next_in = f"[{k + 1}:v]"
                out_lbl = f"[v{k + 1}]"
                t_spec = v_clips[k + 1].transition_in
                t_name = t_spec.name if (t_spec and t_spec.kind == "xfade") else "fade"
                t_dur_s = max(0.05, (trans_durations[k] / 1_000_000.0)) if trans_durations[k] > 0 else 0.05
                off_s = max(0.0, offsets_us[k] / 1_000_000.0)
                if trans_durations[k] <= 0:
                    t_name = "fade"
                    t_dur_s = 0.02
                filter_parts.append(
                    f"{prev_label}{next_in}xfade=transition={t_name}:duration={t_dur_s:.4f}:offset={off_s:.4f}{out_lbl}"
                )
                prev_label = out_lbl

            v_enc = (
                ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"]
                if encoder == "h264_nvenc"
                else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19"]
            )
            run_ffmpeg_with_progress(
                ff,
                [
                    "-y",
                    *inputs,
                    "-filter_complex",
                    ";".join(filter_parts),
                    "-map",
                    prev_label,
                    *v_enc,
                    "-pix_fmt",
                    "yuv420p",
                    str(visual_master),
                ],
                total_duration_us=total_us,
                cwd=work_dir,
            )

        current_video = visual_master

        # Render & overlay motion graphics scenes if present
        motion_track = next((t for t in timeline.tracks if t.kind == "motion" and not t.muted), None)
        if render_motion_overlays and motion_track and motion_track.clips:
            for m_idx, m_clip in enumerate(motion_track.clips):
                if not m_clip.motion:
                    continue
                if on_progress:
                    on_progress(0.68, f"Renderizando gráfico animado ({m_clip.motion.template_id})")
                webm_path = work_dir / f"motion_{m_idx:02d}.webm"
                render_motion_scene_via_sidecar(
                    template_id=m_clip.motion.template_id,
                    props=m_clip.motion.props,
                    duration_us=m_clip.duration_us,
                    output_path=webm_path,
                    width=width,
                    height=height,
                    fps=min(30, fps),
                    alpha=True,
                )
                overlaid = work_dir / f"visual_m_{m_idx:02d}.mp4"
                st_s = m_clip.start_us / 1_000_000.0
                en_s = (m_clip.start_us + m_clip.duration_us) / 1_000_000.0
                v_enc = (
                    ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "20"]
                    if encoder == "h264_nvenc"
                    else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "19"]
                )
                res = run_hidden(
                    [
                        ff,
                        "-y",
                        "-i",
                        str(current_video),
                        "-c:v",
                        "libvpx-vp9",
                        "-itsoffset",
                        f"{st_s:.3f}",
                        "-i",
                        str(webm_path),
                        "-filter_complex",
                        f"[1:v]scale={width}:{height}[ov];[0:v][ov]overlay=0:0:enable='between(t,{st_s:.3f},{en_s:.3f})':eof_action=pass[outv]",
                        "-map",
                        "[outv]",
                        *v_enc,
                        "-pix_fmt",
                        "yuv420p",
                        str(overlaid),
                    ],
                    cwd=work_dir,
                    timeout=180.0,
                )
                if res.returncode == 0 and overlaid.exists():
                    current_video = overlaid

        # Burn ASS subtitles & mux master audio
        if on_progress:
            on_progress(0.85, "Mezclando audio y subtítulos ASS")

        audio_track = next((t for t in timeline.tracks if t.kind == "audio" and not t.muted), None)
        audio_input_path: Path | None = None
        if audio_track and audio_track.clips and audio_track.clips[0].asset_id:
            a_asset = db.get_asset(audio_track.clips[0].asset_id)
            if a_asset and Path(a_asset["file_path"]).exists():
                audio_input_path = Path(a_asset["file_path"])

        vf_final: list[str] = []
        if burn_subtitles and transcript and transcript.segments:
            ass_file = work_dir / "subs.ass"
            style = timeline.subtitle_styles[0] if timeline.subtitle_styles else None
            ass_content = export_ass(transcript, style=style, width=width, height=height, karaoke=True)
            ass_file.write_text(ass_content, encoding="utf-8")
            # Relative path in cwd avoids Windows drive colon escaping issues in FFmpeg ass filter
            vf_final.extend(["-vf", "ass=subs.ass"])

        v_enc_final = (
            ["-c:v", "h264_nvenc", "-preset", "p4", "-cq", "19"]
            if encoder == "h264_nvenc"
            else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "18"]
        )

        final_args = ["-y", "-i", str(current_video)]
        if audio_input_path:
            final_args.extend(["-i", str(audio_input_path)])
        if vf_final:
            final_args.extend(vf_final)
        else:
            final_args.extend(["-c:v", "copy"])

        if vf_final:
            final_args.extend([*v_enc_final, "-pix_fmt", "yuv420p"])

        if audio_input_path:
            final_args.extend(["-c:a", "aac", "-b:a", "192k", "-shortest"])

        final_args.extend(["-movflags", "+faststart", str(output_path.resolve())])
        run_ffmpeg_with_progress(
            ff,
            final_args,
            total_duration_us=total_us,
            on_progress=(lambda p: on_progress(0.85 + 0.14 * p, "Codificando MP4 final")) if on_progress else None,
            cwd=work_dir,
        )
        if on_progress:
            on_progress(1.0, "Renderizado finalizado")
        return output_path
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
