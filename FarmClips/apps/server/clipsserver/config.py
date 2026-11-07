"""Server configuration loaded from and persisted to environment / .env."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

ENV_KEY_RE = re.compile(r"^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def resolve_dotenv_path(path: Optional[Path] = None) -> Path:
    """Resolve the root `.env` file path (respecting `CLIPS_ENV_FILE` or `CLIPS_ROOT_DIR` if set)."""
    if path is not None:
        return path.expanduser().resolve()
    env_override = os.environ.get("CLIPS_ENV_FILE", "").strip()
    if env_override:
        return Path(env_override).expanduser().resolve()
    root_override = os.environ.get("CLIPS_ROOT_DIR", "").strip()
    if root_override:
        return (Path(root_override).expanduser().resolve() / ".env").resolve()
    cwd_env = Path(".env").resolve()
    if cwd_env.is_file() or (cwd_env.parent / ".env.example").is_file():
        return cwd_env
    repo_root = Path(__file__).resolve().parents[3]
    return repo_root / ".env"


def _parse_env_val(raw_v: str) -> str:
    s = raw_v.strip()
    if not s:
        return ""
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1].strip()
    # Strip trailing inline comments like `CLIPS_FIXTURES_DIR= #tests/fixtures/api`
    if "#" in s:
        idx = s.find("#")
        if idx == 0 or s[idx - 1].isspace():
            s = s[:idx].strip()
    return s


def read_dotenv_values(path: Optional[Path] = None) -> Dict[str, str]:
    """Read key-value pairs directly from `.env` without mutating `os.environ`."""
    target = resolve_dotenv_path(path)
    if not target.is_file():
        return {}
    values: Dict[str, str] = {}
    for line in target.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        values[k.strip()] = _parse_env_val(v)
    return values


def load_dotenv(path: Optional[Path] = None, override: bool = False) -> None:
    """Load `.env` into `os.environ`."""
    target = resolve_dotenv_path(path)
    if not target.is_file():
        return
    for line in target.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        key = k.strip()
        val = _parse_env_val(v)
        if override:
            os.environ[key] = val
        elif val:
            os.environ.setdefault(key, val)


def mask_api_key(value: Optional[str]) -> str:
    """Mask an API key for safe display in the UI (e.g. `AIza...8a9b` or `sk-...3f1a`)."""
    if not value:
        return ""
    s = value.strip()
    if not s:
        return ""
    if len(s) <= 8:
        return f"{s[:2]}...{s[-2:]}" if len(s) >= 4 else "****"
    if s.startswith("sk-"):
        return f"sk-...{s[-4:]}"
    return f"{s[:4]}...{s[-4:]}"


def is_masked_or_blank(value: Optional[str], current_raw: Optional[str] = None) -> bool:
    """Return True if an incoming API key string is empty or already masked (should not overwrite `.env`)."""
    if value is None:
        return True
    s = value.strip()
    if not s:
        return True
    if "..." in s or "•" in s or "*" in s:
        return True
    if current_raw and s == mask_api_key(current_raw):
        return True
    return False


def _format_env_value(val: str) -> str:
    clean = val.replace("\r", "").replace("\n", "").strip()
    if any(ch in clean for ch in (" ", "#", '"', "'")) and not (clean.startswith('"') and clean.endswith('"')):
        escaped = clean.replace('"', '\\"')
        return f'"{escaped}"'
    return clean


def update_dotenv_values(
    updates: Mapping[str, Optional[str]],
    path: Optional[Path] = None,
) -> Path:
    """Safely update keys in `.env` preserving comments and ordering, and sync `os.environ`."""
    target = resolve_dotenv_path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    # Seed from .env.example if .env does not exist yet
    if not target.is_file():
        example_path = target.parent / ".env.example"
        if example_path.is_file():
            lines = example_path.read_text(encoding="utf-8").splitlines()
        else:
            lines = [
                "# ============================================================================",
                "# FarmClips — Configuración generada desde el panel web (/settings)",
                "# ============================================================================",
            ]
    else:
        lines = target.read_text(encoding="utf-8").splitlines()

    normalized_updates: Dict[str, str] = {}
    for k, v in updates.items():
        if v is None:
            continue
        normalized_updates[k.strip()] = str(v).strip()

    seen_keys = set()
    new_lines: List[str] = []
    for line in lines:
        m = ENV_KEY_RE.match(line)
        if m:
            key = m.group(1)
            if key in normalized_updates:
                new_val = normalized_updates[key]
                new_lines.append(f"{key}={_format_env_value(new_val)}")
                seen_keys.add(key)
                continue
        new_lines.append(line)

    for key, new_val in normalized_updates.items():
        if key not in seen_keys:
            new_lines.append(f"{key}={_format_env_value(new_val)}")

    target.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    # Apply immediately to os.environ
    for key, new_val in normalized_updates.items():
        os.environ[key] = new_val

    return target


@dataclass(frozen=True)
class ServerSettings:
    data_dir: Path = field(default_factory=lambda: Path("data").resolve())
    host: str = "127.0.0.1"
    port: int = 8790
    style_preset: str = "hormozi-gaming"
    # Budget guard (30,000 COP ~= US$9.40 -> default US$9.00 cap)
    max_budget_usd: float = 9.0
    # STT providers
    stt_primary: str = "deepgram"        # deepgram | groq | fixture
    stt_backup: str = "groq"             # groq | deepgram | none
    deepgram_model: str = "nova-3"
    groq_stt_model: str = "whisper-large-v3-turbo"
    default_keyterms: List[str] = field(
        default_factory=lambda: ["clutch", "headshot", "boss", "lag", "stream", "chat", "bro", "no puede ser"]
    )
    chunk_target_sec: float = 600.0
    # LLM providers
    llm_primary: str = "gemini"          # gemini | openai_compat | fixture
    llm_model: str = "gemini-3.5-flash-lite"
    llm_backup: str = "openai_compat"    # openai_compat | gemini | none
    llm_backup_model: str = "gpt-6-luna"
    llm_backup_base_url: str = "https://api.openai.com/v1"
    # API Keys in memory
    deepgram_api_key: str = ""
    groq_api_key: str = ""
    gemini_api_key: str = ""
    openai_api_key: str = ""
    # Pools & Render + DaVinci Resolve MCP integration
    cpu_workers: int = 2
    use_nvenc: bool = True
    nvenc_slots: int = 2
    auto_render_top_k: int = 5
    auto_render_min_score: float = 60.0
    enable_gameplay_motion: bool = True
    editor_backend: str = "local"        # local | resolve_mcp | both
    resolve_mcp_mode: str = "auto"       # auto | mcp_stdio | mcp_http | direct_script | bundle_only
    resolve_mcp_command: str = ""
    resolve_mcp_url: str = ""
    resolve_project_prefix: str = "FarmClips"
    resolve_auto_export: bool = False
    # Google Drive watcher & direct OAuth 2.0
    drive_mode: str = "local"            # local | oauth | service_account | disabled
    drive_local_dir: Path = field(default_factory=lambda: Path("data/drive_mirror").resolve())
    drive_service_account_json: Optional[Path] = None
    drive_root_folder_id: Optional[str] = None
    drive_client_id: str = ""
    drive_client_secret: str = ""
    drive_poll_sec: float = 120.0
    # Notifications & Storage Maintenance
    webhook_url: Optional[str] = None
    public_web_url: str = "http://127.0.0.1:3040"
    temp_ttl_days: float = 7.0
    # Testing / Offline fixtures
    fixtures_dir: Optional[Path] = None

    @property
    def drive_oauth_token_path(self) -> Path:
        return (self.data_dir / "drive_oauth_token.json").resolve()

    def is_drive_oauth_connected(self) -> bool:
        tpath = self.drive_oauth_token_path
        if not tpath.is_file():
            return False
        try:
            import json

            raw = json.loads(tpath.read_text(encoding="utf-8"))
            return bool(raw.get("refresh_token") or raw.get("access_token"))
        except Exception:
            return False

    @classmethod
    def from_env(cls) -> "ServerSettings":
        root_dir = Path(os.environ.get("CLIPS_ROOT_DIR", ".")).resolve()
        data_dir = Path(os.environ.get("CLIPS_DATA_DIR", str(root_dir / "data"))).expanduser().resolve()
        sa_raw = os.environ.get("CLIPS_DRIVE_SERVICE_ACCOUNT_JSON") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        sa_path = Path(sa_raw).expanduser().resolve() if sa_raw and Path(sa_raw).expanduser().is_file() else None
        drive_folder_id = os.environ.get("CLIPS_DRIVE_ROOT_FOLDER_ID", "").strip() or None
        drive_client_id = os.environ.get("CLIPS_DRIVE_CLIENT_ID", "").strip()
        drive_client_secret = os.environ.get("CLIPS_DRIVE_CLIENT_SECRET", "").strip()

        oauth_token_exists = (data_dir / "drive_oauth_token.json").is_file()
        if oauth_token_exists and drive_client_id and drive_client_secret:
            default_drive_mode = "oauth"
        elif sa_path and drive_folder_id:
            default_drive_mode = "service_account"
        else:
            default_drive_mode = "local"
        drive_mode = os.environ.get("CLIPS_DRIVE_MODE", default_drive_mode).strip().lower()
        drive_local = Path(os.environ.get("CLIPS_DRIVE_LOCAL_DIR", str(data_dir / "drive_mirror"))).expanduser().resolve()

        fix_raw = os.environ.get("CLIPS_FIXTURES_DIR", "").strip()
        fix_path = Path(fix_raw).expanduser().resolve() if fix_raw else None

        cpu_count = os.cpu_count() or 4
        keyterms_raw = os.environ.get("CLIPS_KEYTERMS", "clutch,headshot,boss,lag,stream,chat,bro,no puede ser")

        editor_backend = os.environ.get("CLIPS_EDITOR_BACKEND", "local").strip().lower()
        if editor_backend not in ("local", "resolve_mcp", "both"):
            editor_backend = "local"

        resolve_mcp_mode = os.environ.get("CLIPS_RESOLVE_MCP_MODE", "auto").strip().lower()
        if resolve_mcp_mode not in ("auto", "mcp_stdio", "mcp_http", "direct_script", "bundle_only"):
            resolve_mcp_mode = "auto"

        return cls(
            data_dir=data_dir,
            host=os.environ.get("CLIPS_HOST", "127.0.0.1"),
            port=int(os.environ.get("CLIPS_PORT", "8790")),
            style_preset=os.environ.get("CLIPS_STYLE_PRESET", "hormozi-gaming"),
            max_budget_usd=float(os.environ.get("CLIPS_MAX_BUDGET_USD", "9.0")),
            stt_primary=os.environ.get("CLIPS_STT_PRIMARY", "deepgram").strip().lower(),
            stt_backup=os.environ.get("CLIPS_STT_BACKUP", "groq").strip().lower(),
            deepgram_model=os.environ.get("CLIPS_DEEPGRAM_MODEL", "nova-3").strip(),
            groq_stt_model=os.environ.get("CLIPS_GROQ_STT_MODEL", "whisper-large-v3-turbo").strip(),
            default_keyterms=[t.strip() for t in keyterms_raw.split(",") if t.strip()],
            chunk_target_sec=float(os.environ.get("CLIPS_CHUNK_TARGET_SEC", "600")),
            llm_primary=os.environ.get("CLIPS_LLM_PRIMARY", "gemini").strip().lower(),
            llm_model=os.environ.get("CLIPS_LLM_MODEL", "gemini-3.5-flash-lite").strip(),
            llm_backup=os.environ.get("CLIPS_LLM_BACKUP", "openai_compat").strip().lower(),
            llm_backup_model=os.environ.get("CLIPS_LLM_BACKUP_MODEL", "gpt-6-luna").strip(),
            llm_backup_base_url=os.environ.get("CLIPS_LLM_BACKUP_BASE_URL", "https://api.openai.com/v1").strip(),
            deepgram_api_key=os.environ.get("DEEPGRAM_API_KEY", "").strip(),
            groq_api_key=os.environ.get("GROQ_API_KEY", "").strip(),
            gemini_api_key=os.environ.get("GEMINI_API_KEY", "").strip(),
            openai_api_key=os.environ.get("OPENAI_API_KEY", "").strip(),
            cpu_workers=max(1, int(os.environ.get("CLIPS_CPU_WORKERS", str(max(1, cpu_count - 1))))),
            use_nvenc=_bool("CLIPS_NVENC", True),
            nvenc_slots=max(1, int(os.environ.get("CLIPS_RENDER_SLOTS_NVENC", "2"))),
            auto_render_top_k=int(os.environ.get("CLIPS_AUTO_RENDER_TOP_K", "5")),
            auto_render_min_score=float(os.environ.get("CLIPS_AUTO_RENDER_MIN_SCORE", "60.0")),
            enable_gameplay_motion=_bool("CLIPS_ENABLE_MOTION", True),
            editor_backend=editor_backend,
            resolve_mcp_mode=resolve_mcp_mode,
            resolve_mcp_command=os.environ.get("CLIPS_RESOLVE_MCP_COMMAND", "").strip(),
            resolve_mcp_url=os.environ.get("CLIPS_RESOLVE_MCP_URL", "").strip(),
            resolve_project_prefix=os.environ.get("CLIPS_RESOLVE_PROJECT_PREFIX", "FarmClips").strip() or "FarmClips",
            resolve_auto_export=_bool("CLIPS_RESOLVE_AUTO_EXPORT", False),
            drive_mode=drive_mode,
            drive_local_dir=drive_local,
            drive_service_account_json=sa_path,
            drive_root_folder_id=drive_folder_id,
            drive_client_id=drive_client_id,
            drive_client_secret=drive_client_secret,
            drive_poll_sec=float(os.environ.get("CLIPS_DRIVE_POLL_SEC", "120")),
            webhook_url=os.environ.get("CLIPS_WEBHOOK_URL", "").strip() or None,
            public_web_url=os.environ.get("CLIPS_PUBLIC_WEB_URL", "http://127.0.0.1:3040").strip(),
            temp_ttl_days=float(os.environ.get("CLIPS_TEMP_TTL_DAYS", "7.0")),
            fixtures_dir=fix_path,
        )

    def to_masked_dict(self, env_path: Optional[Path] = None) -> Dict[str, Any]:
        """Serialize current settings with masked API keys and `has_key` booleans."""
        dg_masked = mask_api_key(self.deepgram_api_key)
        gq_masked = mask_api_key(self.groq_api_key)
        gm_masked = mask_api_key(self.gemini_api_key)
        oa_masked = mask_api_key(self.openai_api_key)
        drv_secret_masked = mask_api_key(self.drive_client_secret)

        has_dg = bool(self.deepgram_api_key)
        has_gq = bool(self.groq_api_key)
        has_gm = bool(self.gemini_api_key)
        has_oa = bool(self.openai_api_key)
        has_drv_secret = bool(self.drive_client_secret)

        return {
            "env_path": str(resolve_dotenv_path(env_path)),
            "stt_primary": self.stt_primary,
            "stt_backup": self.stt_backup,
            "deepgram_model": self.deepgram_model,
            "groq_stt_model": self.groq_stt_model,
            "llm_primary": self.llm_primary,
            "llm_model": self.llm_model,
            "llm_backup": self.llm_backup,
            "llm_backup_model": self.llm_backup_model,
            "llm_backup_base_url": self.llm_backup_base_url,
            "max_budget_usd": self.max_budget_usd,
            "webhook_url": self.webhook_url or "",
            "temp_ttl_days": self.temp_ttl_days,
            "auto_render_top_k": self.auto_render_top_k,
            "auto_render_min_score": self.auto_render_min_score,
            "default_keyterms": list(self.default_keyterms),
            "editor_backend": self.editor_backend,
            "resolve_mcp_mode": self.resolve_mcp_mode,
            "resolve_mcp_command": self.resolve_mcp_command,
            "resolve_mcp_url": self.resolve_mcp_url,
            "resolve_project_prefix": self.resolve_project_prefix,
            "resolve_auto_export": self.resolve_auto_export,
            "drive_mode": self.drive_mode,
            "drive_local_dir": str(self.drive_local_dir),
            "drive_root_folder_id": self.drive_root_folder_id or "",
            "drive_poll_sec": self.drive_poll_sec,
            "drive_client_id": self.drive_client_id,
            "drive_client_secret": drv_secret_masked,
            "has_drive_client_secret": has_drv_secret,
            "drive_oauth_connected": self.is_drive_oauth_connected(),
            "deepgram_api_key": dg_masked,
            "groq_api_key": gq_masked,
            "gemini_api_key": gm_masked,
            "openai_api_key": oa_masked,
            "has_deepgram_key": has_dg,
            "has_groq_key": has_gq,
            "has_gemini_key": has_gm,
            "has_openai_key": has_oa,
            "api_keys": {
                "deepgram": {"masked": dg_masked, "has_key": has_dg},
                "groq": {"masked": gq_masked, "has_key": has_gq},
                "gemini": {"masked": gm_masked, "has_key": has_gm},
                "openai": {"masked": oa_masked, "has_key": has_oa},
            },
        }


@lru_cache(maxsize=1)
def get_server_settings() -> ServerSettings:
    load_dotenv()
    return ServerSettings.from_env()


def reload_server_settings(path: Optional[Path] = None) -> ServerSettings:
    """Reload `.env` with override=True, clear settings cache, and return fresh `ServerSettings`."""
    load_dotenv(path=path, override=True)
    get_server_settings.cache_clear()
    return get_server_settings()
