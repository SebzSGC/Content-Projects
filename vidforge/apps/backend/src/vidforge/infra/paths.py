"""Centralized path resolution for VidForge on Windows x64."""

from __future__ import annotations

import os
import shutil
from pathlib import Path


def get_workspace_root() -> Path:
    env_root = os.environ.get("VIDFORGE_ROOT")
    if env_root:
        return Path(env_root).resolve()
    # apps/backend/src/vidforge/infra/paths.py -> 5 levels up is vidforge root
    return Path(__file__).resolve().parents[5]


ROOT_DIR = get_workspace_root()
RUNTIME_DIR = ROOT_DIR / "runtime"
STORAGE_DIR = ROOT_DIR / "storage"
PROJECTS_DIR = STORAGE_DIR / "projects"
CACHE_DIR = STORAGE_DIR / "cache"
TEMP_DIR = STORAGE_DIR / "temp"
USERDATA_DIR = STORAGE_DIR / "userdata"
LOGS_DIR = STORAGE_DIR / "logs"

CONTRACTS_DIR = ROOT_DIR / "packages" / "contracts"
TEMPLATES_DIR = ROOT_DIR / "packages" / "templates"
SIDECAR_SCRIPT = ROOT_DIR / "apps" / "render-sidecar" / "src" / "sidecar.mjs"
WEB_DIST_DIR = ROOT_DIR / "apps" / "web" / "dist"


def ensure_directories() -> None:
    for d in (PROJECTS_DIR, CACHE_DIR, TEMP_DIR, USERDATA_DIR, LOGS_DIR):
        d.mkdir(parents=True, exist_ok=True)


def get_ffmpeg_path() -> str:
    local_ff = RUNTIME_DIR / "ffmpeg" / "ffmpeg.exe"
    if local_ff.exists():
        return str(local_ff)
    which_ff = shutil.which("ffmpeg")
    return which_ff or str(local_ff)


def get_ffprobe_path() -> str:
    local_fp = RUNTIME_DIR / "ffmpeg" / "ffprobe.exe"
    if local_fp.exists():
        return str(local_fp)
    which_fp = shutil.which("ffprobe")
    return which_fp or str(local_fp)


def get_node_path() -> str:
    local_node = RUNTIME_DIR / "node" / "node.exe"
    if local_node.exists():
        return str(local_node)
    which_node = shutil.which("node")
    return which_node or "node.exe"


def get_chrome_path() -> str:
    candidates = [
        RUNTIME_DIR / "browsers" / "chrome-headless-shell-win64" / "chrome-headless-shell.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Google" / "Chrome" / "Application" / "chrome.exe",
        Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
        Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft" / "Edge" / "Application" / "msedge.exe",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "msedge.exe"
