"""VidForge Native Desktop Launcher (pywebview WebView2 + FastAPI Supervisor)."""

from __future__ import annotations

import argparse
import ctypes
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

import httpx
import uvicorn


def _find_free_port(preferred: int = 8765) -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        if s.connect_ex(("127.0.0.1", preferred)) != 0:
            return preferred
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


def _set_app_user_model_id() -> None:
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("VidForge.Desktop.v1")
        except Exception:
            pass


class DesktopJsApi:
    """Native bridge exposed to the React SPA via window.pywebview.api."""

    def __init__(self) -> None:
        self._window = None

    def attach_window(self, window: Any) -> None:
        self._window = window

    def pick_folder(self) -> str | None:
        if not self._window:
            return None
        import webview
        res = self._window.create_file_dialog(webview.FOLDER_DIALOG)
        return res[0] if res else None

    def reveal_in_explorer(self, target_path: str) -> bool:
        p = Path(target_path)
        if not p.exists():
            return False
        if sys.platform == "win32":
            if p.is_dir():
                subprocess.Popen(["explorer.exe", str(p.resolve())])
            else:
                subprocess.Popen(["explorer.exe", f"/select,{str(p.resolve())}"])
            return True
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="VidForge Desktop Launcher")
    parser.add_argument("--port", type=int, default=0, help="Port for local FastAPI server")
    parser.add_argument("--server-only", action="store_true", help="Run server without opening WebView2 window")
    args = parser.parse_args()

    _set_app_user_model_id()
    port = args.port or _find_free_port(8765)
    url = f"http://127.0.0.1:{port}"

    from vidforge.api.app import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    if args.server_only:
        print(f"VidForge API Server running on {url}")
        server.run()
        return 0

    server_thread = threading.Thread(target=server.run, daemon=True)
    server_thread.start()

    # Wait for /api/v1/health
    for _ in range(50):
        try:
            r = httpx.get(f"{url}/api/v1/health", timeout=0.5)
            if r.status_code == 200:
                break
        except Exception:
            time.sleep(0.1)

    import webview
    js_api = DesktopJsApi()
    window = webview.create_window(
        title="VidForge Studio — Generador Modular de Vídeos IA",
        url=url,
        js_api=js_api,
        width=1440,
        height=900,
        min_size=(1100, 720),
        background_color="#090D16",
    )
    js_api.attach_window(window)
    webview.start(gui="edgechromium")
    server.should_exit = True
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
