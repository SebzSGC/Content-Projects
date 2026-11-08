---
titulo: "Edición y exportación de clips en DaVinci Resolve mediante MCP local"
tipo: historia
id: "HU-001"
epica: "EP-01"
estado: vigente
estado_historia: hecho
prioridad: alta
puntos: 8
responsable: "Sebas"
sprint: "Sprint 1"
inicio: "2026-11-07"
fin: "2026-11-07"
progreso: 100
depende_de: []
origen: "[[2026-11-07 Edición externa en DaVinci Resolve vía MCP]]"
audiencia: [negocio, tecnico]
actualizado: 2026-11-07
etiquetas: [tipo/historia, epica/EP-01]
fin_real: 2026-11-07
---

# 📗 HU-001 · Edición y exportación de clips en DaVinci Resolve mediante MCP local

> [!abstract] En pocas palabras
> Permite enviar cualquier clip curado (o sesión completa) de ClipsApp directamente a DaVinci Resolve en el PC local mediante MCP y `DaVinciResolveScript`, construyendo una línea de tiempo vertical 9:16 multipista lista para editar o renderizar y manteniendo disponible la opción de renderizado local con FFmpeg.

## 🙋 Historia
**Como** creador de contenido gaming en ClipsApp
**quiero** trasladar la edición de video de los clips generados hacia DaVinci Resolve mediante MCP de forma local (o alternar con el motor local FFmpeg)
**para** aprovechar las herramientas profesionales de edición no lineal de DaVinci Resolve con las pistas de gameplay, cámara sincronizada, recortes faciales, efectos de sonido y subtítulos ya armados automáticamente.

## ✅ Criterios de aceptación
- [x] **Traducción completa de `EditPlan` v2 a DaVinci Resolve** — Dado un clip con `EditPlan` v2, cuando se invoca el puente MCP de DaVinci Resolve, entonces se construye una línea de tiempo `1080×1920` a `60 fps` con pistas separadas para Gameplay (`V1`), Cámara sincronizada con reencuadre facial (`V2`), Micrófono (`A1`), Audio de juego con ducking (`A2`), efectos de sonido (`A3`), subtítulos `.srt`/`.ass` (`ST1`) y marcadores de IA.
- [x] **Servidor y Cliente MCP Local + Scripting Directo** — Dado que DaVinci Resolve se ejecuta localmente, cuando el usuario o el orquestador envía un clip vía MCP (`auto`, `mcp_stdio`, `mcp_http`, `direct_script` o `bundle_only`), entonces el sistema se comunica mediante JSON-RPC 2.0 MCP / `DaVinciResolveScript` y además genera el paquete local (`.fcpxml`, `.srt`, `.ass`, `resolve_build_timeline.py`, `resolve_mcp_plan.json`).
- [x] **Coexistencia con la opción de edición/renderizado local** — Dado el selector `CLIPS_EDITOR_BACKEND` (`local`, `resolve_mcp`, `both`), cuando el usuario elige `local`, `resolve_mcp` o `both` en `/settings`, entonces el orquestador respeta el flujo elegido sin bloquear el renderizador local FFmpeg ni el Web Studio.
- [x] **Controles en Web Studio y API REST** — Dado un clip en `/editor/[clipId]` o una sesión en `/sessions/[id]`, cuando el usuario pulsa "Editar en DaVinci Resolve (MCP)", entonces la API ejecuta la sincronización MCP y ofrece acceso directo al estado de DaVinci Resolve y a los artefactos del paquete local.

## 💡 Ejemplo
> [!example] Envío de un clip viral a DaVinci Resolve en 1 clic
> Tras procesar una sesión de 30 minutos, Sebas abre el clip #1 (`score 91.5`) en `/editor/[clipId]` y hace clic en **«Editar en DaVinci Resolve (MCP)»**. ClipsApp invoca el servidor MCP local, crea el proyecto `FarmClips - Partida Ranked` en DaVinci Resolve, importa `gameplay.mp4`, `camara.mp4` y `boom.wav`, arma la timeline `clip_01_c01_9x16` con los jump-cuts ya aplicados, aplica el zoom y posición del rostro en `V2`, inserta los subtítulos sincronizados y deja los marcadores del LLM listos para ajustar o exportar.

## 🛠️ Tareas
- [x] Implementar `packages/render-engine/clipsrender/resolve_mcp.py` con compilador FCPXML v1.9 + SRT + script `DaVinciResolveScript`, cliente MCP JSON-RPC 2.0 (`stdio`/`http`) y servidor MCP integrado (`clipsserver resolve-mcp`).
- [x] Agregar configuración `editor_backend` y `resolve_mcp_*` en `apps/server/clipsserver/config.py`, `.env.example` y `orchestrator/engine.py`.
- [x] Exponer endpoints `GET /resolve/status`, `POST /clips/{clip_id}/resolve`, `POST /sessions/{session_id}/resolve` y `GET /clips/{clip_id}/resolve/download/{artifact}` en `apps/server/clipsserver/api/routes.py`.
- [x] Incorporar controles de DaVinci Resolve MCP en `/editor/[clipId]`, `/sessions/[id]` y `/settings` en `apps/web`.
- [x] Añadir pruebas automatizadas en `tests/test_post_mvp_improvements.py` y actualizar la documentación del vault.

## 🔗 Afecta a la documentación
- [[Motor de Renderizado y Subtítulos]]
- [[Motor de Edición Web Studio]]
- [[FastAPI y Orquestador]]
- [[Referencia API REST y SSE]]
- [[Variables de Entorno]]
- [[Comandos CLI y Scripts]]

## 📝 Bitácora
- 2026-11-07 · Creada desde [[2026-11-07 Edición externa en DaVinci Resolve vía MCP]]
- 2026-11-07 · Por hacer → **En progreso** · Iniciando implementación de puente DaVinci Resolve MCP local y paquete FCPXML
- 2026-11-07 · En progreso → **Hecho** · Implementado puente MCP DaVinci Resolve, compilador FCPXML v1.9 + SRT + Py3, endpoints REST y UI en Web Studio (23/23 tests pasando)
- 2026-11-07 · **Optimización y Estabilidad** · Despacho asíncrono no bloqueante (`async_mode: true`), eventos SSE en tiempo real y detección no invasiva de proyecto activo con `GetCurrentProject()`, eliminando cuelgues de IPC y bloqueos del navegador.

## 🔗 Relacionado
- [[Requerimientos]] · [[EP-01 Integración con DaVinci Resolve vía MCP|EP-01]] · [[Tablero de avance]]
