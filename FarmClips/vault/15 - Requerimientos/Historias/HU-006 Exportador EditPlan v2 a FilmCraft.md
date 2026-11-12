---
id: HU-006
titulo: Exportador EditPlan v2 a FilmCraft
tipo: historia
epica: EP-03
estado: hecho
audiencia: [creadores, desarrolladores]
responsable: Equipo FarmClips
prioridad: alta
estimacion: L
avance: 100
fecha_inicio: 2026-11-12
fecha_fin: 2026-11-12
origen: "[[2026-11-12 Plan de integracion FilmCraft y copiloto MCP]]"
afecta:
  - "[[ADR-006 Integración con FilmCraft y copiloto MCP]]"
  - "[[Contrato EditPlan v2]]"
actualizado: 2026-11-12
etiquetas: [requerimientos, historia, area/interchange, area/nle]
estado_historia: hecho
inicio: 2026-11-12
fin: 2026-11-12
progreso: 100
---

# 📗 HU-006 — Exportador EditPlan v2 a proyecto FilmCraft

> [!abstract] En pocas palabras
> Generar un proyecto nativo `.fcproj` determinista a partir de un `EditPlan v2` con pistas V1 (gameplay), V2 (cámara), V3 (overlays/captions), A1 (voz), A2 (juego con ducking) y A3 (sfx), cortes sincronizados al frame y keyframes de encuadre.

> [!info] Historia de usuario
> **Como** creador de contenido,
> **quiero** que mi clip de FarmClips se transforme en un proyecto completo de FilmCraft,
> **para** disponer de un timeline editable en un NLE profesional con todas las pistas alineadas.

## ✅ Criterios de aceptación
- [x] El exportador genera un archivo `.fcproj` válido conforme a `schema_version: 17`.
- [x] La secuencia resultante tiene dimensiones 1080×1920 y respeta la tasa de cuadros racional.
- [x] Los rangos de `source.ranges` crean cortes sincronizados en V1, V2, A1 y A2 en instantes idénticos del timeline.
- [x] El offset FFT de la cámara se aplica al punto de entrada (`source_in`) de los clips en V2.
- [x] Los layouts (`split`, `camera_full`, `gameplay_full`) y keyframes de `camera_crop` y `gameplay_crop` se traducen a transformaciones de `motion` (posición, escala, ancla) matemáticamente idénticas a `fast_compositor.py`.
- [x] La ganancia del micrófono (`mic_gain_db`) y el ducking del juego (`duck_game_db`) se traducen a niveles y keyframes de volumen en A1 y A2.
- [x] Los captions se exportan según `CLIPS_FILMCRAFT_CAPTIONS_MODE` (clips nativos en V3 + marcadores en la secuencia).
- [x] Exportaciones repetidas con el mismo `plan_hash` generan salidas idénticas (idempotencia).

## 🛠️ Tareas técnicas
- [x] Crear paquete `packages/interchange/` con `clipsinterchange`.
- [x] Módulo `timebase.py`: funciones `seconds_to_ticks`, `ticks_to_seconds`, snap a frame.
- [x] Módulo `geometry.py`: funciones para transformar regiones y encuadres normalizados `(cx, cy, zoom)` a coordenadas de lienzo.
- [x] Módulo `audio.py`: generación de keyframes de rampa de ducking sobre tramos con voz.
- [x] Módulo `filmcraft/exporter.py`: ensamblador de la estructura `filmcraft.project`.
- [x] Suite de pruebas unitarias (`test_timebase.py`, `test_geometry.py`, `test_filmcraft_exporter.py`).

## 📝 Bitácora
- 2026-11-12 · Sin iniciar → **En progreso** · Definición de especificaciones y creación de la arquitectura de `clipsinterchange`.
- 2026-11-12 · En progreso → **Hecho** · Paquete `clipsinterchange` implementado y verificado con `filmcraft-cli` oficial (6/6 pruebas aprobadas).

---

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[HU-005 Spike entender FilmCraft en Windows]]
- [[ADR-006 Integración con FilmCraft y copiloto MCP]]
