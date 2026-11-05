"""Kick VODs and clips through yt-dlp.

Kick has no public VOD API; yt-dlp follows the player's own playback endpoint
and needs ``curl_cffi`` installed for browser impersonation (Cloudflare).
Keep yt-dlp up to date: Kick changes break extractors regularly.

Two-step strategy for multi-hour VODs: download a low-res copy for analysis,
then fetch only the chosen ranges at full quality when rendering.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Callable, Dict, Optional

from ..config import get_settings

VOD_RE = re.compile(r"^https?://(?:www\.)?kick\.com/[\w-]+/videos/[\da-f]{8}-(?:[\da-f]{4}-){3}[\da-f]{12}", re.I)
CLIP_RE = re.compile(r"^https?://(?:www\.)?kick\.com/[\w-]+(?:/clips/|/?\?(?:[^#]+&)?clip=)clip_[\w-]+", re.I)

ProgressCb = Callable[[float, str], None]


def is_kick_url(url: str) -> bool:
    return bool(VOD_RE.match(url.strip()) or CLIP_RE.match(url.strip()))


def kick_kind(url: str) -> Optional[str]:
    if VOD_RE.match(url.strip()):
        return "vod"
    if CLIP_RE.match(url.strip()):
        return "clip"
    return None


def _base_opts(dest_dir: Path, name: str, max_height: int, progress: Optional[ProgressCb]) -> Dict[str, Any]:
    s = get_settings()

    def hook(d: Dict[str, Any]) -> None:
        if progress is None or d.get("status") != "downloading":
            return
        total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
        done = d.get("downloaded_bytes") or 0
        progress(done / total if total else 0.0, d.get("_percent_str", "").strip())

    opts: Dict[str, Any] = {
        "format": f"bv*[height<={max_height}]+ba/b[height<={max_height}]/b",
        "outtmpl": str(dest_dir / f"{name}.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "noprogress": True,
        "noplaylist": True,
        "progress_hooks": [hook],
    }
    if s.kick_cookies_file:
        opts["cookiefile"] = str(s.kick_cookies_file)  # subscriber-only VODs
    return opts


def _download(url: str, opts: Dict[str, Any]) -> Path:
    from yt_dlp import YoutubeDL

    with YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
        downloads = info.get("requested_downloads") or []
        path = downloads[0].get("filepath") if downloads else None
        return Path(path or ydl.prepare_filename(info))


def download_for_analysis(url: str, dest_dir: Path, progress: Optional[ProgressCb] = None) -> Path:
    """Whole VOD at low resolution (analysis only needs 480p)."""
    dest_dir.mkdir(parents=True, exist_ok=True)
    existing = sorted(dest_dir.glob("analysis.*"))
    if existing:
        return existing[0]
    opts = _base_opts(dest_dir, "analysis", get_settings().kick_analysis_height, progress)
    return _download(url, opts)


def download_section(url: str, start: float, end: float, dest_dir: Path, progress: Optional[ProgressCb] = None) -> Path:
    """Only ``[start, end]`` at render quality. The file starts at ``start``."""
    from yt_dlp.utils import download_range_func

    dest_dir.mkdir(parents=True, exist_ok=True)
    name = f"section_{int(start * 1000)}_{int(end * 1000)}"
    existing = sorted(dest_dir.glob(f"{name}.*"))
    if existing:
        return existing[0]
    opts = _base_opts(dest_dir, name, get_settings().kick_render_height, progress)
    opts["download_ranges"] = download_range_func(None, [(start, end)])
    opts["force_keyframes_at_cuts"] = True
    return _download(url, opts)
