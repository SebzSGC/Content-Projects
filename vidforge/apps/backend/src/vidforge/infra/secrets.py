"""Secure API key vault using Windows Credential Manager + AES-GCM/DPAPI fallback."""

from __future__ import annotations

import json
import os
import sys
import threading
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from vidforge.infra.paths import USERDATA_DIR, ensure_directories

PROVIDERS = ("openai", "elevenlabs", "pexels", "fal", "openrouter", "ollama")


class SecretStore:
    def __init__(self, vault_path: Path | None = None) -> None:
        ensure_directories()
        self._vault_path = vault_path or (USERDATA_DIR / "secrets.v1.bin")
        self._key_path = self._vault_path.with_suffix(".key")
        self._lock = threading.RLock()

    def _get_or_create_master_key(self) -> bytes:
        if self._key_path.exists():
            raw = self._key_path.read_bytes()
            if sys.platform == "win32":
                try:
                    import win32crypt
                    return win32crypt.CryptUnprotectData(raw, None, None, None, 0)[1]
                except Exception:
                    pass
            return raw[:32]
        key = AESGCM.generate_key(bit_length=256)
        if sys.platform == "win32":
            try:
                import win32crypt
                protected = win32crypt.CryptProtectData(key, "VidForge.MasterKey", None, None, None, 0)
                self._key_path.write_bytes(protected)
                return key
            except Exception:
                pass
        self._key_path.write_bytes(key)
        return key

    def _read_vault(self) -> dict[str, str]:
        with self._lock:
            if not self._vault_path.exists():
                return {}
            try:
                blob = self._vault_path.read_bytes()
                nonce, ct = blob[:12], blob[12:]
                aes = AESGCM(self._get_or_create_master_key())
                pt = aes.decrypt(nonce, ct, b"vidforge.secrets.v1")
                return json.loads(pt.decode("utf-8"))
            except Exception:
                return {}

    def _write_vault(self, data: dict[str, str]) -> None:
        with self._lock:
            aes = AESGCM(self._get_or_create_master_key())
            nonce = os.urandom(12)
            pt = json.dumps(data).encode("utf-8")
            ct = aes.encrypt(nonce, pt, b"vidforge.secrets.v1")
            tmp = self._vault_path.with_suffix(".tmp")
            tmp.write_bytes(nonce + ct)
            os.replace(tmp, self._vault_path)

    def set_secret(self, provider: str, secret: str) -> None:
        provider = provider.lower().strip()
        secret = secret.strip()
        try:
            import keyring
            keyring.set_password("VidForge", provider, secret)
        except Exception:
            pass
        vault = self._read_vault()
        vault[provider] = secret
        self._write_vault(vault)

    def delete_secret(self, provider: str) -> None:
        provider = provider.lower().strip()
        try:
            import keyring
            keyring.delete_password("VidForge", provider)
        except Exception:
            pass
        vault = self._read_vault()
        if provider in vault:
            del vault[provider]
            self._write_vault(vault)

    def get_secret(self, provider: str) -> str | None:
        provider = provider.lower().strip()
        env_key = f"VIDFORGE_{provider.upper()}_API_KEY"
        if os.environ.get(env_key):
            return os.environ[env_key]
        vault = self._read_vault()
        if provider in vault and vault[provider]:
            return vault[provider]
        try:
            import keyring
            val = keyring.get_password("VidForge", provider)
            if val:
                return val
        except Exception:
            pass
        return None

    def list_status(self) -> list[dict[str, Any]]:
        out = []
        for p in PROVIDERS:
            val = self.get_secret(p)
            out.append({
                "provider": p,
                "configured": bool(val),
                "last4": val[-4:] if val and len(val) >= 4 else ("****" if val else None),
            })
        return out


secret_store = SecretStore()
