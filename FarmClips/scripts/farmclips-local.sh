#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
case "${1:-}" in
  server)
    packages="apps/server"
    for package in packages/*; do packages="$packages:$package"; done
    export PYTHONPATH="$packages${FARMCLIPS_DEV_SITE_PACKAGES:+:$FARMCLIPS_DEV_SITE_PACKAGES}"
    export CLIPS_DRIVE_MODE=disabled
    export CLIPS_HOST=127.0.0.1
    export CLIPS_DATA_DIR="${CLIPS_DATA_DIR:-$PWD/.venv/local-data}"
    exec "${FARMCLIPS_DEV_PYTHON:-.venv/bin/python}" -m clipsserver.main serve
    ;;
  web)
    exec npm --prefix apps/web run dev -- --hostname 127.0.0.1
    ;;
  *)
    printf 'Uso: %s server|web\n' "$0" >&2
    exit 2
    ;;
esac
