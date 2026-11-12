"""Servicios de integración, lanzamiento y exportación para FilmCraft."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import threading
import time
from fractions import Fraction
from pathlib import Path
from typing import Any, Dict, List, Literal, Optional, Tuple

from clipseditplan import EditPlan
from clipsinterchange import ExportContext, ExportResult
from clipsinterchange.filmcraft.exporter import FilmCraftExporter
from clipsinterchange.otio.exporter import OtioExporter
from pydantic import BaseModel, Field

DEFAULT_SUPPORTED_VERSION = "0.20.1"


class FilmCraftStatus(BaseModel):
    installed: bool = False
    path: Optional[str] = None
    cli_path: Optional[str] = None
    version: Optional[str] = None
    supported_version: str = DEFAULT_SUPPORTED_VERSION
    version_ok: bool = False
    bridge_up: bool = False
    mcp_available: bool = False


class OpenFilmCraftResponse(BaseModel):
    project_path: str
    launched: bool
    reused_instance: bool
    warnings: List[Dict[str, Any]] = Field(default_factory=list)


def ensure_control_token() -> str:
    """Obtiene o genera un token seguro de 64 caracteres hex para el FilmCraft control server."""
    env_tok = os.environ.get("FILMCRAFT_CONTROL_TOKEN", "").strip()
    if len(env_tok) == 64 and all(c in "0123456789abcdefABCDEF" for c in env_tok):
        _persist_user_env_token(env_tok)
        return env_tok

    token_file = (
        Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
        / "FilmCraft"
        / ".farmclips_control_token"
    )
    try:
        if token_file.is_file():
            tok = token_file.read_text(encoding="utf-8").strip()
            if len(tok) == 64 and all(c in "0123456789abcdefABCDEF" for c in tok):
                os.environ["FILMCRAFT_CONTROL_TOKEN"] = tok
                _persist_user_env_token(tok)
                return tok
    except Exception:
        pass

    new_tok = secrets.token_hex(32)
    os.environ["FILMCRAFT_CONTROL_TOKEN"] = new_tok
    try:
        token_file.parent.mkdir(parents=True, exist_ok=True)
        token_file.write_text(new_tok, encoding="utf-8")
    except Exception:
        pass
    _persist_user_env_token(new_tok)
    return new_tok


def _persist_user_env_token(token: str) -> None:
    """Registra el token en HKCU\\Environment para que los procesos de ShellExecute lo hereden."""
    if sys.platform != "win32":
        return
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Environment", 0, winreg.KEY_SET_VALUE
        ) as key:
            winreg.SetValueEx(key, "FILMCRAFT_CONTROL_TOKEN", 0, winreg.REG_SZ, token)
    except Exception:
        pass


def register_windows_association(app_path: Path, bridge_port: int = 9876) -> None:
    """Asocia la extensión .fcproj con FilmCraft en el registro de Windows del usuario."""
    if sys.platform != "win32":
        return
    try:
        import winreg

        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.fcproj") as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "FilmCraft.Project")

        cmd = f'"{app_path}" --graphics default --control {bridge_port} "%1"'
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\FilmCraft.Project\shell\open\command",
        ) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    except Exception:
        pass


def has_visible_filmcraft_window() -> bool:
    """Comprueba si existe al menos una ventana visible de FilmCraft en el escritorio de Windows."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        found = False

        def callback(hwnd: int, _: int) -> bool:
            nonlocal found
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.lower()
                    if "filmcraft" in title:
                        found = True
                        return False
            return True

        cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(cb_type(callback), 0)
        return found
    except Exception:
        return False


def kill_filmcraft_processes() -> None:
    """Termina procesos de FilmCraft (ej. zombies creados en segundo plano sin ventana)."""
    if sys.platform != "win32":
        return
    try:
        subprocess.run(
            ["taskkill.exe", "/F", "/IM", "filmcraft.exe", "/T"],
            capture_output=True,
            timeout=5,
        )
    except Exception:
        pass


def bring_filmcraft_to_front() -> bool:
    """Trae la ventana de FilmCraft al primer plano en el escritorio de Windows."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        target_hwnd = None

        def callback(hwnd: int, _: int) -> bool:
            nonlocal target_hwnd
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value.lower()
                    if "filmcraft" in title:
                        target_hwnd = hwnd
                        return False
            return True

        cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(cb_type(callback), 0)

        if target_hwnd:
            # Desbloquear y forzar al frente en Windows
            user32.keybd_event(0x12, 0, 0, 0)  # Alt down
            user32.ShowWindow(target_hwnd, 9)  # SW_RESTORE
            user32.SetForegroundWindow(target_hwnd)
            user32.BringWindowToTop(target_hwnd)
            user32.keybd_event(0x12, 0, 2, 0)  # Alt up
            return True
    except Exception:
        pass
    return False


def _async_bring_to_front(retries: int = 15, delay: float = 0.25) -> None:
    """Intenta traer la ventana de FilmCraft al frente de forma asíncrona mientras se inicializa."""
    def runner():
        for _ in range(retries):
            time.sleep(delay)
            if bring_filmcraft_to_front():
                break

    threading.Thread(target=runner, daemon=True).start()


class FilmCraftLauncher:
    """Detecta, consulta y controla la aplicación de escritorio FilmCraft."""

    def __init__(
        self,
        app_path: Optional[str] = None,
        cli_path: Optional[str] = None,
        bridge_port: int = 9876,
    ):
        self.app_path_override = app_path
        self.cli_path_override = cli_path
        self.bridge_port = bridge_port

    def find_app_binary(self) -> Optional[Path]:
        """Localiza el ejecutable principal filmcraft.exe."""
        if self.app_path_override:
            p = Path(self.app_path_override).expanduser()
            if p.is_file():
                return p.resolve()

        # Variable de entorno directa
        env_val = os.environ.get("CLIPS_FILMCRAFT_PATH", "").strip()
        if env_val:
            p = Path(env_val).expanduser()
            if p.is_file():
                return p.resolve()

        # Ubicación estándar de instalación en Windows (ArtCraft Launcher)
        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidate = Path(local_app) / "Programs" / "ArtCraft" / "FilmCraft" / "filmcraft.exe"
            if candidate.is_file():
                return candidate.resolve()

        # Buscar en PATH
        which = shutil.which("filmcraft") or shutil.which("filmcraft.exe")
        if which:
            return Path(which).resolve()

        return None

    def find_cli_binary(self) -> Optional[Path]:
        """Localiza el ejecutable filmcraft-cli.exe."""
        if self.cli_path_override:
            p = Path(self.cli_path_override).expanduser()
            if p.is_file():
                return p.resolve()

        env_val = os.environ.get("CLIPS_FILMCRAFT_CLI_PATH", "").strip()
        if env_val:
            p = Path(env_val).expanduser()
            if p.is_file():
                return p.resolve()

        app = self.find_app_binary()
        if app:
            cli_neighbor = app.parent / ("filmcraft-cli.exe" if sys.platform == "win32" else "filmcraft-cli")
            if cli_neighbor.is_file():
                return cli_neighbor.resolve()

        local_app = os.environ.get("LOCALAPPDATA", "")
        if local_app:
            candidate = Path(local_app) / "Programs" / "ArtCraft" / "FilmCraft" / "filmcraft-cli.exe"
            if candidate.is_file():
                return candidate.resolve()

        which = shutil.which("filmcraft-cli") or shutil.which("filmcraft-cli.exe")
        if which:
            return Path(which).resolve()

        return None

    def is_bridge_listening(self, host: str = "127.0.0.1", port: Optional[int] = None) -> bool:
        """Comprueba si el socket TCP de control loopback está abierto."""
        p = port or self.bridge_port
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(0.2)
            try:
                s.connect((host, p))
                return True
            except (socket.error, ConnectionRefusedError, TimeoutError):
                return False

    def get_version(self) -> Optional[str]:
        """Consulta la versión actual reportada por filmcraft-cli."""
        cli = self.find_cli_binary()
        if not cli:
            return None
        try:
            res = subprocess.run([str(cli), "--version"], capture_output=True, text=True, timeout=3)
            if res.returncode == 0:
                # salida tipo "filmcraft-cli 0.20.1"
                out = res.stdout.strip()
                parts = out.split()
                return parts[-1] if parts else out
        except Exception:
            pass
        return None

    def get_status(self) -> FilmCraftStatus:
        """Devuelve el diagnóstico completo del entorno de FilmCraft."""
        app = self.find_app_binary()
        cli = self.find_cli_binary()
        version = self.get_version()
        installed = app is not None and app.is_file()
        version_ok = version == DEFAULT_SUPPORTED_VERSION if version else False
        bridge_up = self.is_bridge_listening()

        return FilmCraftStatus(
            installed=installed,
            path=str(app) if app else None,
            cli_path=str(cli) if cli else None,
            version=version,
            supported_version=DEFAULT_SUPPORTED_VERSION,
            version_ok=version_ok,
            bridge_up=bridge_up,
            mcp_available=cli is not None,
        )

    def open_project(self, project_path: Path) -> OpenFilmCraftResponse:
        """Abre el proyecto en FilmCraft (reutilizando instancia activa o lanzando una nueva)."""
        app = self.find_app_binary()
        cli = self.find_cli_binary()
        if not app:
            raise FileNotFoundError("No se encontró el ejecutable de FilmCraft en el equipo")

        project_path = project_path.resolve()
        if not project_path.is_file():
            raise FileNotFoundError(f"El archivo de proyecto no existe: {project_path}")

        token = ensure_control_token()
        child_env = os.environ.copy()
        child_env["FILMCRAFT_CONTROL_TOKEN"] = token

        bridge_active = self.is_bridge_listening()

        # Si el bridge responde en Windows pero ninguna ventana es visible (proceso zombie en segundo plano),
        # cerramos esos procesos para asegurar que se lance una instancia visible en pantalla.
        if bridge_active and sys.platform == "win32" and not has_visible_filmcraft_window():
            kill_filmcraft_processes()
            time.sleep(0.5)
            bridge_active = False

        # Si el bridge está activo y tenemos CLI, reutilizamos la ventana existente
        if bridge_active and cli:
            cmd = [
                str(cli),
                "--bridge",
                f"127.0.0.1:{self.bridge_port}",
                "exec",
                "file.open",
                f"path={project_path}",
            ]
            try:
                res = subprocess.run(
                    cmd, env=child_env, capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0:
                    _async_bring_to_front()
                    return OpenFilmCraftResponse(
                        project_path=str(project_path),
                        launched=False,
                        reused_instance=True,
                    )
            except Exception:
                pass

        # Si no se pudo reutilizar, lanzamos una nueva instancia en el desktop interactivo.
        # En Windows registramos la asociación de .fcproj y delegamos a Shell.Application de Explorer,
        # lo que garantiza que Windows cree el proceso en la Window Station interactiva del usuario (winsta0\default)
        # con aceleración Vulkan/DX12, el control loopback activo y su ventana visible en primer plano.
        if sys.platform == "win32":
            register_windows_association(app, self.bridge_port)
            opened = False
            try:
                os.startfile(str(project_path))
                opened = True
            except Exception:
                pass
            if not opened:
                ps_open = f"(New-Object -ComObject Shell.Application).Open('{project_path}')"
                subprocess.run(
                    ["powershell.exe", "-NoProfile", "-Command", ps_open],
                    capture_output=True,
                    timeout=5,
                )
        else:
            args = [str(app), "--graphics", "default", "--control", str(self.bridge_port), str(project_path)]
            subprocess.Popen(
                args,
                env=child_env,
                close_fds=True,
            )

        _async_bring_to_front()

        return OpenFilmCraftResponse(
            project_path=str(project_path),
            launched=True,
            reused_instance=False,
        )
