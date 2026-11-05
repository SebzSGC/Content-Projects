"""Runtime settings, read once from environment variables (see .env.example)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _opt(name: str) -> Optional[str]:
    raw = os.environ.get(name, "").strip()
    return raw or None


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    host: str
    port: int
    ffmpeg: str
    ffprobe: str
    use_nvenc: bool
    fonts_dir: Optional[Path]
    title_font: str
    caption_font: str
    # Analysis
    proxy_height: int
    proxy_fps: float
    use_demucs: bool
    demucs_model: str
    whisper_model: str
    whisper_device: str
    whisper_compute_type: str
    face_landmarker_model: Optional[Path]
    torch_device: str
    # Kick
    kick_analysis_height: int
    kick_render_height: int
    kick_cookies_file: Optional[Path]
    # LLM (any provider, see selection/providers.py)
    llm_provider: str
    llm_model: str  # empty → provider default
    llm_base_url: Optional[str]
    llm_api_key: Optional[str]  # empty → provider's own env var (ANTHROPIC_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY)
    llm_vision: bool  # send keyframes in the verification pass
    llm_effort: str
    verify_top_k: int
    # Clip shape
    min_clip_sec: float
    max_clip_sec: float

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = Path(os.environ.get("CLIPS_DATA_DIR", "./data")).expanduser().resolve()
        fonts = _opt("CLIPS_FONTS_DIR")
        landmarker = _opt("CLIPS_FACE_LANDMARKER_MODEL")
        cookies = _opt("CLIPS_KICK_COOKIES")
        return cls(
            data_dir=data_dir,
            host=os.environ.get("CLIPS_HOST", "127.0.0.1"),
            port=int(os.environ.get("CLIPS_PORT", "8790")),
            ffmpeg=os.environ.get("CLIPS_FFMPEG", "ffmpeg"),
            ffprobe=os.environ.get("CLIPS_FFPROBE", "ffprobe"),
            use_nvenc=_bool("CLIPS_NVENC", True),
            fonts_dir=Path(fonts).expanduser().resolve() if fonts else None,
            title_font=os.environ.get("CLIPS_TITLE_FONT", "Montserrat ExtraBold"),
            caption_font=os.environ.get("CLIPS_CAPTION_FONT", "Montserrat ExtraBold"),
            proxy_height=int(os.environ.get("CLIPS_PROXY_HEIGHT", "480")),
            proxy_fps=float(os.environ.get("CLIPS_PROXY_FPS", "10")),
            use_demucs=_bool("CLIPS_DEMUCS", True),
            demucs_model=os.environ.get("CLIPS_DEMUCS_MODEL", "htdemucs_ft"),
            whisper_model=os.environ.get("CLIPS_WHISPER_MODEL", "large-v3-turbo"),
            whisper_device=os.environ.get("CLIPS_WHISPER_DEVICE", "auto"),
            whisper_compute_type=os.environ.get("CLIPS_WHISPER_COMPUTE", "default"),
            face_landmarker_model=Path(landmarker).expanduser().resolve() if landmarker else None,
            torch_device=os.environ.get("CLIPS_TORCH_DEVICE", "cuda"),
            kick_analysis_height=int(os.environ.get("CLIPS_KICK_ANALYSIS_HEIGHT", "480")),
            kick_render_height=int(os.environ.get("CLIPS_KICK_RENDER_HEIGHT", "1080")),
            kick_cookies_file=Path(cookies).expanduser().resolve() if cookies else None,
            llm_provider=os.environ.get("CLIPS_LLM_PROVIDER", "anthropic").strip().lower(),
            llm_model=os.environ.get("CLIPS_LLM_MODEL", "").strip(),
            llm_base_url=_opt("CLIPS_LLM_BASE_URL"),
            llm_api_key=_opt("CLIPS_LLM_API_KEY"),
            llm_vision=_bool("CLIPS_LLM_VISION", True),
            llm_effort=os.environ.get("CLIPS_LLM_EFFORT", "high"),
            verify_top_k=int(os.environ.get("CLIPS_VERIFY_TOP_K", "10")),
            min_clip_sec=float(os.environ.get("CLIPS_MIN_SEC", "20")),
            max_clip_sec=float(os.environ.get("CLIPS_MAX_SEC", "90")),
        )


def load_dotenv(path: Path = Path(".env")) -> None:
    """Minimal .env loader (KEY=VALUE lines); real environment variables win."""
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip().strip('"').strip("'")
        if value:
            os.environ.setdefault(key.strip(), value)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    load_dotenv()
    return Settings.from_env()
