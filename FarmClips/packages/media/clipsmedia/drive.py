"""Google Drive folder connector (OAuth 2.0 + Service Account over async httpx + Local Folder mirror).

Follows the exact MVP & interactive studio rules:
- Shared folder layout: `Entradas/<grabación>/gameplay.mp4` + `camara.mp4` -> `Salidas/<grabación>/`.
- Direct OAuth 2.0 connection with persisted `refresh_token` in `data/drive_oauth_token.json`.
- Interactive folder & video explorer (`browse_folder`) with breadcrumbs and automatic pair detection (`_pick_gameplay_and_camera`).
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
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Protocol, Tuple
from urllib.parse import urlencode

import httpx

VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".webm"}


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
    async def browse_folder(
        self,
        folder_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]: ...
    async def get_file_entry(self, file_id: str) -> RemoteFileEntry: ...


def _infer_role_hint(filename: str) -> Optional[str]:
    low = Path(filename).stem.lower()
    if any(k in low for k in ("gameplay", "juego", "pantalla")):
        return "gameplay"
    if any(k in low for k in ("camara", "cámara", "camera", "facecam", "webcam", "cam")):
        return "camera"
    if any(k in low for k in ("game", "stream")):
        return "gameplay"
    return None


def _is_video_entry(filename: str, mime_type: Optional[str] = None) -> bool:
    if Path(filename).suffix.lower() in VIDEO_EXTENSIONS:
        return True
    if mime_type and mime_type.lower().startswith("video/"):
        return True
    return False


def _parse_iso_ts(raw_iso: Optional[str]) -> float:
    if not raw_iso:
        return 0.0
    try:
        s = raw_iso.strip()
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        return datetime.fromisoformat(s).timestamp()
    except Exception:
        return 0.0


def _pick_gameplay_and_camera(files: List[RemoteFileEntry]) -> Optional[Tuple[RemoteFileEntry, RemoteFileEntry]]:
    vids = [f for f in files if Path(f.name).suffix.lower() in VIDEO_EXTENSIONS and f.size > 0]
    if len(vids) < 2:
        return None
    gp: Optional[RemoteFileEntry] = None
    cam: Optional[RemoteFileEntry] = None
    for f in vids:
        hint = _infer_role_hint(f.name)
        if hint == "gameplay" and gp is None:
            gp = f
        elif hint == "camera" and cam is None:
            cam = f
    if gp and cam and gp.id != cam.id:
        return gp, cam
    # Heuristic fallback: gameplay bitrate/size is typically larger than facecam
    ordered = sorted(vids, key=lambda x: x.size, reverse=True)
    return ordered[0], ordered[1]


def _build_pair_and_roles(
    folder_name: str,
    entries: List[RemoteFileEntry],
) -> Tuple[Optional[Dict[str, Any]], Dict[str, str]]:
    role_by_id: Dict[str, str] = {}
    for e in entries:
        hint = _infer_role_hint(e.name)
        if hint:
            role_by_id[e.id] = hint

    pair = _pick_gameplay_and_camera(entries)
    if not pair:
        return None, role_by_id

    gp, cam = pair
    role_by_id[gp.id] = "gameplay"
    role_by_id[cam.id] = "camera"
    detected_pair = {
        "recording_name": folder_name,
        "gameplay": {
            "id": gp.id,
            "name": gp.name,
            "size": gp.size,
            "modified_ts": gp.modified_ts,
            "role_hint": "gameplay",
        },
        "camera": {
            "id": cam.id,
            "name": cam.name,
            "size": cam.size,
            "modified_ts": cam.modified_ts,
            "role_hint": "camera",
        },
    }
    return detected_pair, role_by_id


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

    def _resolve_local_dir(self, folder_id: Optional[str]) -> Path:
        raw = (folder_id or "").strip()
        if not raw or raw == "root":
            return self.root_dir
        cand = Path(raw)
        if not cand.is_absolute():
            cand = self.root_dir / cand
        resolved = cand.resolve()
        try:
            resolved.relative_to(self.root_dir)
        except ValueError as exc:
            raise ValueError(f"Ruta fuera del espejo local de Drive: {folder_id}") from exc
        if not resolved.is_dir():
            raise FileNotFoundError(f"Carpeta no encontrada en espejo local de Drive: {folder_id}")
        return resolved

    async def browse_folder(
        self,
        folder_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        target = self._resolve_local_dir(folder_id)
        q_norm = (query or "").strip().lower()

        breadcrumbs: List[Dict[str, str]] = [{"id": str(self.root_dir), "name": "Raíz local"}]
        if target != self.root_dir:
            rel_parts = target.relative_to(self.root_dir).parts
            accum = self.root_dir
            for part in rel_parts:
                accum = (accum / part).resolve()
                breadcrumbs.append({"id": str(accum), "name": part})

        parent_id = str(target.parent.resolve()) if target != self.root_dir else None
        folder_name = "Raíz local" if target == self.root_dir else target.name

        if q_norm:
            matched_dirs = sorted(
                (p for p in target.rglob("*") if p.is_dir() and q_norm in p.name.lower()),
                key=lambda x: x.name.lower(),
            )
            matched_files = sorted(
                (
                    p
                    for p in target.rglob("*")
                    if p.is_file() and _is_video_entry(p.name) and q_norm in p.name.lower()
                ),
                key=lambda x: x.name.lower(),
            )
        else:
            matched_dirs = sorted((p for p in target.iterdir() if p.is_dir()), key=lambda x: x.name.lower())
            matched_files = sorted(
                (p for p in target.iterdir() if p.is_file() and _is_video_entry(p.name)),
                key=lambda x: x.name.lower(),
            )

        folders = [
            {
                "id": str(d.resolve()),
                "name": d.name,
                "modified_ts": round(d.stat().st_mtime, 3),
            }
            for d in matched_dirs
        ]

        entries = [
            RemoteFileEntry(
                id=str(f.resolve()),
                name=f.name,
                size=f.stat().st_size,
                modified_ts=round(f.stat().st_mtime, 3),
            )
            for f in matched_files
        ]
        detected_pair, role_by_id = _build_pair_and_roles(folder_name, entries)

        files = [
            {
                "id": e.id,
                "name": e.name,
                "size": e.size,
                "mime_type": f"video/{Path(e.name).suffix.lstrip('.').lower() or 'mp4'}",
                "modified_ts": e.modified_ts,
                "role_hint": role_by_id.get(e.id),
            }
            for e in entries
        ]

        return {
            "folder_id": str(target),
            "folder_name": folder_name,
            "parent_id": parent_id,
            "breadcrumbs": breadcrumbs,
            "folders": folders,
            "files": files,
            "detected_pair": detected_pair,
        }

    async def get_file_entry(self, file_id: str) -> RemoteFileEntry:
        cand = Path(file_id).expanduser()
        if not cand.is_absolute():
            cand = self.root_dir / cand
        resolved = cand.resolve()
        try:
            resolved.relative_to(self.root_dir)
        except ValueError as exc:
            raise ValueError(f"Archivo fuera del espejo local de Drive: {file_id}") from exc
        if not resolved.is_file():
            raise FileNotFoundError(f"Archivo no encontrado en Drive local: {file_id}")
        st = resolved.stat()
        return RemoteFileEntry(
            id=str(resolved),
            name=resolved.name,
            size=st.st_size,
            modified_ts=round(st.st_mtime, 3),
        )


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

    async def _fetch_folder_meta_safe(self, folder_id: str) -> Optional[Dict[str, Any]]:
        try:
            res = await self._client.get(
                f"{self.DRIVE_API}/files/{folder_id}",
                headers=await self._headers(),
                params={"fields": "id,name,parents,mimeType"},
            )
            if res.status_code != 200:
                return None
            data = res.json()
            if isinstance(data, dict) and data.get("id") and data.get("name"):
                return data
        except Exception:
            pass
        return None

    async def _resolve_breadcrumbs(
        self,
        target_id: str,
        root_id: str,
    ) -> Tuple[List[Dict[str, str]], str, Optional[str]]:
        root_label = "Mi unidad" if root_id == "root" else "Raíz Drive"
        if target_id == root_id:
            return [{"id": root_id, "name": root_label}], root_label, None

        chain: List[Dict[str, str]] = []
        parent_id: Optional[str] = None
        curr_id: Optional[str] = target_id
        visited = set()

        for hop in range(5):
            if not curr_id or curr_id in visited:
                break
            visited.add(curr_id)
            if curr_id == root_id or curr_id == "root":
                chain.append({"id": root_id, "name": root_label})
                break
            meta = await self._fetch_folder_meta_safe(curr_id)
            if not meta:
                if hop == 0:
                    chain.append({"id": target_id, "name": target_id})
                    parent_id = root_id
                break
            chain.append({"id": str(meta["id"]), "name": str(meta["name"])})
            parents = meta.get("parents") or []
            next_parent = str(parents[0]) if parents else None
            if hop == 0:
                parent_id = next_parent or root_id
            curr_id = next_parent

        chain.reverse()
        if not chain or chain[0]["id"] != root_id:
            chain.insert(0, {"id": root_id, "name": root_label})
        folder_name = chain[-1]["name"] if chain else target_id
        return chain, folder_name, parent_id

    async def browse_folder(
        self,
        folder_id: Optional[str] = None,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        root_id = (self.root_folder_id or "root").strip() or "root"
        target_id = (folder_id or "").strip() or root_id
        breadcrumbs, folder_name, parent_id = await self._resolve_breadcrumbs(target_id, root_id)

        q_clean = (query or "").strip()
        if q_clean:
            safe_q = q_clean.replace("\\", "\\\\").replace("'", "\\'")
            if folder_id and target_id not in ("root", root_id):
                q_str = f"'{target_id}' in parents and name contains '{safe_q}' and trashed = false"
            else:
                q_str = f"name contains '{safe_q}' and trashed = false"
        else:
            q_str = f"'{target_id}' in parents and trashed = false"

        res = await self._client.get(
            f"{self.DRIVE_API}/files",
            headers=await self._headers(),
            params={
                "q": q_str,
                "fields": "files(id,name,size,mimeType,modifiedTime,parents)",
                "pageSize": 200,
            },
        )
        res.raise_for_status()
        items = res.json().get("files", [])

        folders: List[Dict[str, Any]] = []
        video_items: List[Dict[str, Any]] = []
        entries: List[RemoteFileEntry] = []

        for c in items:
            cid = str(c.get("id") or "")
            cname = str(c.get("name") or "")
            cmime = str(c.get("mimeType") or "")
            mod_ts = _parse_iso_ts(c.get("modifiedTime"))
            if not cid or not cname:
                continue
            if cmime == "application/vnd.google-apps.folder":
                folders.append({"id": cid, "name": cname, "modified_ts": mod_ts})
            elif _is_video_entry(cname, cmime):
                csize = int(c.get("size") or 0)
                video_items.append(
                    {
                        "id": cid,
                        "name": cname,
                        "size": csize,
                        "mime_type": cmime or "video/mp4",
                        "modified_ts": mod_ts,
                    }
                )
                entries.append(RemoteFileEntry(id=cid, name=cname, size=csize, modified_ts=mod_ts))

        folders.sort(key=lambda x: x["name"].lower())
        video_items.sort(key=lambda x: x["name"].lower())
        entries.sort(key=lambda x: x.name.lower())

        detected_pair, role_by_id = _build_pair_and_roles(folder_name, entries)
        files = [{**v, "role_hint": role_by_id.get(v["id"])} for v in video_items]

        return {
            "folder_id": target_id,
            "folder_name": folder_name,
            "parent_id": parent_id,
            "breadcrumbs": breadcrumbs,
            "folders": folders,
            "files": files,
            "detected_pair": detected_pair,
        }

    async def get_file_entry(self, file_id: str) -> RemoteFileEntry:
        res = await self._client.get(
            f"{self.DRIVE_API}/files/{file_id}",
            headers=await self._headers(),
            params={"fields": "id,name,size,mimeType,modifiedTime"},
        )
        res.raise_for_status()
        data = res.json()
        return RemoteFileEntry(
            id=str(data.get("id") or file_id),
            name=str(data.get("name") or f"{file_id}.mp4"),
            size=int(data.get("size") or 0),
            modified_ts=_parse_iso_ts(data.get("modifiedTime")),
        )

    async def aclose(self) -> None:
        await self._client.aclose()


class GoogleDriveOAuthConnector(GoogleDriveServiceAccountConnector):
    """Google Drive v3 connector authenticated via OAuth 2.0 with `refresh_token` persisted in `data/drive_oauth_token.json`."""

    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        token_path: Path = Path("data/drive_oauth_token.json"),
        root_folder_id: Optional[str] = "root",
        token_uri: str = TOKEN_URL,
    ) -> None:
        self.client_id = (client_id or "").strip()
        self.client_secret = (client_secret or "").strip()
        self.token_path = Path(token_path).expanduser().resolve()
        self.token_uri = token_uri
        self.root_folder_id = (root_folder_id or "root").strip() or "root"
        self._access_token: Optional[str] = None
        self._refresh_token: Optional[str] = None
        self._token_exp: float = 0.0
        self.user_email: Optional[str] = None
        self.user_name: Optional[str] = None
        self._stability = SizeStabilityTracker()
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=300.0))
        self._load_token_from_disk()

    def _load_token_from_disk(self) -> bool:
        if not self.token_path.is_file():
            return False
        try:
            raw = json.loads(self.token_path.read_text(encoding="utf-8"))
            self._access_token = (raw.get("access_token") or "").strip() or None
            self._refresh_token = (raw.get("refresh_token") or "").strip() or None
            self._token_exp = float(raw.get("expires_at") or 0.0)
            self.user_email = (raw.get("user_email") or "").strip() or None
            self.user_name = (raw.get("user_name") or "").strip() or None
            if raw.get("token_uri"):
                self.token_uri = str(raw["token_uri"])
            return bool(self._refresh_token or self._access_token)
        except Exception:
            return False

    def _save_token_to_disk(self) -> Dict[str, Any]:
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        payload: Dict[str, Any] = {
            "access_token": self._access_token or "",
            "refresh_token": self._refresh_token or "",
            "token_uri": self.token_uri,
            "expires_at": round(self._token_exp, 3),
            "scope": self.SCOPE,
            "token_type": "Bearer",
            "user_email": self.user_email,
            "user_name": self.user_name,
            "updated_at": round(time.time(), 3),
        }
        self.token_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return payload

    def is_connected(self) -> bool:
        if not self._refresh_token and not self._access_token and self.token_path.is_file():
            self._load_token_from_disk()
        return bool(self._refresh_token or (self._access_token and time.time() < self._token_exp))

    def build_auth_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        params: Dict[str, str] = {
            "client_id": self.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": self.SCOPE,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        if state:
            params["state"] = state
        return f"{self.AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, redirect_uri: str) -> Dict[str, Any]:
        if not self.client_id or not self.client_secret:
            raise ValueError("Faltan CLIPS_DRIVE_CLIENT_ID o CLIPS_DRIVE_CLIENT_SECRET para intercambiar el código OAuth.")
        res = await self._client.post(
            self.token_uri,
            data={
                "code": code.strip(),
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "redirect_uri": redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        res.raise_for_status()
        data = res.json()
        self._access_token = data["access_token"]
        if data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]
        elif not self._refresh_token and self.token_path.is_file():
            try:
                old = json.loads(self.token_path.read_text(encoding="utf-8"))
                self._refresh_token = old.get("refresh_token") or None
            except Exception:
                pass
        self._token_exp = time.time() + float(data.get("expires_in", 3600))

        # Best-effort user identity fetch from Drive v3 /about
        try:
            about_res = await self._client.get(
                f"{self.DRIVE_API}/about",
                headers={"Authorization": f"Bearer {self._access_token}"},
                params={"fields": "user(displayName,emailAddress)"},
            )
            if about_res.status_code == 200:
                u = about_res.json().get("user") or {}
                self.user_email = u.get("emailAddress") or self.user_email
                self.user_name = u.get("displayName") or self.user_name
        except Exception:
            pass

        return self._save_token_to_disk()

    async def _token(self) -> str:
        if not self._refresh_token and not self._access_token and self.token_path.is_file():
            self._load_token_from_disk()
        if self._access_token and time.time() < self._token_exp - 60:
            return self._access_token
        if not self._refresh_token:
            if self._access_token:
                return self._access_token
            raise RuntimeError("Google Drive OAuth 2.0 no está conectado (falta refresh_token en drive_oauth_token.json).")
        res = await self._client.post(
            self.token_uri,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "refresh_token": self._refresh_token,
                "grant_type": "refresh_token",
            },
        )
        res.raise_for_status()
        data = res.json()
        self._access_token = data["access_token"]
        if data.get("refresh_token"):
            self._refresh_token = data["refresh_token"]
        self._token_exp = time.time() + float(data.get("expires_in", 3600))
        self._save_token_to_disk()
        return self._access_token

    async def disconnect(self) -> None:
        self._access_token = None
        self._refresh_token = None
        self._token_exp = 0.0
        self.user_email = None
        self.user_name = None
        self.token_path.unlink(missing_ok=True)
