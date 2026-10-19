@echo off
title VidForge Studio Launcher
set "VIDFORGE_ROOT=%~dp0"
"%~dp0runtime\venv\Scripts\pythonw.exe" "%~dp0apps\launcher\main.py" %*
