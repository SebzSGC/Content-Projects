---
id: HU-013
titulo: Selección de cantidad de clips a extraer por sesión
tipo: historia
epica: EP-02
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
prioridad: alta
estimacion: M
avance: 0
fecha_inicio: 2026-11-13
fecha_fin: 2026-11-13
origen: "[[2026-11-13 Selector de cantidad de clips por sesión]]"
afecta:
  - "[[Motor de Edición Web Studio]]"
  - "[[FastAPI y Orquestador]]"
actualizado: 2026-11-13
etiquetas: [requerimientos, historia, area/frontend, area/backend]
estado_historia: hecho
inicio: 2026-11-13
fin: 2026-11-13
progreso: 100
fin_real: 2026-11-13
---

# 📗 HU-013 — Selección de cantidad de clips a extraer por sesión

> [!abstract] En pocas palabras
> Permite al creador elegir exactamente cuántos clips (entre `1` y `20`) quiere obtener de cada partida al crear la sesión, al reprocesarla o como valor predeterminado en Ajustes.

> [!info] Historia de usuario
> **Como** creador de contenido en FarmClips,
> **quiero** elegir cuántos clips extraer de mi grabación antes de procesarla (o al reprocesar una sesión existente),
> **para** obtener justo la cantidad de Shorts que necesito según la duración de mi partida y controlar mejor el tiempo de renderizado.

## ✅ Criterios de aceptación
- [x] **Dado** el formulario de creación de sesión en `/sessions` (modos PC, Subir archivos y Google Drive), **cuando** el usuario selecciona o escribe una cantidad de clips entre `1` y `20`, **entonces** el servidor guarda `max_clips` en la sesión y el orquestador solicita y entrega como máximo esa cantidad de clips.
- [x] **Dado** el detalle de una sesión existente en `/sessions/[id]`, **cuando** el usuario cambia la cantidad de clips y pulsa **«Reprocesar gratis»**, **entonces** `POST /sessions/{id}/run` actualiza `max_clips` y regenera los clips respetando el nuevo límite sin volver a transcribir el audio.
- [x] **Dado** el panel de Ajustes (`/settings`), **cuando** el usuario modifica la cantidad predeterminada de clips por sesión (`auto_render_top_k`), **entonces** el valor se persiste en caliente y sirve como predeterminado para nuevas sesiones.
- [x] **Dadas** las pruebas unitarias y la compilación de `apps/web`, **cuando** se ejecuta `pytest -v`, `tsc --noEmit` y `next build`, **entonces** todas las pruebas pasan sin regresiones.

## 🛠️ Tareas técnicas
- [x] Añadir columna `max_clips` en SQLite (`db.py`) con migración automática segura para bases de datos existentes.
- [x] Propagar `max_clips` en `routes.py` (`CreateSessionBody`, `CreateDriveSessionBody`, `RerunSessionBody`, `UpdateSettingsBody.auto_render_top_k`) y `engine.py` / `api_pool.py`.
- [x] Añadir selector de cantidad de clips en `/sessions`, `/sessions/[id]`, `/settings` y `apps/web/src/lib/api/client.ts`.
- [x] Agregar pruebas en `tests/` verificando creación, reprocesamiento con distinto `max_clips` y persistencia en `/settings`.

## 📝 Registro de avance
- **2026-11-13**: Rama `feat/seleccion-cantidad-clips` creada y análisis técnico completado.
- **2026-11-13**: Implementación completa en backend (`db.py`, `api_pool.py`, `engine.py`, `routes.py`), frontend (`client.ts`, `/sessions`, `/sessions/[id]`, `/settings`) y pruebas automatizadas (`test_session_max_clips_and_settings_top_k`).

## 📝 Bitácora

- 2026-11-13 · Sin iniciar → **En progreso** · Implementación de selector de cantidad de clips en backend y frontend

---
- 2026-11-13 · En progreso → **Hecho** · Implementado selector de cantidad de clips (1-20) en backend, Web Studio y pruebas

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[2026-11-13 Selector de cantidad de clips por sesión]]
- [[Motor de Edición Web Studio]]
- [[FastAPI y Orquestador]]
