---
id: HU-009
titulo: Servidor farmclips-mcp y mcp-config
tipo: historia
epica: EP-03
estado: hecho
audiencia: [desarrolladores, creadores]
responsable: Equipo FarmClips
prioridad: alta
estimacion: M
avance: 100
fecha_inicio: 2026-11-12
fecha_fin: 2026-11-12
origen: "[[2026-11-12 Plan de integracion FilmCraft y copiloto MCP]]"
afecta:
  - "[[ADR-006 Integración con FilmCraft y copiloto MCP]]"
  - "[[Comandos CLI y Scripts]]"
actualizado: 2026-11-12
etiquetas: [requerimientos, historia, area/backend, mcp]
estado_historia: hecho
inicio: 2026-11-12
fin: 2026-11-12
progreso: 100
---

# 📗 HU-009 — Servidor farmclips-mcp y comando mcp-config

> [!abstract] En pocas palabras
> Servidor MCP en Python por stdio (`python -m clipsserver.mcp`) que expone herramientas semánticas y de control sobre sesiones y clips a Claude Desktop y otros clientes MCP, más comando generador de configuración.

> [!info] Historia de usuario
> **Como** usuario con Claude Desktop o Antigravity,
> **quiero** conectar un servidor MCP de FarmClips,
> **para** que el asistente de IA pueda consultar mis sesiones, leer la transcripción, actualizar encuadres de forma segura y ejecutar acciones.

## ✅ Criterios de aceptación
- [x] Servidor stdio operativo con herramientas: `list_sessions`, `list_clips`, `get_clip`, `get_transcript`, `update_editplan`, `export_to_filmcraft`, `open_in_filmcraft`, `render_clip`, `get_render_status`.
- [x] `update_editplan` valida los planes estrictamente con Pydantic y notifica cambios en tiempo real vía SSE a la interfaz web.
- [x] Comando `python -m clipsserver.main mcp-config` que genera el bloque JSON para `claude_desktop_config.json` con rutas absolutas detectadas en el sistema.

## 🛠️ Tareas técnicas
- [x] Módulo `clipsserver.mcp` con `MCPServer` del SDK oficial de MCP.
- [x] Implementación de clientes HTTP locales contra `127.0.0.1:8790`.
- [x] Comando `mcp-config` en `clipsserver/main.py`.
- [x] Pruebas unitarias en `tests/test_mcp_server.py`.

---

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[ADR-006 Integración con FilmCraft y copiloto MCP]]
- [[HU-010 Copiloto en Claude Desktop y Antigravity]]
