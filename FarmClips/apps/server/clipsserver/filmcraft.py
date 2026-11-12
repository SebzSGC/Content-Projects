"""Servicios de integración, lanzamiento y exportación para FilmCraft."""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
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
    return new_tok


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
                    return OpenFilmCraftResponse(
                        project_path=str(project_path),
                        launched=False,
                        reused_instance=True,
                    )
            except Exception:
                pass

        # Si no se pudo reutilizar, lanzamos una nueva instancia en el desktop interactivo.
        # En Windows usamos CREATE_NEW_PROCESS_GROUP (nunca DETACHED_PROCESS porque aislaría la ventana).
        creation_flags = 0
        if sys.platform == "win32":
            creation_flags = subprocess.CREATE_NEW_PROCESS_GROUP

        args = [str(app), "--control", str(self.bridge_port), str(project_path)]
        subprocess.Popen(
            args,
            env=child_env,
            creationflags=creation_flags,
            close_fds=(sys.platform != "win32"),
        )

        return OpenFilmCraftResponse(
            project_path=str(project_path),
            launched=True,
            reused_instance=False,
        )
