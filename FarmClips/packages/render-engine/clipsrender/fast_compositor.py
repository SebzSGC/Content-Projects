"""High-speed C++ OpenCV `cv2.warpAffine` compositor + 2-pass linear EBU R128 `loudnorm` helper.

Replaces FFmpeg's per-frame `scale(..., eval=frame)` dynamic filtergraph reconfiguration (~28s on 1080p)
with sub-pixel smooth `cv2.warpAffine` composition streamed into `h264_nvenc` / `libx264` + static `libass`.
"""

from __future__ import annotations

import json
import math
import queue
import re
import subprocess
import threading
from pathlib import Path
from typing import Callable, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np
from PIL import Image

from clipscore.domain import SyncResult
from clipseditplan import CropKeyframe, EditPlan
from clipsmedia.ffmpeg import FfmpegError, resolve_binary
from clipsstyles import StylePreset, ensure_emoji_png, ensure_sfx_wav

from .filtergraph import RenderQuality, _even, quote_filter_path


def eval_ease(u: float, ease: Optional[str]) -> float:
    u = max(0.0, min(1.0, u))
    if ease == "outBack":
        c1 = 1.70158
        c3 = c1 + 1.0
        return 1.0 + c3 * ((u - 1.0) ** 3) + c1 * ((u - 1.0) ** 2)
    if ease == "inOutSine":
        return 0.5 * (1.0 - math.cos(math.pi * u))
    if ease == "outCubic":
        return 1.0 - ((1.0 - u) ** 3)
    return u


def eval_crop_keyframes(
    keyframes: Sequence[CropKeyframe],
    t: float,
    default_cx: float = 0.5,
    default_cy: float = 0.5,
    default_zoom: float = 1.0,
) -> Tuple[float, float, float]:
    """Interpolate (cx, cy, zoom) at clip time `t` matching EditPlan v2 easing curves."""
    if not keyframes:
        return default_cx, default_cy, default_zoom
    if t <= keyframes[0].t or len(keyframes) == 1:
        k0 = keyframes[0]
        return (
            max(0.05, min(0.95, float(k0.cx))),
            max(0.05, min(0.95, float(k0.cy))),
            max(1.0, min(3.0, float(k0.zoom))),
        )
    if t >= keyframes[-1].t:
        kl = keyframes[-1]
        return (
            max(0.05, min(0.95, float(kl.cx))),
            max(0.05, min(0.95, float(kl.cy))),
            max(1.0, min(3.0, float(kl.zoom))),
        )

    # Binary search / linear scan (typically <= 60 keyframes per clip)
    lo, hi = 0, len(keyframes) - 1
    while lo + 1 < hi:
        mid = (lo + hi) // 2
        if keyframes[mid].t <= t:
            lo = mid
        else:
            hi = mid
    ka, kb = keyframes[lo], keyframes[hi]
    dt = max(1e-4, kb.t - ka.t)
    eu = eval_ease((t - ka.t) / dt, getattr(kb, "ease", None))
    cx = ka.cx + (kb.cx - ka.cx) * eu
    cy = ka.cy + (kb.cy - ka.cy) * eu
    zoom = ka.zoom + (kb.zoom - ka.zoom) * eu
    return (
        max(0.05, min(0.95, cx)),
        max(0.05, min(0.95, cy)),
        max(1.0, min(3.0, zoom)),
    )


def compute_cover_affine_matrix(
    sw: int,
    sh: int,
    tw: int,
    th: int,
    cx: float,
    cy: float,
    zoom: float,
    anchor_y: float = 0.44,
) -> np.ndarray:
    """Compute forward 2x3 affine matrix M for `cv2.warpAffine` mapping source (sw, sh) into cover box (tw, th)."""
    base_s = max(tw / max(1.0, float(sw)), th / max(1.0, float(sh)))
    s = base_s * max(1.0, float(zoom))
    scaled_w = sw * s
    scaled_h = sh * s
    crop_x = min(max(0.0, scaled_w * cx - tw * 0.50), max(0.0, scaled_w - tw))
    crop_y = min(max(0.0, scaled_h * cy - th * anchor_y), max(0.0, scaled_h - th))
    return np.array([[s, 0.0, -crop_x], [0.0, s, -crop_y]], dtype=np.float32)


def build_audio_filtergraph(
    plan: EditPlan,
    preset: StylePreset,
    sync: SyncResult,
    cam_seek: float,
    game_seek: float,
    cam_input_idx: int,
    game_input_idx: int,
    sfx_inputs: Sequence[Tuple[int, float, float]],
    clean_game_audio_stream: Optional[int],
    loudnorm_stats: Optional[Dict[str, str]] = None,
    measure_only: bool = False,
) -> List[str]:
    """Build FFmpeg audio trim/concat + sidechain ducking + SFX + EBU R128 loudnorm filter chain."""
    ranges = plan.source.ranges
    n_seg = len(ranges)
    fg: List[str] = []

    if n_seg == 1:
        a, b = ranges[0]
        ga, gb = max(0.0, a - game_seek), max(0.05, b - game_seek)
        if clean_game_audio_stream is not None:
            mca = max(0.0, sync.camera_time(a) - cam_seek)
            mcb = max(mca + 0.05, sync.camera_time(b) - cam_seek)
            fg.append(f"[{cam_input_idx}:a:0]atrim=start={mca:.3f}:end={mcb:.3f},asetpts=PTS-STARTPTS[mic_a]")
            fg.append(f"[{game_input_idx}:a:{clean_game_audio_stream}]atrim=start={ga:.3f}:end={gb:.3f},asetpts=PTS-STARTPTS[game_a]")
        else:
            fg.append(f"[{game_input_idx}:a:0]atrim=start={ga:.3f}:end={gb:.3f},asetpts=PTS-STARTPTS[mix_a]")
    else:
        if clean_game_audio_stream is not None:
            fg.append(f"[{cam_input_idx}:a:0]asplit={n_seg}" + "".join(f"[ma{i}]" for i in range(n_seg)))
            fg.append(f"[{game_input_idx}:a:{clean_game_audio_stream}]asplit={n_seg}" + "".join(f"[ga{i}]" for i in range(n_seg)))
        else:
            fg.append(f"[{game_input_idx}:a:0]asplit={n_seg}" + "".join(f"[xa{i}]" for i in range(n_seg)))

        for i, (a, b) in enumerate(ranges):
            ga, gb = max(0.0, a - game_seek), max(0.05, b - game_seek)
            if clean_game_audio_stream is not None:
                mca = max(0.0, sync.camera_time(a) - cam_seek)
                mcb = max(mca + 0.05, sync.camera_time(b) - cam_seek)
                fg.append(f"[ma{i}]atrim=start={mca:.3f}:end={mcb:.3f},asetpts=PTS-STARTPTS[mas{i}]")
                fg.append(f"[ga{i}]atrim=start={ga:.3f}:end={gb:.3f},asetpts=PTS-STARTPTS[gas{i}]")
            else:
                fg.append(f"[xa{i}]atrim=start={ga:.3f}:end={gb:.3f},asetpts=PTS-STARTPTS[xas{i}]")

        if clean_game_audio_stream is not None:
            fg.append("".join(f"[mas{i}]" for i in range(n_seg)) + f"concat=n={n_seg}:v=0:a=1[mic_a]")
            fg.append("".join(f"[gas{i}]" for i in range(n_seg)) + f"concat=n={n_seg}:v=0:a=1[game_a]")
        else:
            fg.append("".join(f"[xas{i}]" for i in range(n_seg)) + f"concat=n={n_seg}:v=0:a=1[mix_a]")

    mic_gain = plan.audio.mic_gain_db
    duck_db = plan.audio.duck_game_db
    if clean_game_audio_stream is not None:
        ratio = max(2.0, min(12.0, abs(duck_db) * 0.7))
        fg.append(f"[mic_a]aresample=48000,highpass=f=75,volume={mic_gain:.1f}dB,asplit=2[mic_sc][mic_mix]")
        fg.append("[game_a]aresample=48000[game_rs]")
        fg.append(f"[game_rs][mic_sc]sidechaincompress=threshold=0.035:ratio={ratio:.1f}:attack=15:release=260[game_duck]")
        fg.append("[mic_mix][game_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[base_a]")
    else:
        boost = mic_gain * 0.5
        fg.append(f"[mix_a]aresample=48000,highpass=f=70,equalizer=f=3000:t=q:w=1.2:g=2.5,volume={boost:.1f}dB[base_a]")

    cur_a = "[base_a]"
    if sfx_inputs:
        mix_labels = [cur_a]
        for s_i, (inp_i, cue_t, gain_db) in enumerate(sfx_inputs):
            delay_ms = max(0, int(round(cue_t * 1000.0)))
            lbl = f"[sfx{s_i}]"
            fg.append(f"[{inp_i}:a]aresample=48000,volume={gain_db:.1f}dB,adelay={delay_ms}|{delay_ms}{lbl}")
            mix_labels.append(lbl)
        fg.append("".join(mix_labels) + f"amix=inputs={len(mix_labels)}:duration=first:normalize=0[pre_loud]")
        cur_a = "[pre_loud]"

    target_i = preset.format.target_lufs
    if measure_only:
        fg.append(f"{cur_a}loudnorm=I={target_i:.1f}:TP=-1.5:LRA=11:print_format=json[a_out]")
    elif loudnorm_stats and "input_i" in loudnorm_stats:
        fg.append(
            f"{cur_a}loudnorm=I={target_i:.1f}:TP=-1.5:LRA=11:"
            f"measured_I={loudnorm_stats['input_i']}:"
            f"measured_TP={loudnorm_stats['input_tp']}:"
            f"measured_LRA={loudnorm_stats['input_lra']}:"
            f"measured_thresh={loudnorm_stats['input_thresh']}:"
            f"linear=true,aresample=48000[a_out]"
        )
    else:
        fg.append(f"{cur_a}loudnorm=I={target_i:.1f}:TP=-1.5:LRA=11,aresample=48000[a_out]")
    return fg


def measure_plan_loudnorm_pass1(
    plan: EditPlan,
    preset: StylePreset,
    gameplay_path: Path,
    camera_path: Path,
    sync: SyncResult,
    clean_game_audio_stream: Optional[int] = None,
) -> Optional[Dict[str, str]]:
    """Run ultra-fast (<0.4s) audio-only pass (`-vn`) to measure EBU R128 loudness for linear pass 2."""
    ranges = plan.source.ranges
    total_dur = plan.total_duration()
    min_master_s, max_master_e = ranges[0][0], ranges[-1][1]
    game_seek = max(0.0, min_master_s - 0.25)
    game_read_dur = (max_master_e - game_seek) + 0.75

    min_cam_s, max_cam_e = sync.camera_time(min_master_s), sync.camera_time(max_master_e)
    cam_seek = max(0.0, min_cam_s - 0.35)
    cam_read_dur = max(1.0, max_cam_e - cam_seek + 1.0)

    input_args: List[str] = [
        "-vn", "-ss", f"{cam_seek:.3f}", "-t", f"{cam_read_dur:.3f}", "-i", str(camera_path),
        "-vn", "-ss", f"{game_seek:.3f}", "-t", f"{game_read_dur:.3f}", "-i", str(gameplay_path),
    ]
    sfx_inputs: List[Tuple[int, float, float]] = []
    next_idx = 2
    for cue in plan.audio.sfx:
        if 0.0 <= cue.t < total_dur:
            wav_path = ensure_sfx_wav(cue.id)
            input_args += ["-i", str(wav_path)]
            sfx_inputs.append((next_idx, cue.t, cue.gain_db))
            next_idx += 1

    audio_fg = ";".join(
        build_audio_filtergraph(
            plan=plan,
            preset=preset,
            sync=sync,
            cam_seek=cam_seek,
            game_seek=game_seek,
            cam_input_idx=0,
            game_input_idx=1,
            sfx_inputs=sfx_inputs,
            clean_game_audio_stream=clean_game_audio_stream,
            measure_only=True,
        )
    )
    cmd = [
        resolve_binary("ffmpeg"),
        "-hide_banner",
        "-nostdin",
        *input_args,
        "-filter_complex",
        audio_fg,
        "-map",
        "[a_out]",
        "-t",
        f"{total_dur:.3f}",
        "-f",
        "null",
        "-",
    ]
    try:
        res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25.0)
        if res.returncode != 0:
            return None
        matches = re.findall(r"\{\s*\"input_i\"\s*:.*?\}", res.stderr, flags=re.DOTALL)
        if not matches:
            return None
        parsed = json.loads(matches[-1])
        input_i = str(parsed.get("input_i", ""))
        if not input_i or "inf" in input_i.lower() or float(input_i) < -65.0:
            return None
        return {
            "input_i": input_i,
            "input_tp": str(parsed["input_tp"]),
            "input_lra": str(parsed["input_lra"]),
            "input_thresh": str(parsed["input_thresh"]),
        }
    except Exception:
        return None


def _preload_bgra_emoji(emoji_id: str, target_px: int) -> np.ndarray:
    png_path = ensure_emoji_png(emoji_id, size=128)
    with Image.open(png_path) as im:
        rgba = im.convert("RGBA")
        if rgba.size != (target_px, target_px):
            rgba = rgba.resize((target_px, target_px), resample=Image.Resampling.LANCZOS)
        arr = np.array(rgba, dtype=np.uint8)
    bgra = arr.copy()
    bgra[:, :, 0] = arr[:, :, 2]
    bgra[:, :, 2] = arr[:, :, 0]
    return bgra


def _blend_bgra_inplace(canvas: np.ndarray, icon_bgra: np.ndarray, x: int, y: int) -> None:
    ih, iw = icon_bgra.shape[:2]
    ch, cw = canvas.shape[:2]
    x0, y0 = max(0, x), max(0, y)
    x1, y1 = min(cw, x + iw), min(ch, y + ih)
    if x1 <= x0 or y1 <= y0:
        return
    sub_icon = icon_bgra[y0 - y : y1 - y, x0 - x : x1 - x]
    alpha = sub_icon[:, :, 3:4].astype(np.float32) * (1.0 / 255.0)
    roi = canvas[y0:y1, x0:x1]
    blended = roi.astype(np.float32) * (1.0 - alpha) + sub_icon[:, :, :3].astype(np.float32) * alpha
    np.copyto(roi, blended.astype(np.uint8))


def _drain_stream(stream, collector: List[str]) -> None:
    if stream is None:
        return
    try:
        for raw in stream:
            line = (
                raw.decode("utf-8", errors="replace").rstrip()
                if isinstance(raw, (bytes, bytearray))
                else str(raw).rstrip()
            )
            collector.append(line)
            if len(collector) > 40:
                collector.pop(0)
    except Exception:
        pass


class _SequentialVideoSampler:
    """In-process C++ OpenCV decoder with zero-copy `grab()` stepping across jump cuts and FPS decimation."""

    def __init__(self, path: Path, initial_sec: float) -> None:
        self.cap = cv2.VideoCapture(str(path))
        if hasattr(cv2, "CAP_PROP_HW_ACCELERATION") and hasattr(cv2, "VIDEO_ACCELERATION_ANY"):
            try:
                self.cap.set(cv2.CAP_PROP_HW_ACCELERATION, float(cv2.VIDEO_ACCELERATION_ANY))
            except Exception:
                pass
        self.src_fps = float(self.cap.get(cv2.CAP_PROP_FPS) or 30.0)
        self.frame_dt = 1.0 / max(1.0, self.src_fps)
        self.w = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)) or 1280
        self.h = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) or 720
        self.last_frame = np.zeros((self.h, self.w, 3), dtype=np.uint8)
        self.cur_sec = 0.0

        start_s = max(0.0, initial_sec)
        if start_s > 0.05:
            self.cap.set(cv2.CAP_PROP_POS_MSEC, start_s * 1000.0)
        ok, frm = self.cap.read()
        if ok and frm is not None:
            self.last_frame = frm
            pos_ms = self.cap.get(cv2.CAP_PROP_POS_MSEC)
            self.cur_sec = (pos_ms / 1000.0) if pos_ms > 0 else start_s

    def frame_at(self, target_sec: float) -> np.ndarray:
        t = max(0.0, target_sec)
        gap = t - self.cur_sec
        if gap <= self.frame_dt * 0.55:
            return self.last_frame

        if gap > 8.0:
            self.cap.set(cv2.CAP_PROP_POS_MSEC, t * 1000.0)
            ok, frm = self.cap.read()
            if ok and frm is not None:
                self.last_frame = frm
                pos_ms = self.cap.get(cv2.CAP_PROP_POS_MSEC)
                self.cur_sec = (pos_ms / 1000.0) if pos_ms > 0 else t
            return self.last_frame

        grabbed_any = False
        while self.cur_sec + self.frame_dt * 0.55 < t:
            if not self.cap.grab():
                break
            self.cur_sec += self.frame_dt
            grabbed_any = True

        if grabbed_any:
            ok, frm = self.cap.retrieve()
            if ok and frm is not None:
                self.last_frame = frm
        return self.last_frame

    def close(self) -> None:
        self.cap.release()


def render_fast_affine_sync(
    plan: EditPlan,
    preset: StylePreset,
    gameplay_path: Path,
    camera_path: Path,
    sync: SyncResult,
    ass_path: Path,
    fonts_dir: Optional[Path],
    output_mp4: Path,
    encoder_flags: Sequence[str],
    quality: RenderQuality = "final",
    clean_game_audio_stream: Optional[int] = None,
    loudnorm_stats: Optional[Dict[str, str]] = None,
    timeout_sec: float = 180.0,
    emit_progress: Optional[Callable[[float], None]] = None,
) -> None:
    """Decode in-process via C++ `cv2.VideoCapture`, composite via `cv2.warpAffine`, and stream `yuv420p` into NVENC/x264."""
    if quality == "draft":
        render_w, render_h = 540, 960
        fps = min(30, plan.output.fps)
    else:
        render_w, render_h = plan.output.w, plan.output.h
        fps = min(preset.format.max_fps, plan.output.fps)

    scale_ratio = render_w / float(preset.format.width)
    ranges = plan.source.ranges
    total_dur = plan.total_duration()
    total_frames = max(1, int(round(total_dur * fps)))

    min_master_s, max_master_e = ranges[0][0], ranges[-1][1]
    game_seek = max(0.0, min_master_s - 0.25)
    game_read_dur = (max_master_e - game_seek) + 0.75

    min_cam_s, max_cam_e = sync.camera_time(min_master_s), sync.camera_time(max_master_e)
    cam_seek = max(0.0, min_cam_s - 0.35)
    cam_read_dur = max(1.0, max_cam_e - cam_seek + 1.0)

    ffmpeg_bin = resolve_binary("ffmpeg")

    # Single FFmpeg subprocess: receives raw `yuv420p` frames from pipe:0, burns static-res libass, mixes audio, encodes H.264
    enc_inputs: List[str] = [
        "-f", "rawvideo", "-pix_fmt", "yuv420p", "-s", f"{render_w}x{render_h}", "-r", str(fps), "-i", "pipe:0",
        "-vn", "-ss", f"{cam_seek:.3f}", "-t", f"{cam_read_dur:.3f}", "-i", str(camera_path),
        "-vn", "-ss", f"{game_seek:.3f}", "-t", f"{game_read_dur:.3f}", "-i", str(gameplay_path),
    ]
    sfx_inputs: List[Tuple[int, float, float]] = []
    next_inp = 3
    for cue in plan.audio.sfx:
        if 0.0 <= cue.t < total_dur:
            wav_path = ensure_sfx_wav(cue.id)
            enc_inputs += ["-i", str(wav_path)]
            sfx_inputs.append((next_inp, cue.t, cue.gain_db))
            next_inp += 1

    sub_filter = f"subtitles={quote_filter_path(ass_path)}"
    if fonts_dir is not None:
        sub_filter += f":fontsdir={quote_filter_path(fonts_dir)}"

    enc_fg_parts = [
        f"[0:v]{sub_filter},format=yuv420p[v_out]",
        *build_audio_filtergraph(
            plan=plan,
            preset=preset,
            sync=sync,
            cam_seek=cam_seek,
            game_seek=game_seek,
            cam_input_idx=1,
            game_input_idx=2,
            sfx_inputs=sfx_inputs,
            clean_game_audio_stream=clean_game_audio_stream,
            loudnorm_stats=loudnorm_stats,
            measure_only=False,
        ),
    ]
    enc_cmd = [
        ffmpeg_bin, "-hide_banner", "-loglevel", "error", "-y",
        *enc_inputs,
        "-filter_complex", ";".join(enc_fg_parts),
        "-map", "[v_out]", "-map", "[a_out]",
        "-t", f"{total_dur:.3f}",
        "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart",
        *encoder_flags,
        str(output_mp4),
    ]

    # Preload emoji overlays
    em_px = _even(max(36, preset.emojis.size_px * scale_ratio))
    emoji_cues: List[Tuple[float, float, np.ndarray]] = []
    icon_cache: Dict[str, np.ndarray] = {}
    for grp in plan.captions.groups:
        if grp.emoji and grp.words:
            eid = grp.emoji.id
            if eid not in icon_cache:
                icon_cache[eid] = _preload_bgra_emoji(eid, em_px)
            es = max(0.0, grp.emoji.at)
            ee = min(total_dur, max(es + 0.35, grp.words[-1].e))
            emoji_cues.append((es, ee, icon_cache[eid]))

    base_cam_ratio = preset.layout.camera_ratio
    for ev in plan.layout:
        if ev.kind == "split" and ev.camera_ratio is not None:
            base_cam_ratio = ev.camera_ratio
            break
    cam_panel_h = _even(render_h * base_cam_ratio)
    game_panel_h = render_h - cam_panel_h
    caption_ratio = plan.captions.vertical_ratio if getattr(plan.captions, "vertical_ratio", None) is not None else preset.captions.gameplay_top_third_ratio
    caption_y = cam_panel_h + int(round(game_panel_h * caption_ratio))
    base_em_x = (render_w - em_px) // 2
    base_em_y = max(cam_panel_h + 8, caption_y - em_px - int(round(28 * scale_ratio)))

    full_events = [
        (ev.t, ev.until or ev.t + 2.0)
        for ev in plan.layout
        if ev.kind == "camera_full" and (ev.until or ev.t + 2.0) > ev.t
    ]

    cam_sampler = _SequentialVideoSampler(camera_path, max(0.0, min_cam_s))
    game_sampler = _SequentialVideoSampler(gameplay_path, max(0.0, min_master_s))
    cam_w, cam_h_src = cam_sampler.w, cam_sampler.h
    game_w, game_h_src = game_sampler.w, game_sampler.h

    yuv_h = (render_h * 3) // 2
    yuv_bytes = (render_w * render_h * 3) // 2
    enc_proc = subprocess.Popen(
        enc_cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        bufsize=yuv_bytes * 4,
    )

    enc_err: List[str] = []
    t_ee = threading.Thread(target=_drain_stream, args=(enc_proc.stderr, enc_err), daemon=True)
    t_ee.start()

    # Pre-allocated YUV420p ring buffer pool: eliminates ~5 GB of transient heap allocations per clip
    pool_size = 10
    free_buffers: "queue.Queue[np.ndarray]" = queue.Queue(maxsize=pool_size)
    for _ in range(pool_size):
        free_buffers.put_nowait(np.empty((yuv_h, render_w), dtype=np.uint8))

    frame_queue: "queue.Queue[Optional[np.ndarray]]" = queue.Queue(maxsize=pool_size)
    writer_exc: List[BaseException] = []

    def _stdin_writer() -> None:
        assert enc_proc.stdin is not None
        try:
            while True:
                item = frame_queue.get()
                if item is None:
                    break
                enc_proc.stdin.write(memoryview(item))
                try:
                    free_buffers.put_nowait(item)
                except queue.Full:
                    pass
        except BaseException as exc:
            writer_exc.append(exc)
        finally:
            try:
                if enc_proc.stdin is not None:
                    enc_proc.stdin.close()
            except Exception:
                pass

    t_writer = threading.Thread(target=_stdin_writer, daemon=True)
    t_writer.start()

    canvas = np.zeros((render_h, render_w, 3), dtype=np.uint8)

    try:
        for f_idx in range(total_frames):
            if writer_exc:
                raise writer_exc[0]

            t = f_idx / float(fps)
            _, master_t = plan.clip_to_master_time(t)
            cam_t = max(0.0, sync.camera_time(master_t))

            cam_frame = cam_sampler.frame_at(cam_t)
            game_frame = game_sampler.frame_at(master_t)

            cx, cy, zoom = eval_crop_keyframes(plan.camera_crop, t, 0.5, 0.45, 1.0)
            is_full = any(fs <= t <= fe for fs, fe in full_events)
            if is_full:
                m_full = compute_cover_affine_matrix(cam_w, cam_h_src, render_w, render_h, cx, cy, zoom, anchor_y=0.44)
                cv2.warpAffine(
                    cam_frame,
                    m_full,
                    (render_w, render_h),
                    dst=canvas,
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REPLICATE,
                )
            else:
                m_cam = compute_cover_affine_matrix(cam_w, cam_h_src, render_w, cam_panel_h, cx, cy, zoom, anchor_y=0.44)
                cv2.warpAffine(
                    cam_frame,
                    m_cam,
                    (render_w, cam_panel_h),
                    dst=canvas[:cam_panel_h, :],
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REPLICATE,
                )
                gcx, gcy, gzoom = eval_crop_keyframes(plan.gameplay_crop or (), t, 0.5, 0.5, 1.0)
                m_game = compute_cover_affine_matrix(game_w, game_h_src, render_w, game_panel_h, gcx, gcy, gzoom, anchor_y=0.50)
                cv2.warpAffine(
                    game_frame,
                    m_game,
                    (render_w, game_panel_h),
                    dst=canvas[cam_panel_h:, :],
                    flags=cv2.INTER_LINEAR,
                    borderMode=cv2.BORDER_REPLICATE,
                )

            for es, ee, icon_bgra in emoji_cues:
                if es <= t <= ee:
                    dt_em = t - es
                    if dt_em < 0.12:
                        pop_s = 0.80 + 0.35 * math.sin(math.pi * (dt_em / 0.12))
                        cur_px = max(16, int(round(em_px * pop_s)))
                        scaled_icon = cv2.resize(icon_bgra, (cur_px, cur_px), interpolation=cv2.INTER_LINEAR)
                        ex = (render_w - cur_px) // 2
                        ey = base_em_y - (cur_px - em_px) // 2
                        _blend_bgra_inplace(canvas, scaled_icon, ex, ey)
                    else:
                        _blend_bgra_inplace(canvas, icon_bgra, base_em_x, base_em_y)

            try:
                yuv_buf = free_buffers.get(timeout=0.5)
            except queue.Empty:
                yuv_buf = np.empty((yuv_h, render_w), dtype=np.uint8)
            cv2.cvtColor(canvas, cv2.COLOR_BGR2YUV_I420, dst=yuv_buf)
            frame_queue.put(yuv_buf)

            if emit_progress and (f_idx % 15 == 0):
                emit_progress(min(0.98, f_idx / float(total_frames)))

        frame_queue.put(None)
        t_writer.join(timeout=timeout_sec)
        if writer_exc:
            raise writer_exc[0]
        enc_proc.wait(timeout=timeout_sec)
    except (BrokenPipeError, OSError) as exc:
        try:
            enc_proc.wait(timeout=5.0)
        except Exception:
            enc_proc.kill()
        t_ee.join(timeout=1.5)
        tail = "\n".join(enc_err[-18:])
        raise FfmpegError(f"FFmpeg encoder falló durante fast_compositor:\n{tail}") from exc
    except subprocess.TimeoutExpired as exc:
        enc_proc.kill()
        raise FfmpegError(f"Timeout de renderizado ({timeout_sec:.0f}s) excedido.") from exc
    finally:
        cam_sampler.close()
        game_sampler.close()
        try:
            frame_queue.put_nowait(None)
        except Exception:
            pass
        if enc_proc.poll() is None:
            try:
                enc_proc.kill()
            except Exception:
                pass
        try:
            enc_proc.wait(timeout=2.0)
        except Exception:
            pass
        t_writer.join(timeout=2.0)
        t_ee.join(timeout=1.0)

    if enc_proc.returncode != 0:
        tail = "\n".join(enc_err[-18:])
        raise FfmpegError(f"FFmpeg render falló ({enc_proc.returncode}):\n{tail}")
