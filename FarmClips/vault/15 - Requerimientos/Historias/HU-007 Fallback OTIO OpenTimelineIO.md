---
id: HU-007
titulo: Fallback OTIO OpenTimelineIO
tipo: historia
epica: EP-03
estado: hecho
audiencia: [creadores, desarrolladores]
responsable: Equipo FarmClips
prioridad: media
estimacion: S
avance: 100
fecha_inicio: 2026-11-12
fecha_fin: 2026-11-12
origen: "[[2026-11-12 Plan de integracion FilmCraft y copiloto MCP]]"
afecta:
  - "[[ADR-006 Integración con FilmCraft y copiloto MCP]]"
actualizado: 2026-11-12
etiquetas: [requerimientos, historia, area/interchange, otio]
estado_historia: hecho
inicio: 2026-11-12
fin: 2026-11-12
progreso: 100
---

# 📗 HU-007 — Fallback OTIO (OpenTimelineIO)

> [!abstract] En pocas palabras
> Proveer un exportador alternativo en formato universal OpenTimelineIO (`.otio`) para garantizar interoperabilidad con DaVinci Resolve, Premiere Pro y versiones anteriores o alternativas de NLEs.

> [!info] Historia de usuario
> **Como** creador que utiliza diversos entornos de montaje,
> **quiero** poder exportar mi clip como archivo `.otio`,
> **para** abrir el proyecto en cualquier editor no lineal estándar si el formato nativo no es requerido.

## ✅ Criterios de aceptación
- [x] Exportación a `.otio` con las pistas V1, V2, A1 y A2 con sus clips y cortes temporales.
- [x] Inclusión de marcadores de texto para los captions.
- [x] Metadatos del clip (`clip_id`, `plan_hash`) almacenados en el diccionario de metadatos de OTIO.

## 🛠️ Tareas técnicas
- [x] Módulo `clipsinterchange.otio.exporter`.
- [x] Pruebas unitarias de serialización OTIO (`test_otio_exporter`).

---

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[HU-006 Exportador EditPlan v2 a FilmCraft]]
