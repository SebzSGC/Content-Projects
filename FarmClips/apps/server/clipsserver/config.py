"""Server configuration loaded from environment / .env."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import List, Optional


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def load_dotenv(path: Path = Path(".env")) -> None:
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or "=" not in s:
            continue
        k, _, v = s.partition("=")
        val = v.strip().strip('"').strip("'")
        if val:
            os.environ.setdefault(k.strip(), val)


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
    llm_backup: str = "openai_compat"    # openai_compat | none
    llm_backup_model: str = "gpt-6-luna"
    llm_backup_base_url: str = "https://api.openai.com/v1"
    # Pools & Render
    cpu_workers: int = 2
    use_nvenc: bool = True
    nvenc_slots: int = 2
    auto_render_top_k: int = 5
    auto_render_min_score: float = 60.0
    enable_gameplay_motion: bool = True
    # Google Drive watcher
    drive_mode: str = "local"            # local | service_account | disabled
    drive_local_dir: Path = field(default_factory=lambda: Path("data/drive_mirror").resolve())
    drive_service_account_json: Optional[Path] = None
    drive_root_folder_id: Optional[str] = None
    drive_poll_sec: float = 120.0
    # Notifications & Storage Maintenance
    webhook_url: Optional[str] = None
    public_web_url: str = "http://127.0.0.1:3040"
    temp_ttl_days: float = 7.0
    # Testing / Offline fixtures
    fixtures_dir: Optional[Path] = None

    @classmethod
    def from_env(cls) -> "ServerSettings":
        root_dir = Path(os.environ.get("CLIPS_ROOT_DIR", ".")).resolve()
        data_dir = Path(os.environ.get("CLIPS_DATA_DIR", str(root_dir / "data"))).expanduser().resolve()
        sa_raw = os.environ.get("CLIPS_DRIVE_SERVICE_ACCOUNT_JSON") or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
        sa_path = Path(sa_raw).expanduser().resolve() if sa_raw and Path(sa_raw).expanduser().is_file() else None
        drive_folder_id = os.environ.get("CLIPS_DRIVE_ROOT_FOLDER_ID", "").strip() or None

        default_drive_mode = "service_account" if (sa_path and drive_folder_id) else "local"
        drive_mode = os.environ.get("CLIPS_DRIVE_MODE", default_drive_mode).strip().lower()
        drive_local = Path(os.environ.get("CLIPS_DRIVE_LOCAL_DIR", str(data_dir / "drive_mirror"))).expanduser().resolve()

        fix_raw = os.environ.get("CLIPS_FIXTURES_DIR", "").strip()
        fix_path = Path(fix_raw).expanduser().resolve() if fix_raw else None

        cpu_count = os.cpu_count() or 4
        keyterms_raw = os.environ.get("CLIPS_KEYTERMS", "clutch,headshot,boss,lag,stream,chat,bro,no puede ser")

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
            cpu_workers=max(1, int(os.environ.get("CLIPS_CPU_WORKERS", str(max(1, cpu_count - 1))))),
            use_nvenc=_bool("CLIPS_NVENC", True),
            nvenc_slots=max(1, int(os.environ.get("CLIPS_RENDER_SLOTS_NVENC", "2"))),
            auto_render_top_k=int(os.environ.get("CLIPS_AUTO_RENDER_TOP_K", "5")),
            auto_render_min_score=float(os.environ.get("CLIPS_AUTO_RENDER_MIN_SCORE", "60.0")),
            enable_gameplay_motion=_bool("CLIPS_ENABLE_MOTION", True),
            drive_mode=drive_mode,
            drive_local_dir=drive_local,
            drive_service_account_json=sa_path,
            drive_root_folder_id=drive_folder_id,
            drive_poll_sec=float(os.environ.get("CLIPS_DRIVE_POLL_SEC", "120")),
            webhook_url=os.environ.get("CLIPS_WEBHOOK_URL", "").strip() or None,
            public_web_url=os.environ.get("CLIPS_PUBLIC_WEB_URL", "http://127.0.0.1:3040").strip(),
            temp_ttl_days=float(os.environ.get("CLIPS_TEMP_TTL_DAYS", "7.0")),
            fixtures_dir=fix_path,
        )


@lru_cache(maxsize=1)
def get_server_settings() -> ServerSettings:
    load_dotenv()
    return ServerSettings.from_env()
