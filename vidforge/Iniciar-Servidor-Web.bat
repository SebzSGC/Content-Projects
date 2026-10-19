@echo off
title VidForge Studio Server (http://127.0.0.1:8765)
set "VIDFORGE_ROOT=%~dp0"
echo Iniciando VidForge Studio en http://127.0.0.1:8765 ...
start "" "http://127.0.0.1:8765"
"%~dp0runtime\venv\Scripts\python.exe" "%~dp0apps\launcher\main.py" --server-only --port 8765
