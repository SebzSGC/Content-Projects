"""Declarative style presets (hormozi-gaming), fonts, color emoji PNGs, and SFX assets."""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np
from pydantic import BaseModel, Field

from .emoji_catalog import EMOJI_CATALOG, list_emoji_catalog, render_supersampled_emoji
from .keyterms import KEYTERMS_DIR, list_game_profiles, load_all_game_profiles, resolve_game_keyterms

PACKAGE_DIR = Path(__file__).resolve().parent
PRESETS_DIR = PACKAGE_DIR / "presets"
FONTS_DIR = PACKAGE_DIR / "fonts"
EMOJIS_DIR = PACKAGE_DIR / "emojis"
SFX_DIR = PACKAGE_DIR / "sfx"


class FormatSpec(BaseModel):
    width: int = 1080
    height: int = 1920
    max_fps: int = 60
    video_codec: str = "h264"
    audio_codec: str = "aac"
    audio_bitrate: str = "192k"
    target_lufs: float = -14.0


class DurationSpec(BaseModel):
    min_sec: float = 20.0
    max_sec: float = 60.0


class LayoutSpec(BaseModel):
    camera_ratio: float = 0.4
    gameplay_ratio: float = 0.6
    camera_full_sec: float = 2.0
    camera_full_max_reactions: int = 2


class TitleSpec(BaseModel):
    duration_sec: float = 3.0
    position: str = "seam"
    max_lines: int = 2
    font_family: str = "Montserrat ExtraBold"
    font_size_px: int = 74
    color_hex: str = "#FFFFFF"
    outline_color_hex: str = "#000000"
    outline_px: int = 7
    max_chars_per_line: int = 18


class ActiveWordSpec(BaseModel):
    color_hex: str = "#FFD400"
    pop_scale_pct: int = 115
    pop_duration_ms: int = 120


class EmphasisWordSpec(BaseModel):
    color_hex: str = "#39FF14"
    scale_pct: int = 110


class CaptionsSpec(BaseModel):
    preset: str = "hormozi"
    font_family: str = "Montserrat ExtraBold"
    uppercase: bool = True
    min_words: int = 1
    max_words: int = 3
    max_chars: int = 14
    pause_split_sec: float = 0.3
    font_size_px: int = 80
    color_hex: str = "#FFFFFF"
    outline_color_hex: str = "#000000"
    outline_px: int = 8
    shadow_px: int = 3
    gameplay_top_third_ratio: float = 0.22
    active_word: ActiveWordSpec = Field(default_factory=ActiveWordSpec)
    emphasis_word: EmphasisWordSpec = Field(default_factory=EmphasisWordSpec)


class EmojisSpec(BaseModel):
    max_interval_sec: float = 5.0
    only_on_emphasis: bool = True
    asset_set: str = "twemoji"
    size_px: int = 112


class ImpactZoomSpec(BaseModel):
    scale: float = 1.25
    in_ms: int = 150
    in_ease: str = "outBack"
    hold_sec: float = 0.8
    out_ms: int = 300
    out_ease: str = "inOutSine"
    min_interval_sec: float = 4.0


class SlowZoomSpec(BaseModel):
    start_scale: float = 1.0
    end_scale: float = 1.1
    min_setup_sec: float = 5.0
    ease: str = "inOutSine"


class CutsSpec(BaseModel):
    min_silence_sec: float = 0.7
    margin_sec: float = 0.15
    never_cut_laughter_or_scream: bool = True


class AudioPresetSpec(BaseModel):
    mic_gain_db: float = 2.0
    duck_game_db: float = -9.0


class StylePreset(BaseModel):
    id: str = "hormozi-gaming"
    version: str = "1.0.0"
    format: FormatSpec = Field(default_factory=FormatSpec)
    duration: DurationSpec = Field(default_factory=DurationSpec)
    layout: LayoutSpec = Field(default_factory=LayoutSpec)
    title: TitleSpec = Field(default_factory=TitleSpec)
    captions: CaptionsSpec = Field(default_factory=CaptionsSpec)
    emojis: EmojisSpec = Field(default_factory=EmojisSpec)
    impact_zoom: ImpactZoomSpec = Field(default_factory=ImpactZoomSpec)
    slow_zoom: SlowZoomSpec = Field(default_factory=SlowZoomSpec)
    cuts: CutsSpec = Field(default_factory=CutsSpec)
    audio: AudioPresetSpec = Field(default_factory=AudioPresetSpec)

    def content_hash(self) -> str:
        payload = json.dumps(self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def list_presets() -> List[str]:
    if not PRESETS_DIR.exists():
        return []
    return sorted(p.stem for p in PRESETS_DIR.glob("*.json"))


@lru_cache(maxsize=16)
def load_preset(preset_id: str = "hormozi-gaming", custom_dir: Optional[str] = None) -> StylePreset:
    search_dirs = [Path(custom_dir)] if custom_dir else []
    search_dirs.append(PRESETS_DIR)
    for d in search_dirs:
        candidate = d / f"{preset_id}.json"
        if candidate.is_file():
            raw = json.loads(candidate.read_text(encoding="utf-8"))
            return StylePreset.model_validate(raw)
    raise FileNotFoundError(f"No existe el preset de estilo '{preset_id}' en {PRESETS_DIR}")


def get_fonts_dir() -> Path:
    FONTS_DIR.mkdir(parents=True, exist_ok=True)
    return FONTS_DIR


def hex_to_ass_bgr(hex_color: str, alpha: int = 0) -> str:
    """Convert #RRGGBB into libass &HAABBGGRR& color string."""
    clean = hex_color.strip().lstrip("#")
    if len(clean) != 6:
        clean = "FFFFFF"
    r = int(clean[0:2], 16)
    g = int(clean[2:4], 16)
    b = int(clean[4:6], 16)
    return f"&H{alpha:02X}{b:02X}{g:02X}{r:02X}&"


def normalize_emoji_id(emoji_id_or_char: str) -> str:
    """Normalize either an emoji character ('😱') or hex code ('1f631', 'U+1F631') to lowercase hex."""
    val = emoji_id_or_char.strip()
    if not val:
        return "1f525"
    low = val.lower().replace("u+", "").replace("0x", "")
    if all(c in "0123456789abcdef-" for c in low) and len(low) >= 4:
        return low.split("-")[0]
    codepoints = [f"{ord(ch):x}" for ch in val if ord(ch) not in (0xFE0F, 0x200D)]
    return codepoints[0] if codepoints else "1f525"


def ensure_emoji_png(emoji_id: str, size: int = 128, cache_dir: Optional[Path] = None) -> Path:
    """Return path to a 2x-supersampled color RGBA PNG for the given emoji hex ID, generating it cleanly if absent."""
    norm = normalize_emoji_id(emoji_id)
    out_dir = cache_dir or EMOJIS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{norm}.png" if size == 128 else f"{norm}_{size}.png"
    target = out_dir / fname
    if target.is_file() and target.stat().st_size > 100:
        return target
    return render_supersampled_emoji(norm, target, size=size)


def ensure_sfx_wav(sfx_id: str = "boom", cache_dir: Optional[Path] = None) -> Path:
    """Return path to a clean synthetic CC0 SFX WAV (e.g. 'boom' bass impact) for audio.sfx."""
    import soundfile as sf

    safe_id = "".join(c for c in sfx_id.lower() if c.isalnum() or c in ("_", "-")) or "boom"
    out_dir = cache_dir or SFX_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    target = out_dir / f"{safe_id}.wav"
    if target.is_file() and target.stat().st_size > 200:
        return target

    sr = 48000
    dur = 0.55
    t = np.linspace(0.0, dur, int(sr * dur), endpoint=False, dtype=np.float32)
    # Sub-bass pitch drop 110Hz -> 38Hz + transient punch
    freq = 38.0 + 72.0 * np.exp(-t * 14.0)
    phase = 2.0 * math.pi * np.cumsum(freq) / sr
    env = np.exp(-t * 6.5)
    punch = np.sin(2.0 * math.pi * 220.0 * t) * np.exp(-t * 45.0) * 0.35
    wave = np.clip((np.sin(phase) * env * 0.75 + punch), -0.95, 0.95).astype(np.float32)
    sf.write(str(target), wave, sr, subtype="PCM_16")
    return target
