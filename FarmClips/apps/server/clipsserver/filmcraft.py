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

        cmd = f'"{app_path}" "%1"'
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Classes\FilmCraft.Project\shell\open\command",
        ) as k:
            winreg.SetValueEx(k, "", 0, winreg.REG_SZ, cmd)
    except Exception:
        pass


def is_filmcraft_process_running() -> bool:
    """Comprueba si hay procesos filmcraft.exe en ejecución."""
    if sys.platform != "win32":
        return False
    try:
        res = subprocess.run(
            ["tasklist.exe", "/FI", "IMAGENAME eq filmcraft.exe", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        return "filmcraft.exe" in res.stdout.lower()
    except Exception:
        return False


def find_filmcraft_hwnd_windows() -> Optional[int]:
    """Busca el HWND de la ventana de FilmCraft en el escritorio Default o en el actual."""
    if sys.platform != "win32":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        user32 = ctypes.windll.user32

        target_hwnd = None
        def check_window(hwnd: int, _: int) -> bool:
            nonlocal target_hwnd
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buf = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buf, length + 1)
                    title = buf.value.strip().lower()
                    if title == "filmcraft" or title.startswith("filmcraft –") or title.startswith("filmcraft -"):
                        target_hwnd = hwnd
                        return False
            return True

        cb_type = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        cb = cb_type(check_window)

        # 1. Probar en el escritorio Default interactivo del usuario
        hdesk = user32.OpenDesktopW("Default", 0, False, 0x01FF)
        if hdesk:
            try:
                user32.EnumDesktopWindows(hdesk, cb, 0)
            finally:
                user32.CloseDesktop(hdesk)

        if target_hwnd:
            return target_hwnd

        # 2. Fallback al escritorio del hilo actual
        hwnd = user32.FindWindowW(None, "FilmCraft")
        if hwnd and user32.IsWindow(hwnd) and user32.IsWindowVisible(hwnd):
            return hwnd

        user32.EnumWindows(cb, 0)
        return target_hwnd
    except Exception:
        return None


def has_visible_filmcraft_window() -> bool:
    """Comprueba si existe al menos una ventana visible de FilmCraft en el escritorio de Windows."""
    return find_filmcraft_hwnd_windows() is not None


def cleanup_orphaned_recovery() -> None:
    """Elimina carpetas de Recovery y estados de prueba gráfica huérfanos para evitar popups o bloqueos."""
    if sys.platform != "win32":
        return
    try:
        appdata = os.environ.get("APPDATA", "")
        if appdata:
            rec_dir = Path(appdata) / "FilmCraft" / "Recovery"
            if rec_dir.is_dir():
                for item in rec_dir.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item, ignore_errors=True)

            # Limpiar marcadores gráficos si quedaron en estado fallido tras un cierre previo
            gt = Path(appdata) / "FilmCraft" / "graphics-test.json"
            if gt.is_file():
                try:
                    gt.unlink()
                except Exception:
                    pass
            gs = Path(appdata) / "FilmCraft" / "graphics-start.json"
            if gs.is_file():
                try:
                    gs.unlink()
                except Exception:
                    pass
    except Exception:
        pass


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
    hwnd = find_filmcraft_hwnd_windows()
    if not hwnd:
        return False
    try:
        import ctypes
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32

        cur_thread = kernel32.GetCurrentThreadId()
        win_thread = user32.GetWindowThreadProcessId(hwnd, None)
        user32.AttachThreadInput(cur_thread, win_thread, True)
        user32.ShowWindow(hwnd, 9)  # SW_RESTORE
        user32.SetForegroundWindow(hwnd)
        user32.BringWindowToTop(hwnd)
        user32.AttachThreadInput(cur_thread, win_thread, False)
        return True
    except Exception:
        try:
            import ctypes
            user32 = ctypes.windll.user32
            user32.ShowWindow(hwnd, 9)
            user32.SetForegroundWindow(hwnd)
            user32.BringWindowToTop(hwnd)
            return True
        except Exception:
            return False


def launch_filmcraft_windows(app_path: Path, project_path: Path) -> bool:
    """Lanza FilmCraft explícitamente en el escritorio interactivo WinSta0\\Default."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        from ctypes import wintypes

        class STARTUPINFO(ctypes.Structure):
            _fields_ = [
                ("cb", wintypes.DWORD),
                ("lpReserved", wintypes.LPWSTR),
                ("lpDesktop", wintypes.LPWSTR),
                ("lpTitle", wintypes.LPWSTR),
                ("dwX", wintypes.DWORD),
                ("dwY", wintypes.DWORD),
                ("dwXSize", wintypes.DWORD),
                ("dwYSize", wintypes.DWORD),
                ("dwXCountChars", wintypes.DWORD),
                ("dwYCountChars", wintypes.DWORD),
                ("dwFillAttribute", wintypes.DWORD),
                ("dwFlags", wintypes.DWORD),
                ("wShowWindow", wintypes.WORD),
                ("cbReserved2", wintypes.WORD),
                ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
                ("hStdInput", wintypes.HANDLE),
                ("hStdOutput", wintypes.HANDLE),
                ("hStdError", wintypes.HANDLE),
            ]

        class PROCESS_INFORMATION(ctypes.Structure):
            _fields_ = [
                ("hProcess", wintypes.HANDLE),
                ("hThread", wintypes.HANDLE),
                ("dwProcessId", wintypes.DWORD),
                ("dwThreadId", wintypes.DWORD),
            ]

        si = STARTUPINFO()
        si.cb = ctypes.sizeof(STARTUPINFO)
        si.lpDesktop = r"WinSta0\Default"

        pi = PROCESS_INFORMATION()
        kernel32 = ctypes.windll.kernel32

        cmd = f'"{app_path}" "{project_path}"'
        CREATE_BREAKAWAY_FROM_JOB = 0x01000000

        # Primero intentar romper la atadura a job objects para que el proceso sobreviva autónomo
        res = kernel32.CreateProcessW(
            None,
            cmd,
            None,
            None,
            False,
            CREATE_BREAKAWAY_FROM_JOB,
            None,
            None,
            ctypes.byref(si),
            ctypes.byref(pi),
        )
        if not res:
            # Fallback a creación normal conservando lpDesktop en WinSta0\Default
            res = kernel32.CreateProcessW(
                None,
                cmd,
                None,
                None,
                False,
                0,
                None,
                None,
                ctypes.byref(si),
                ctypes.byref(pi),
            )

        if res:
            kernel32.CloseHandle(pi.hProcess)
            kernel32.CloseHandle(pi.hThread)
            return True
    except Exception:
        pass

    # Fallback con ShellExecute interactivo de Windows
    try:
        os.startfile(str(app_path), arguments=f'"{project_path}"')
        return True
    except Exception:
        try:
            os.startfile(str(project_path))
            return True
        except Exception:
            return False


def _async_bring_to_front(retries: int = 15, delay: float = 0.25) -> None:
    """Intenta traer la ventana de FilmCraft al frente de forma asíncrona mientras se inicializa."""
    def runner():
        for _ in range(retries):
            time.sleep(delay)
            if bring_filmcraft_to_front():
                break

    threading.Thread(target=runner, daemon=True).start()


def _async_import_captions(project_path: Path, cli: Optional[Path], token: str, port: int) -> None:
    """Importa captions.srt en FilmCraft de manera no bloqueante si el archivo existe."""
    if not cli or not cli.is_file():
        return
    srt_path = project_path.parent / "captions.srt"
    if not srt_path.is_file():
        return

    def _worker():
        env = os.environ.copy()
        env["FILMCRAFT_CONTROL_TOKEN"] = token
        for _ in range(12):
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                    s.settimeout(0.3)
                    if s.connect_ex(("127.0.0.1", port)) == 0:
                        break
            except Exception:
                pass
            time.sleep(0.5)

        time.sleep(0.5)
        try:
            subprocess.run(
                [str(cli), "--bridge", f"127.0.0.1:{port}", "exec", "captions.import", f"path={srt_path.resolve()}"],
                env=env,
                capture_output=True,
                text=True,
                timeout=5,
            )
        except Exception:
            pass

    threading.Thread(target=_worker, daemon=True).start()


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

        # Si el bridge está activo y tenemos CLI, intentamos reutilizar la ventana existente
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
                    _async_import_captions(project_path, cli, token, self.bridge_port)
                    return OpenFilmCraftResponse(
                        project_path=str(project_path),
                        launched=False,
                        reused_instance=True,
                    )
            except Exception:
                pass

        # Si el bridge no respondió o no se pudo reutilizar, y hay procesos zombie de FilmCraft colgados en Windows
        # SIN ventana visible en pantalla, los limpiamos (nunca matamos una ventana visible del usuario).
        if sys.platform == "win32":
            if is_filmcraft_process_running() and not has_visible_filmcraft_window():
                kill_filmcraft_processes()
                time.sleep(0.5)

        cleanup_orphaned_recovery()

        # Lanzar la nueva instancia en el desktop interactivo
        if sys.platform == "win32":
            register_windows_association(app, self.bridge_port)
            launched_ok = launch_filmcraft_windows(app, project_path)
            if not launched_ok:
                try:
                    subprocess.Popen(
                        [str(app), str(project_path)],
                    )
                except Exception:
                    subprocess.Popen(
                        ["cmd.exe", "/c", "start", '""', str(app), str(project_path)],
                        shell=True,
                    )
        else:
            args = [
                str(app),
                str(project_path),
            ]
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
