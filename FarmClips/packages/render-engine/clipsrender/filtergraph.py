"""Compiles EditPlan v2 into an FFmpeg filtergraph + argument list (draft 540p & final 1080p)."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Literal, Optional, Sequence, Tuple

from clipscore.domain import SyncResult
from clipseditplan import CropKeyframe, EditPlan
from clipsstyles import StylePreset, ensure_emoji_png, ensure_sfx_wav

RenderQuality = Literal["draft", "final"]


def _even(v: float) -> int:
    i = max(2, int(round(v)))
    return i - (i % 2)


def quote_filter_path(path: str | Path) -> str:
    p = str(path).replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    return f"'{p}'"


def _ease_expr(u_expr: str, ease: Optional[str]) -> str:
    if ease == "outBack":
        return f"(1+2.70158*pow(({u_expr})-1,3)+1.70158*pow(({u_expr})-1,2))"
    if ease == "inOutSine":
        return f"((1-cos(PI*({u_expr})))/2)"
    if ease == "outCubic":
        return f"(1-pow(1-({u_expr}),3))"
    return f"({u_expr})"


def build_keyframe_expr(
    keyframes: Sequence[CropKeyframe],
    attr: str,
    min_val: float,
    max_val: float,
) -> str:
    """Build piecewise FFmpeg `t` expression interpolating `cx`, `cy`, or `zoom` across keyframes."""
    if not keyframes:
        default = 1.0 if attr == "zoom" else 0.5
        return f"{default:.4f}"
    if len(keyframes) == 1:
        val = float(getattr(keyframes[0], attr))
        return f"{max(min_val, min(max_val, val)):.4f}"

    # Nested `if(lt(t, t_next), seg_expr, ...)`
    last_val = float(getattr(keyframes[-1], attr))
    expr = f"{max(min_val, min(max_val, last_val)):.4f}"
    for i in range(len(keyframes) - 2, -1, -1):
        kf_a = keyframes[i]
        kf_b = keyframes[i + 1]
        va = float(getattr(kf_a, attr))
        vb = float(getattr(kf_b, attr))
        dt = max(0.001, kf_b.t - kf_a.t)
        if abs(vb - va) < 1e-4:
            seg = f"{va:.4f}"
        else:
            u = f"clip((t-{kf_a.t:.3f})/{dt:.3f},0,1)"
            eu = _ease_expr(u, kf_b.ease)
            seg = f"({va:.4f}+({vb - va:.4f})*{eu})"
        if i == 0:
            expr = f"if(lt(t,{kf_b.t:.3f}),{seg},{expr})"
        else:
            expr = f"if(lt(t,{kf_b.t:.3f}),{seg},{expr})"
    return f"clip({expr},{min_val:.4f},{max_val:.4f})"


@dataclass
class CompiledRenderCommand:
    input_args: List[str]
    filtergraph: str
    output_args: List[str]
    render_w: int
    render_h: int
    fps: int
    duration: float


def compile_ffmpeg_plan(
    plan: EditPlan,
    preset: StylePreset,
    gameplay_path: str | Path,
    camera_path: str | Path,
    sync: SyncResult,
    ass_path: Path,
    fonts_dir: Optional[Path] = None,
    quality: RenderQuality = "final",
    clean_game_audio_stream: Optional[int] = None,
    loudnorm_stats: Optional[dict] = None,
) -> CompiledRenderCommand:
    """Compile declarative EditPlan v2 into inputs + FFmpeg filter_complex + output flags."""
    if quality == "draft":
        render_w, render_h = 540, 960
        fps = min(30, plan.output.fps)
    else:
        render_w, render_h = plan.output.w, plan.output.h
        fps = min(preset.format.max_fps, plan.output.fps)

    scale_ratio = render_w / float(preset.format.width)
    ranges = plan.source.ranges
    total_dur = plan.total_duration()

    min_master_s = ranges[0][0]
    max_master_e = ranges[-1][1]
    game_seek = max(0.0, min_master_s - 0.25)
    game_read_dur = (max_master_e - game_seek) + 0.75

    min_cam_s = sync.camera_time(min_master_s)
    max_cam_e = sync.camera_time(max_master_e)
    cam_seek = max(0.0, min_cam_s - 0.35)
    cam_lead_pad = max(0.0, -min_cam_s)
    cam_read_dur = max(1.0, max_cam_e - cam_seek + 1.0)

    input_args: List[str] = [
        "-ss", f"{cam_seek:.3f}", "-t", f"{cam_read_dur:.3f}", "-i", str(camera_path),
        "-ss", f"{game_seek:.3f}", "-t", f"{game_read_dur:.3f}", "-i", str(gameplay_path),
    ]

    # Collect emoji overlay inputs (input index >= 2)
    emoji_overlays: List[Tuple[int, float, float]] = []
    next_input_idx = 2
    groups = plan.captions.groups
    for gi, grp in enumerate(groups):
        if grp.emoji and grp.words:
            png_path = ensure_emoji_png(grp.emoji.id)
            input_args += ["-loop", "1", "-t", f"{total_dur + 0.5:.3f}", "-i", str(png_path)]
            em_start = max(0.0, grp.emoji.at)
            em_end = min(total_dur, max(em_start + 0.35, grp.words[-1].e))
            emoji_overlays.append((next_input_idx, em_start, em_end))
            next_input_idx += 1

    # Collect SFX inputs
    sfx_inputs: List[Tuple[int, float, float]] = []
    for cue in plan.audio.sfx:
        if 0.0 <= cue.t < total_dur:
            wav_path = ensure_sfx_wav(cue.id)
            input_args += ["-i", str(wav_path)]
            sfx_inputs.append((next_input_idx, cue.t, cue.gain_db))
            next_input_idx += 1

    fg: List[str] = []

    # 1. Trim & concat jump-cut ranges for Camera video ([cam_trim]), Gameplay video ([game_trim]), and Audio
    n_seg = len(ranges)
    cam_pre = f"fps={fps},setpts=(PTS-STARTPTS)/{sync.scale:.6f}"
    if cam_lead_pad > 0.005:
        cam_pre = f"tpad=start_duration={cam_lead_pad:.3f}:start_mode=clone," + cam_pre

    if n_seg == 1:
        a, b = ranges[0]
        ga, gb = max(0.0, a - game_seek), max(0.05, b - game_seek)
        ca = max(0.0, sync.camera_time(a) - cam_seek + cam_lead_pad)
        cb = max(ca + 0.05, ca + (b - a))
        fg.append(f"[0:v]{cam_pre},trim=start={ca:.3f}:end={cb:.3f},setpts=PTS-STARTPTS[cam_trim]")
        fg.append(f"[1:v]fps={fps},trim=start={ga:.3f}:end={gb:.3f},setpts=PTS-STARTPTS[game_trim]")
        if clean_game_audio_stream is not None:
            fg.append(f"[0:a:0]atrim=start={max(0.0, sync.camera_time(a) - cam_seek):.3f}:end={max(0.05, sync.camera_time(b) - cam_seek):.3f},asetpts=PTS-STARTPTS[mic_a]")
            fg.append(f"[1:a:{clean_game_audio_stream}]atrim=start={ga:.3f}:end={gb:.3f},asetpts=PTS-STARTPTS[game_a]")
        else:
            fg.append(f"[1:a:0]atrim=start={ga:.3f}:end={gb:.3f},asetpts=PTS-STARTPTS[mix_a]")
    else:
        fg.append(f"[0:v]{cam_pre},split={n_seg}" + "".join(f"[cv{i}]" for i in range(n_seg)))
        fg.append(f"[1:v]fps={fps},split={n_seg}" + "".join(f"[gv{i}]" for i in range(n_seg)))
        if clean_game_audio_stream is not None:
            fg.append(f"[0:a:0]asplit={n_seg}" + "".join(f"[ma{i}]" for i in range(n_seg)))
            fg.append(f"[1:a:{clean_game_audio_stream}]asplit={n_seg}" + "".join(f"[ga{i}]" for i in range(n_seg)))
        else:
            fg.append(f"[1:a:0]asplit={n_seg}" + "".join(f"[xa{i}]" for i in range(n_seg)))

        for i, (a, b) in enumerate(ranges):
            ga, gb = max(0.0, a - game_seek), max(0.05, b - game_seek)
            ca = max(0.0, sync.camera_time(a) - cam_seek + cam_lead_pad)
            cb = max(ca + 0.05, ca + (b - a))
            fg.append(f"[cv{i}]trim=start={ca:.3f}:end={cb:.3f},setpts=PTS-STARTPTS[cvs{i}]")
            fg.append(f"[gv{i}]trim=start={ga:.3f}:end={gb:.3f},setpts=PTS-STARTPTS[gvs{i}]")
            if clean_game_audio_stream is not None:
                mca = max(0.0, sync.camera_time(a) - cam_seek)
                mcb = max(mca + 0.05, sync.camera_time(b) - cam_seek)
                fg.append(f"[ma{i}]atrim=start={mca:.3f}:end={mcb:.3f},asetpts=PTS-STARTPTS[mas{i}]")
                fg.append(f"[ga{i}]atrim=start={ga:.3f}:end={gb:.3f},asetpts=PTS-STARTPTS[gas{i}]")
            else:
                fg.append(f"[xa{i}]atrim=start={ga:.3f}:end={gb:.3f},asetpts=PTS-STARTPTS[xas{i}]")

        fg.append("".join(f"[cvs{i}]" for i in range(n_seg)) + f"concat=n={n_seg}:v=1:a=0[cam_trim]")
        fg.append("".join(f"[gvs{i}]" for i in range(n_seg)) + f"concat=n={n_seg}:v=1:a=0[game_trim]")
        if clean_game_audio_stream is not None:
            fg.append("".join(f"[mas{i}]" for i in range(n_seg)) + f"concat=n={n_seg}:v=0:a=1[mic_a]")
            fg.append("".join(f"[gas{i}]" for i in range(n_seg)) + f"concat=n={n_seg}:v=0:a=1[game_a]")
        else:
            fg.append("".join(f"[xas{i}]" for i in range(n_seg)) + f"concat=n={n_seg}:v=0:a=1[mix_a]")

    # 2. Panel geometry & animated camera zoom/pan (`scale` eval=frame + fixed `crop` of time `t`)
    cam_ratio = preset.layout.camera_ratio
    for ev in plan.layout:
        if ev.kind == "split" and ev.camera_ratio is not None:
            cam_ratio = ev.camera_ratio
            break
    cam_h = _even(render_h * cam_ratio)
    game_h = render_h - cam_h

    z_expr = build_keyframe_expr(plan.camera_crop, "zoom", 1.0, 3.0)
    cx_expr = build_keyframe_expr(plan.camera_crop, "cx", 0.05, 0.95)
    cy_expr = build_keyframe_expr(plan.camera_crop, "cy", 0.05, 0.95)

    full_events = [ev for ev in plan.layout if ev.kind == "camera_full" and (ev.until or ev.t + 2.0) > ev.t]
    if full_events:
        fg.append("[cam_trim]split=2[cam_for_split][cam_for_full]")
        cam_split_in = "[cam_for_split]"
    else:
        cam_split_in = "[cam_trim]"

    # Normalize camera to exact split-panel cover box, then per-frame scale(eval=frame) + animated crop
    fg.append(
        f"{cam_split_in}scale={render_w}:{cam_h}:force_original_aspect_ratio=increase,"
        f"crop={render_w}:{cam_h},"
        f"scale=w='2*trunc(({render_w}*{z_expr})/2)':h='2*trunc(({cam_h}*{z_expr})/2)':eval=frame,"
        f"crop=w={render_w}:h={cam_h}:x='clip(iw*{cx_expr}-{render_w}/2,0,iw-{render_w})':y='clip(ih*{cy_expr}-{cam_h}*0.44,0,ih-{cam_h})',"
        f"setsar=1[cam_panel]"
    )

    # Gameplay panel (centered or centroid-focused)
    gp_cx = 0.5
    if plan.gameplay_crop:
        gp_cx = plan.gameplay_crop[0].cx
    fg.append(
        f"[game_trim]scale={render_w}:{game_h}:force_original_aspect_ratio=increase,"
        f"crop=w={render_w}:h={game_h}:x='clip((iw-{render_w})*{gp_cx:.3f},0,iw-{render_w})':y='(ih-{game_h})/2',"
        f"setsar=1[game_panel]"
    )

    fg.append("[cam_panel][game_panel]vstack=inputs=2[stacked]")
    current_v = "[stacked]"

    # Fullscreen camera reaction overrides (`camera_full` for 2s on top reactions)
    if full_events:
        enable_terms = "+".join(
            f"between(t,{ev.t:.3f},{(ev.until or ev.t + 2.0):.3f})" for ev in full_events
        )
        fg.append(
            f"[cam_for_full]scale={render_w}:{render_h}:force_original_aspect_ratio=increase,"
            f"crop={render_w}:{render_h},"
            f"scale=w='2*trunc(({render_w}*{z_expr})/2)':h='2*trunc(({render_h}*{z_expr})/2)':eval=frame,"
            f"crop=w={render_w}:h={render_h}:x='clip(iw*{cx_expr}-{render_w}/2,0,iw-{render_w})':y='clip(ih*{cy_expr}-{render_h}*0.44,0,ih-{render_h})',"
            f"setsar=1[cam_full_v]"
        )
        fg.append(f"{current_v}[cam_full_v]overlay=0:0:enable='{enable_terms}'[v_layout]")
        current_v = "[v_layout]"

    # 3. Color Emoji PNG overlays (libass does not render color bitmap/vector emojis reliably)
    if emoji_overlays:
        em_px = _even(max(36, preset.emojis.size_px * scale_ratio))
        caption_y = cam_h + int(round(game_h * preset.captions.gameplay_top_third_ratio))
        em_x = (render_w - em_px) // 2
        em_y = max(cam_h + 8, caption_y - em_px - int(round(28 * scale_ratio)))
        for idx_em, (inp_i, es, ee) in enumerate(emoji_overlays):
            fg.append(f"[{inp_i}:v]scale={em_px}:{em_px},format=rgba[em{idx_em}]")
            out_lbl = f"[vem{idx_em}]"
            fg.append(f"{current_v}[em{idx_em}]overlay={em_x}:{em_y}:enable='between(t,{es:.3f},{ee:.3f})'{out_lbl}")
            current_v = out_lbl

    # 4. Burn ASS subtitles & format yuv420p
    sub_filter = f"subtitles={quote_filter_path(ass_path)}"
    if fonts_dir is not None:
        sub_filter += f":fontsdir={quote_filter_path(fonts_dir)}"
    fg.append(f"{current_v}{sub_filter},format=yuv420p[v_out]")

    # 5. Audio mixing, sidechain ducking, SFX, and -14 LUFS loudness normalization
    mic_gain = plan.audio.mic_gain_db
    duck_db = plan.audio.duck_game_db
    if clean_game_audio_stream is not None:
        # Attenuate clean game track when streamer speaks using sidechaincompress
        ratio = max(2.0, min(12.0, abs(duck_db) * 0.7))
        fg.append(f"[mic_a]aresample=48000,highpass=f=75,volume={mic_gain:.1f}dB,asplit=2[mic_sc][mic_mix]")
        fg.append(f"[game_a]aresample=48000[game_rs]")
        fg.append(
            f"[game_rs][mic_sc]sidechaincompress=threshold=0.035:ratio={ratio:.1f}:attack=15:release=260[game_duck]"
        )
        fg.append("[mic_mix][game_duck]amix=inputs=2:duration=first:dropout_transition=0:normalize=0[base_a]")
    else:
        boost = mic_gain * 0.5
        fg.append(
            f"[mix_a]aresample=48000,highpass=f=70,equalizer=f=3000:t=q:w=1.2:g=2.5,volume={boost:.1f}dB[base_a]"
        )

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
    if loudnorm_stats and "input_i" in loudnorm_stats:
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

    output_args = [
        "-map", "[v_out]",
        "-map", "[a_out]",
        "-t", f"{total_dur:.3f}",
        "-c:a", "aac",
        "-b:a", "192k",
        "-movflags", "+faststart",
    ]
    return CompiledRenderCommand(
        input_args=input_args,
        filtergraph=";\n".join(fg),
        output_args=output_args,
        render_w=render_w,
        render_h=render_h,
        fps=fps,
        duration=total_dur,
    )
