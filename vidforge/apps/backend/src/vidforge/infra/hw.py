"""Hardware capabilities and encoder probing (NVENC / QSV / AMF / CPU)."""

from __future__ import annotations

import os
import shutil
from functools import lru_cache
from typing import Any

import psutil

from vidforge.infra.paths import get_ffmpeg_path, get_chrome_path
from vidforge.infra.procs import run_hidden


def _probe_encoder(ffmpeg_path: str, encoder: str) -> bool:
    if not os.path.exists(ffmpeg_path) and not shutil.which(ffmpeg_path):
        return False
    try:
        res = run_hidden(
            [
                ffmpeg_path,
                "-hide_banner",
                "-v",
                "error",
                "-f",
                "lavfi",
                "-i",
                "color=black:s=256x256:d=0.1",
                "-c:v",
                encoder,
                "-f",
                "null",
                "-",
            ],
            timeout=10.0,
        )
        return res.returncode == 0
    except Exception:
        return False


def _detect_nvidia_gpu() -> dict[str, Any] | None:
    smi = shutil.which("nvidia-smi")
    if not smi:
        return None
    try:
        res = run_hidden(
            [smi, "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"],
            timeout=5.0,
        )
        if res.returncode == 0 and res.stdout.strip():
            parts = [p.strip() for p in res.stdout.splitlines()[0].split(",")]
            if len(parts) >= 3:
                return {
                    "name": parts[0],
                    "vram": parts[1],
                    "driver_version": parts[2],
                }
    except Exception:
        pass
    return None


@lru_cache(maxsize=1)
def detect_hardware() -> dict[str, Any]:
    ff = get_ffmpeg_path()
    gpu_info = _detect_nvidia_gpu()
    nvenc_ok = _probe_encoder(ff, "h264_nvenc")
    amf_ok = _probe_encoder(ff, "h264_amf")
    qsv_ok = _probe_encoder(ff, "h264_qsv")

    if nvenc_ok:
        preferred = "h264_nvenc"
    elif amf_ok:
        preferred = "h264_amf"
    elif qsv_ok:
        preferred = "h264_qsv"
    else:
        preferred = "libx264"

    vm = psutil.virtual_memory()
    return {
        "cpu_cores_physical": psutil.cpu_count(logical=False) or 4,
        "cpu_cores_logical": psutil.cpu_count(logical=True) or 8,
        "ram_total_gb": round(vm.total / (1024**3), 1),
        "gpu": gpu_info,
        "encoders": {
            "h264_nvenc": nvenc_ok,
            "h264_amf": amf_ok,
            "h264_qsv": qsv_ok,
            "libx264": True,
        },
        "preferred_encoder": preferred,
        "ffmpeg_path": ff,
        "chrome_path": get_chrome_path(),
    }
