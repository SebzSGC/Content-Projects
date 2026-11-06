"""Google Drive folder connector (Service Account over async httpx + Local Folder mirror for testing).

Follows the exact MVP rules:
- Shared folder layout: `Entradas/<grabación>/gameplay.mp4` + `camara.mp4` -> `Salidas/<grabación>/`.
- Polls periodically; a recording enters ONLY when both files are present AND their sizes stopped changing.
- Streaming download with HTTP Range resumption (`Range: bytes=<offset>-`) in the API pool.
- Uploads MP4 + companion metadata JSON (`post_title`, `hashtags`, `source_ranges`, `score`, `reason`) to `Salidas/<grabación>/`.
- Replaces existing clip file in `Salidas/<grabación>/` when re-rendered from the editor.
"""

from __future__ import annotations

import asyncio
import base64
import json
import shutil
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple

import httpx


@dataclass
class RemoteFileEntry:
    id: str
    name: str
    size: int
    modified_ts: float = 0.0


@dataclass
class ReadyRecording:
    recording_name: str
    folder_id: str
    gameplay_file: RemoteFileEntry
    camera_file: RemoteFileEntry


class DriveConnector(Protocol):
    async def list_ready_recordings(self) -> List[ReadyRecording]: ...
    async def download_resumable(self, entry: RemoteFileEntry, dst: Path) -> Path: ...
    async def upload_clip_bundle(
        self,
        recording_name: str,
        clip_slug: str,
        mp4_path: Path,
        metadata: Dict[str, Any],
    ) -> Dict[str, str]: ...


def _pick_gameplay_and_camera(files: List[RemoteFileEntry]) -> Optional[Tuple[RemoteFileEntry, RemoteFileEntry]]:
    vids = [f for f in files if Path(f.name).suffix.lower() in {".mp4", ".mkv", ".mov", ".webm"} and f.size > 0]
    if len(vids) < 2:
        return None
    gp: Optional[RemoteFileEntry] = None
    cam: Optional[RemoteFileEntry] = None
    for f in vids:
        low = Path(f.name).stem.lower()
        if any(k in low for k in ("gameplay", "game", "juego", "stream")):
            gp = f
        elif any(k in low for k in ("camara", "cámara", "camera", "facecam", "webcam", "cam")):
            cam = f
    if gp and cam and gp.id != cam.id:
        return gp, cam
    # Heuristic fallback: gameplay bitrate/size is typically larger than facecam
    ordered = sorted(vids, key=lambda x: x.size, reverse=True)
    return ordered[0], ordered[1]


class SizeStabilityTracker:
    """Ensures both files exist and their byte size remained unchanged since the previous poll."""

    def __init__(self) -> None:
        self._seen_sizes: Dict[str, Tuple[int, int]] = {}

    def is_stable(self, folder_id: str, gp: RemoteFileEntry, cam: RemoteFileEntry) -> bool:
        sig = (gp.size, cam.size)
        prev = self._seen_sizes.get(folder_id)
        self._seen_sizes[folder_id] = sig
        return prev is not None and prev == sig and gp.size > 0 and cam.size > 0


class LocalFolderDriveConnector:
    """Drop-in local filesystem mirror of `Entradas/<grabación>/` and `Salidas/<grabación>/`."""

    def __init__(self, root_dir: Path, require_two_polls: bool = True) -> None:
        self.root_dir = root_dir.resolve()
        self.entradas = self.root_dir / "Entradas"
        self.salidas = self.root_dir / "Salidas"
        self.entradas.mkdir(parents=True, exist_ok=True)
        self.salidas.mkdir(parents=True, exist_ok=True)
        self.require_two_polls = require_two_polls
        self._stability = SizeStabilityTracker()

    async def list_ready_recordings(self) -> List[ReadyRecording]:
        ready: List[ReadyRecording] = []
        if not self.entradas.exists():
            return ready
        for sub in sorted(p for p in self.entradas.iterdir() if p.is_dir()):
            entries = [
                RemoteFileEntry(
                    id=str(f.resolve()),
                    name=f.name,
                    size=f.stat().st_size,
                    modified_ts=f.stat().st_mtime,
                )
                for f in sub.iterdir()
                if f.is_file()
            ]
            pair = _pick_gameplay_and_camera(entries)
            if not pair:
                continue
            gp, cam = pair
            stable = self._stability.is_stable(str(sub), gp, cam)
            if stable or not self.require_two_polls:
                ready.append(
                    ReadyRecording(
                        recording_name=sub.name,
                        folder_id=str(sub.resolve()),
                        gameplay_file=gp,
                        camera_file=cam,
                    )
                )
        return ready

    async def download_resumable(self, entry: RemoteFileEntry, dst: Path) -> Path:
        dst.parent.mkdir(parents=True, exist_ok=True)
        src = Path(entry.id)
        part = dst.with_suffix(dst.suffix + ".part")
        offset = part.stat().st_size if part.exists() else 0
        with src.open("rb") as rfh:
            rfh.seek(offset)
            mode = "ab" if offset > 0 else "wb"
            with part.open(mode) as wfh:
                while True:
                    chunk = rfh.read(1024 * 1024)
                    if not chunk:
                        break
                    wfh.write(chunk)
        part.replace(dst)
        return dst

    async def upload_clip_bundle(
        self,
        recording_name: str,
        clip_slug: str,
        mp4_path: Path,
        metadata: Dict[str, Any],
    ) -> Dict[str, str]:
        out_dir = self.salidas / recording_name
        out_dir.mkdir(parents=True, exist_ok=True)
        mp4_dst = out_dir / f"{clip_slug}.mp4"
        json_dst = out_dir / f"{clip_slug}.json"
        json_text = json.dumps(metadata, ensure_ascii=False, indent=2) + "\n"
        await asyncio.gather(
            asyncio.to_thread(shutil.copy2, mp4_path, mp4_dst),
            asyncio.to_thread(json_dst.write_text, json_text, "utf-8"),
        )
        return {"mp4": str(mp4_dst), "json": str(json_dst)}


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


class GoogleDriveServiceAccountConnector:
    """Google Drive v3 connector authenticated via Service Account JSON over async httpx (zero heavy SDKs)."""

    DRIVE_API = "https://www.googleapis.com/drive/v3"
    UPLOAD_API = "https://www.googleapis.com/upload/drive/v3"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    SCOPE = "https://www.googleapis.com/auth/drive"

    def __init__(self, service_account_json: Path, root_folder_id: str) -> None:
        raw = json.loads(service_account_json.read_text(encoding="utf-8"))
        self.client_email: str = raw["client_email"]
        self.private_key_pem: bytes = raw["private_key"].encode("utf-8")
        self.token_uri: str = raw.get("token_uri", self.TOKEN_URL)
        self.root_folder_id = root_folder_id
        self._access_token: Optional[str] = None
        self._token_exp: float = 0.0
        self._stability = SizeStabilityTracker()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0))

    def _sign_jwt(self) -> str:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import padding

        now = int(time.time())
        header = _b64url(json.dumps({"alg": "RS256", "typ": "JWT"}).encode("utf-8"))
        claims = _b64url(
            json.dumps(
                {
                    "iss": self.client_email,
                    "scope": self.SCOPE,
                    "aud": self.token_uri,
                    "iat": now,
                    "exp": now + 3600,
                }
            ).encode("utf-8")
        )
        signing_input = f"{header}.{claims}".encode("ascii")
        private_key = serialization.load_pem_private_key(self.private_key_pem, password=None)
        signature = private_key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())  # type: ignore[union-attr]
        return f"{header}.{claims}.{_b64url(signature)}"

    async def _token(self) -> str:
        if self._access_token and time.time() < self._token_exp - 60:
            return self._access_token
        assertion = self._sign_jwt()
        res = await self._client.post(
            self.token_uri,
            data={"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion},
        )
        res.raise_for_status()
        data = res.json()
        self._access_token = data["access_token"]
        self._token_exp = time.time() + float(data.get("expires_in", 3600))
        return self._access_token

    async def _headers(self, extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        h = {"Authorization": f"Bearer {await self._token()}"}
        if extra:
            h.update(extra)
        return h

    async def _list_children(self, parent_id: str, folders_only: bool = False) -> List[Dict[str, Any]]:
        mime_clause = " and mimeType = 'application/vnd.google-apps.folder'" if folders_only else ""
        q = f"'{parent_id}' in parents and trashed = false{mime_clause}"
        res = await self._client.get(
            f"{self.DRIVE_API}/files",
            headers=await self._headers(),
            params={"q": q, "fields": "files(id,name,size,mimeType,modifiedTime)", "pageSize": 200},
        )
        res.raise_for_status()
        return res.json().get("files", [])

    async def _ensure_subfolder(self, parent_id: str, name: str) -> str:
        existing = await self._list_children(parent_id, folders_only=True)
        for f in existing:
            if f["name"].lower() == name.lower():
                return f["id"]
        res = await self._client.post(
            f"{self.DRIVE_API}/files",
            headers=await self._headers({"Content-Type": "application/json"}),
            json={"name": name, "mimeType": "application/vnd.google-apps.folder", "parents": [parent_id]},
        )
        res.raise_for_status()
        return res.json()["id"]

    async def list_ready_recordings(self) -> List[ReadyRecording]:
        entradas_id = await self._ensure_subfolder(self.root_folder_id, "Entradas")
        rec_folders = await self._list_children(entradas_id, folders_only=True)
        ready: List[ReadyRecording] = []
        for rf in rec_folders:
            children = await self._list_children(rf["id"], folders_only=False)
            entries = [
                RemoteFileEntry(id=c["id"], name=c["name"], size=int(c.get("size") or 0))
                for c in children
                if c.get("mimeType") != "application/vnd.google-apps.folder"
            ]
            pair = _pick_gameplay_and_camera(entries)
            if not pair:
                continue
            gp, cam = pair
            if self._stability.is_stable(rf["id"], gp, cam):
                ready.append(
                    ReadyRecording(
                        recording_name=rf["name"],
                        folder_id=rf["id"],
                        gameplay_file=gp,
                        camera_file=cam,
                    )
                )
        return ready

    async def download_resumable(self, entry: RemoteFileEntry, dst: Path) -> Path:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.is_file() and dst.stat().st_size == entry.size and entry.size > 0:
            return dst
        part = dst.with_suffix(dst.suffix + ".part")
        offset = part.stat().st_size if part.is_file() else 0
        extra = {"Range": f"bytes={offset}-"} if offset > 0 else {}
        url = f"{self.DRIVE_API}/files/{entry.id}?alt=media"
        async with self._client.stream("GET", url, headers=await self._headers(extra)) as resp:
            if resp.status_code == 416:  # Already complete
                part.replace(dst)
                return dst
            resp.raise_for_status()
            mode = "ab" if (offset > 0 and resp.status_code == 206) else "wb"
            with part.open(mode) as fh:
                async for chunk in resp.aiter_bytes(chunk_size=1024 * 512):
                    fh.write(chunk)
        part.replace(dst)
        return dst

    async def _put_resumable_chunks(self, upload_url: str, content: bytes, mime_type: str, chunk_bytes: int = 8 * 1024 * 1024) -> Dict[str, Any]:
        total = len(content)
        if total == 0:
            res = await self._client.put(upload_url, headers={"Content-Type": mime_type, "Content-Length": "0"}, content=b"")
            res.raise_for_status()
            return res.json()

        offset = 0
        while offset < total:
            end = min(total, offset + chunk_bytes)
            chunk = content[offset:end]
            headers = {
                "Content-Type": mime_type,
                "Content-Length": str(len(chunk)),
                "Content-Range": f"bytes {offset}-{end - 1}/{total}",
            }
            put_res = await self._client.put(upload_url, headers=headers, content=chunk)
            if put_res.status_code in (200, 201):
                return put_res.json()
            if put_res.status_code == 308:
                rng = put_res.headers.get("Range", "")
                if "-" in rng:
                    offset = int(rng.split("-", 1)[1]) + 1
                else:
                    offset = end
                continue
            put_res.raise_for_status()
            offset = end
        return {"id": ""}

    async def _upsert_file(
        self,
        folder_id: str,
        filename: str,
        content: bytes,
        mime_type: str,
        existing_children: Optional[List[Dict[str, Any]]] = None,
    ) -> str:
        children = existing_children if existing_children is not None else await self._list_children(folder_id, folders_only=False)
        existing_id = next((c["id"] for c in children if c["name"] == filename), None)

        if existing_id:
            if len(content) < 256 * 1024:
                res = await self._client.patch(
                    f"{self.UPLOAD_API}/files/{existing_id}?uploadType=media",
                    headers=await self._headers({"Content-Type": mime_type}),
                    content=content,
                )
                res.raise_for_status()
                return existing_id
            # Resumable replacement session for large MP4 re-renders
            init_res = await self._client.patch(
                f"{self.UPLOAD_API}/files/{existing_id}?uploadType=resumable",
                headers=await self._headers(
                    {
                        "Content-Type": "application/json; charset=UTF-8",
                        "X-Upload-Content-Type": mime_type,
                        "X-Upload-Content-Length": str(len(content)),
                    }
                ),
                json={"name": filename},
            )
            init_res.raise_for_status()
            upload_url = init_res.headers["Location"]
            await self._put_resumable_chunks(upload_url, content, mime_type)
            return existing_id

        # Resumable upload initiation for new files (chunked Content-Range safe for large 1080p MP4s)
        init_res = await self._client.post(
            f"{self.UPLOAD_API}/files?uploadType=resumable",
            headers=await self._headers(
                {
                    "Content-Type": "application/json; charset=UTF-8",
                    "X-Upload-Content-Type": mime_type,
                    "X-Upload-Content-Length": str(len(content)),
                }
            ),
            json={"name": filename, "parents": [folder_id]},
        )
        init_res.raise_for_status()
        upload_url = init_res.headers["Location"]
        uploaded = await self._put_resumable_chunks(upload_url, content, mime_type)
        return str(uploaded.get("id") or "")

    async def upload_clip_bundle(
        self,
        recording_name: str,
        clip_slug: str,
        mp4_path: Path,
        metadata: Dict[str, Any],
    ) -> Dict[str, str]:
        salidas_id = await self._ensure_subfolder(self.root_folder_id, "Salidas")
        rec_out_id = await self._ensure_subfolder(salidas_id, recording_name)
        children = await self._list_children(rec_out_id, folders_only=False)
        mp4_bytes = await asyncio.to_thread(mp4_path.read_bytes)
        json_bytes = (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        mp4_id, json_id = await asyncio.gather(
            self._upsert_file(rec_out_id, f"{clip_slug}.mp4", mp4_bytes, "video/mp4", existing_children=children),
            self._upsert_file(rec_out_id, f"{clip_slug}.json", json_bytes, "application/json", existing_children=children),
        )
        return {"mp4": mp4_id, "json": json_id}

    async def aclose(self) -> None:
        await self._client.aclose()
