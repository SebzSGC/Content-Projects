#!/usr/bin/env python3
"""Lanzador local del dashboard para FarmClips."""
import json
import os
import subprocess
import sys
from pathlib import Path

GLOBAL = Path.home() / ".obsidian-docs.json"
plugin_path = None
if GLOBAL.is_file():
    try:
        cfg = json.loads(GLOBAL.read_text(encoding="utf-8-sig"))
        plugin_path = cfg.get("pluginObsidianDocs")
    except Exception:
        pass

if not plugin_path:
    plugin_path = "C:/Users/sebas/OneDrive/Documentos/personal-config-IA/plugins/obsidian-docs"

script = Path(plugin_path) / "skills" / "dashboard-documentacion" / "scripts" / "generar_dashboard.py"
if not script.is_file():
    print(f"❌ No se encontró el script en {script}")
    sys.exit(1)

cmd = [sys.executable, str(script), "--abrir", *sys.argv[1:]]
sys.exit(subprocess.run(cmd).returncode)
