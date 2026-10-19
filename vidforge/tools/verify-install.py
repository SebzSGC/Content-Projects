"""Post-installation and build integrity verifier for VidForge."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path


def generate_manifest(root: Path) -> dict:
    entries = {}
    for sub in ("apps/backend/src", "apps/web/dist", "apps/render-sidecar/src", "packages/contracts", "packages/templates"):
        target = root / sub
        if not target.exists():
            continue
        for f in sorted(target.rglob("*")):
            if f.is_file() and "__pycache__" not in f.parts:
                rel = f.relative_to(root).as_posix()
                entries[rel] = hashlib.sha256(f.read_bytes()).hexdigest()
    manifest = {"schema": "vidforge.manifest/1", "files_count": len(entries), "files": entries}
    (root / "MANIFEST.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def verify_installation(root: Path) -> int:
    mf_path = root / "MANIFEST.json"
    if not mf_path.exists():
        generate_manifest(root)
    manifest = json.loads(mf_path.read_text(encoding="utf-8"))
    for rel, expected_hash in manifest.get("files", {}).items():
        fp = root / rel
        if not fp.exists():
            sys.stderr.write(f"Missing file: {rel}\n")
            return 2
        actual = hashlib.sha256(fp.read_bytes()).hexdigest()
        if actual != expected_hash:
            sys.stderr.write(f"Hash mismatch for {rel}\n")
            return 3
    # Verify core imports
    import vidforge.api.app  # noqa: F401
    print(f"OK: Verified {manifest['files_count']} files and backend imports.")
    return 0


if __name__ == "__main__":
    args = sys.argv[1:]
    generate_flag = "--generate" in args
    filtered = [a for a in args if a != "--generate"]
    root_dir = Path(filtered[0]).resolve() if filtered else Path(__file__).resolve().parents[1]
    if generate_flag:
        generate_manifest(root_dir)
        print(f"Generated manifest for {root_dir}")
    raise SystemExit(verify_installation(root_dir))
