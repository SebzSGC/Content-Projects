"""Multimedia generation (local procedural high-res artwork, synthetic video, stock API) and thumbnails."""

from __future__ import annotations

import hashlib
import math
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from vidforge.infra.paths import get_ffmpeg_path
from vidforge.infra.procs import run_hidden


PALETTES = [
    ((15, 23, 42), (56, 189, 248), (129, 140, 248)),
    ((24, 24, 27), (245, 158, 11), (239, 68, 68)),
    ((6, 78, 59), (52, 211, 153), (16, 185, 129)),
    ((49, 16, 66), (192, 132, 252), (244, 114, 182)),
    ((12, 74, 110), (56, 189, 248), (34, 211, 238)),
]


def create_thumbnail(source_path: Path, thumb_path: Path, width: int = 384, height: int = 216) -> Path:
    thumb_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = source_path.suffix.lower()
    if suffix in (".mp4", ".webm", ".mov", ".mkv"):
        ff = get_ffmpeg_path()
        res = run_hidden(
            [
                ff,
                "-y",
                "-ss",
                "0.2",
                "-i",
                str(source_path),
                "-frames:v",
                "1",
                "-vf",
                f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}",
                str(thumb_path),
            ]
        )
        if res.returncode == 0 and thumb_path.exists():
            return thumb_path

    try:
        with Image.open(source_path) as im:
            im_rgb = im.convert("RGB")
            im_rgb.thumbnail((width, height))
            canvas = Image.new("RGB", (width, height), (15, 23, 42))
            ox = (width - im_rgb.width) // 2
            oy = (height - im_rgb.height) // 2
            canvas.paste(im_rgb, (ox, oy))
            canvas.save(thumb_path, "JPEG", quality=85)
            return thumb_path
    except Exception:
        canvas = Image.new("RGB", (width, height), (30, 41, 59))
        canvas.save(thumb_path, "JPEG", quality=80)
        return thumb_path


import re
import urllib.parse
import urllib.request

from vidforge.infra.secrets import secret_store


def _generate_procedural_image(
    prompt: str,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    tags: list[str] | None = None,
    beat_index: int = 0,
) -> Path:
    """Deterministic, high-resolution procedural scene card (used for offline fallback)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(f"{prompt}:{beat_index}".encode("utf-8")).digest()
    bg_col, acc1, acc2 = PALETTES[digest[0] % len(PALETTES)]

    img = Image.new("RGB", (width, height), bg_col)
    draw = ImageDraw.Draw(img)

    cx = int(width * (0.35 + (digest[1] / 255.0) * 0.30))
    cy = int(height * (0.35 + (digest[2] / 255.0) * 0.30))
    for r in range(720, 80, -80):
        ratio = r / 720.0
        col = (
            int(bg_col[0] * ratio + acc1[0] * (1 - ratio)),
            int(bg_col[1] * ratio + acc1[1] * (1 - ratio)),
            int(bg_col[2] * ratio + acc1[2] * (1 - ratio)),
        )
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], outline=col, width=6)

    for x in range(0, width, 160):
        draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 18), width=1)
    for y in range(0, height, 160):
        draw.line([(0, y), (width, y)], fill=(255, 255, 255, 18), width=1)

    pad = 96
    draw.rounded_rectangle(
        [pad, height - 340, width - pad, height - pad],
        radius=24,
        fill=(15, 23, 42),
        outline=acc2,
        width=4,
    )

    try:
        font_title = ImageFont.truetype("C:\\Windows\\Fonts\\segoeuib.ttf", 44)
        font_body = ImageFont.truetype("C:\\Windows\\Fonts\\segoeui.ttf", 32)
    except Exception:
        font_title = ImageFont.load_default()
        font_body = ImageFont.load_default()

    tag_str = " ".join(tags or [])
    header_txt = f"ESCENA #{beat_index + 1:02d}  {tag_str}".strip()
    draw.text((pad + 42, height - 305), header_txt, fill=acc1, font=font_title)

    short_prompt = (prompt[:110] + "…") if len(prompt) > 110 else prompt
    draw.text((pad + 42, height - 230), short_prompt, fill=(241, 245, 249), font=font_body)

    img.save(output_path, "PNG")
    return output_path


def generate_visual_image(
    prompt: str,
    output_path: Path,
    width: int = 1920,
    height: int = 1080,
    tags: list[str] | None = None,
    beat_index: int = 0,
) -> Path:
    """Generates a high-quality visual image using AI (Pollinations Flux / fal / openai), falling back to procedural."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    clean_prompt = re.sub(r"[@#]", "", prompt).strip()
    if not clean_prompt:
        clean_prompt = "cinematic scene, high quality, 4k"

    seed = int(hashlib.sha256(f"{clean_prompt}:{beat_index}".encode("utf-8")).hexdigest()[:8], 16) % 100000

    # 1. Try Pollinations AI (Zero-config Flux / SDXL, free)
    try:
        encoded = urllib.parse.quote(clean_prompt)
        url = f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&model=flux&nologo=true&seed={seed}"
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) VidForge/1.0"},
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            data = resp.read()
            if len(data) > 1024:
                import io

                with Image.open(io.BytesIO(data)) as im:
                    im_rgb = im.convert("RGB")
                    if im_rgb.size != (width, height):
                        im_rgb = im_rgb.resize((width, height), Image.Resampling.LANCZOS)
                    im_rgb.save(output_path, "PNG")
                    return output_path
    except Exception:
        pass

    # 2. Offline fallback: Procedural graphic card
    return _generate_procedural_image(prompt, output_path, width, height, tags, beat_index)


def generate_visual_video_clip(
    prompt: str,
    output_path: Path,
    duration_s: float = 4.0,
    width: int = 1920,
    height: int = 1080,
    beat_index: int = 0,
) -> Path:
    """Generates a smooth animated MP4 video clip locally from a high-res scene frame."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    still_path = output_path.with_suffix(".still.png")
    generate_visual_image(prompt, still_path, width=width, height=height, beat_index=beat_index)

    ff = get_ffmpeg_path()
    frames = max(30, int(round(duration_s * 30)))
    vf = (
        f"scale=2560:1440,zoompan=z='1.0+0.08*on/{frames}':"
        f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d={frames}:s={width}x{height}:fps=30,format=yuv420p"
    )
    res = run_hidden(
        [
            ff,
            "-y",
            "-loop",
            "1",
            "-i",
            str(still_path),
            "-vf",
            vf,
            "-t",
            f"{duration_s:.2f}",
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        timeout=60.0,
    )
    still_path.unlink(missing_ok=True)
    if res.returncode != 0:
        raise RuntimeError(f"Video generation failed: {res.stderr[-300:]}")
    return output_path
