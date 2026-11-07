---
titulo: "Integración con DaVinci Resolve vía MCP"
tipo: epica
id: "EP-01"
estado: vigente
responsable: "Sebas"
progreso: 100
audiencia: [negocio, tecnico]
actualizado: "2026-11-07"
etiquetas: [tipo/epica]
---

# 🧩 EP-01 · Integración con DaVinci Resolve vía MCP

> [!abstract] En pocas palabras
> Permitir que ClipsApp traslade la edición de video de cada `EditPlan` v2 hacia DaVinci Resolve en la máquina local mediante un puente MCP (Model Context Protocol), API local `DaVinciResolveScript` y paquete FCPXML multipista, coexistiendo con el renderizador local FFmpeg.

## 🎯 Objetivo
Desacoplar la edición final del video para que el creador pueda abrir, perfeccionar o renderizar sus Shorts verticales 9:16 (`1080×1920`, 60 fps) directamente dentro de DaVinci Resolve (Free o Studio) sin perder los cortes de silencios, la sincronización de cámara/gameplay, el reencuadre facial de MediaPipe, los efectos de sonido ni los subtítulos estilo Hormozi.

## 📦 Alcance
- **Incluye:**
  - Servidor y cliente MCP JSON-RPC 2.0 (`clipsrender.resolve_mcp` y comando `clipsserver resolve-mcp`).
  - Integración directa con la API local `DaVinciResolveScript` (`fusionscript.dll` / módulos de Blackmagic Design).
  - Generación de paquete local auto-contenido (`.fcpxml` v1.9 multipista V1/V2/A1/A2/A3, `.srt`, `.ass`, `resolve_build_timeline.py` y manifiesto MCP).
  - Endpoints REST (`GET /resolve/status`, `POST /clips/{clip_id}/resolve`, `POST /sessions/{session_id}/resolve`, descarga de artefactos) y controles en Web Studio (`/editor/[clipId]`, `/sessions/[id]` y `/settings`).
- **No incluye:**
  - Ejecución de DaVinci Resolve en servidores remotos en la nube (opera 100 % en la estación de trabajo local).

## 📋 Historias y requerimientos
- [[HU-001 Edición y exportación de clips en DaVinci Resolve mediante MCP local|HU-001]] — Edición y exportación de clips en DaVinci Resolve mediante MCP local

## 🔗 Relacionado
- [[Requerimientos]] · [[Tablero de avance]]
