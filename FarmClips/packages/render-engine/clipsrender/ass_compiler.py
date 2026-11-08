"""Compiles EditPlan v2 captions and title overlays into animated libass (.ass) script."""

from __future__ import annotations

from typing import List

from clipseditplan import EditPlan
from clipsstyles import StylePreset, hex_to_ass_bgr


def ass_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    total_cs = int(round(sec * 100))
    h, rem = divmod(total_cs, 360000)
    m, rem = divmod(rem, 6000)
    s, cs = divmod(rem, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def escape_ass(text: str) -> str:
    return text.replace("\\", "").replace("{", "(").replace("}", ")").replace("\n", " ").strip()


def balance_title_lines(title: str, max_chars_per_line: int = 18, max_lines: int = 2) -> str:
    words = title.split()
    if max_lines <= 1 or len(title) <= max_chars_per_line or len(words) < 2:
        return title
    best_idx = 1
    best_diff = len(title) + 1
    for i in range(1, len(words)):
        diff = abs(len(" ".join(words[:i])) - len(" ".join(words[i:])))
        if diff < best_diff:
            best_diff = diff
            best_idx = i
    return " ".join(words[:best_idx]) + r"\N" + " ".join(words[best_idx:])


def compile_ass(plan: EditPlan, preset: StylePreset, render_w: int, render_h: int) -> str:
    """Compile title and Hormozi animated captions (`\\t`, `\\fscx`, `\\fscy`, `\\1c`) for target resolution."""
    scale = render_w / float(preset.format.width)

    t_spec = preset.title
    c_spec = preset.captions

    title_fs = max(24, int(round(t_spec.font_size_px * scale)))
    title_out = max(2, int(round(t_spec.outline_px * scale)))
    cap_fs = max(26, int(round(c_spec.font_size_px * scale)))
    emph_fs = max(28, int(round(cap_fs * (c_spec.emphasis_word.scale_pct / 100.0))))
    cap_out = max(2, int(round(c_spec.outline_px * scale)))
    cap_shd = max(1, int(round(c_spec.shadow_px * scale)))

    title_primary = hex_to_ass_bgr(t_spec.color_hex)
    title_outline = hex_to_ass_bgr(t_spec.outline_color_hex)

    cap_white = hex_to_ass_bgr(c_spec.color_hex)
    cap_outline = hex_to_ass_bgr(c_spec.outline_color_hex)
    active_bgr = hex_to_ass_bgr(c_spec.active_word.color_hex)      # #FFD400
    emph_bgr = hex_to_ass_bgr(c_spec.emphasis_word.color_hex)      # #39FF14

    base_cam_ratio = preset.layout.camera_ratio
    for ev in plan.layout:
        if ev.kind == "split" and ev.camera_ratio is not None:
            base_cam_ratio = ev.camera_ratio
            break

    seam_y = int(round(render_h * base_cam_ratio))
    game_h = render_h - seam_y
    caption_ratio = plan.captions.vertical_ratio if getattr(plan.captions, "vertical_ratio", None) is not None else c_spec.gameplay_top_third_ratio
    caption_y = seam_y + int(round(game_h * caption_ratio))
    center_x = render_w // 2

    header = f"""[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
YCbCr Matrix: TV.709
PlayResX: {render_w}
PlayResY: {render_h}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Title,{t_spec.font_family},{title_fs},{title_primary},{title_primary},{title_outline},&H00000000,-1,0,0,0,100,100,0,0,1,{title_out},0,5,{int(40*scale)},{int(40*scale)},0,1
Style: Caption,{c_spec.font_family},{cap_fs},{cap_white},{cap_white},{cap_outline},&H78000000,-1,0,0,0,100,100,0,0,1,{cap_out},{cap_shd},5,{int(50*scale)},{int(50*scale)},0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: List[str] = []
    clip_dur = plan.total_duration()

    # 1. Overlays (Title on seam for first 3s)
    for ov in plan.overlays:
        if ov.kind == "title" and ov.text.strip() and ov.end > ov.start:
            s_t = max(0.0, ov.start)
            e_t = min(clip_dur, ov.end)
            if e_t > s_t:
                formatted = balance_title_lines(escape_ass(ov.text), t_spec.max_chars_per_line, t_spec.max_lines)
                events.append(
                    f"Dialogue: 3,{ass_time(s_t)},{ass_time(e_t)},Title,,0,0,0,,"
                    f"{{\\an5\\pos({center_x},{seam_y})\\fad(120,200)}}{formatted}"
                )

    # 2. Hormozi animated captions
    pop_pct = c_spec.active_word.pop_scale_pct
    pop_ms = max(40, c_spec.active_word.pop_duration_ms)
    half_pop = pop_ms // 2

    groups = plan.captions.groups
    for gi, group in enumerate(groups):
        if not group.words:
            continue
        next_group_start = groups[gi + 1].words[0].s if (gi + 1 < len(groups) and groups[gi + 1].words) else None

        for wi, active_w in enumerate(group.words):
            a = max(0.0, active_w.s)
            if wi + 1 < len(group.words):
                b = group.words[wi + 1].s
            else:
                b = active_w.e
                if next_group_start is not None and 0.0 < (next_group_start - b) < 0.22:
                    b = next_group_start
            b = min(clip_dur, max(a + 0.06, b))
            if b <= a:
                continue

            # Pop animation 100 -> 115 -> 100% in 120ms using \fscx \fscy \t
            anim_prefix = (
                f"\\an5\\pos({center_x},{caption_y})"
                f"\\fscx100\\fscy100"
                f"\\t(0,{half_pop},\\fscx{pop_pct}\\fscy{pop_pct})"
                f"\\t({half_pop},{pop_ms},\\fscx100\\fscy100)"
            )

            tokens: List[str] = []
            for other in group.words:
                txt = escape_ass(other.w.upper() if c_spec.uppercase else other.w)
                is_active = other is active_w
                is_emph = bool(other.emphasis)

                if is_active and is_emph:
                    tokens.append(f"{{\\1c{emph_bgr}\\fs{emph_fs}}}{txt}{{\\1c{cap_white}\\fs{cap_fs}}}")
                elif is_active:
                    tokens.append(f"{{\\1c{active_bgr}}}{txt}{{\\1c{cap_white}}}")
                elif is_emph:
                    tokens.append(f"{{\\1c{emph_bgr}\\fs{emph_fs}}}{txt}{{\\1c{cap_white}\\fs{cap_fs}}}")
                else:
                    tokens.append(txt)

            events.append(
                f"Dialogue: 2,{ass_time(a)},{ass_time(b)},Caption,,0,0,0,,{{{anim_prefix}}}{' '.join(tokens)}"
            )

    return header + "\n".join(events) + "\n"
