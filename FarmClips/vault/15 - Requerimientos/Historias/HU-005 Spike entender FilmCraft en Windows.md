---
id: HU-005
titulo: Spike entender FilmCraft en Windows
tipo: historia
epica: EP-03
estado: hecho
audiencia: [desarrolladores, arquitectos]
responsable: Equipo FarmClips
prioridad: alta
estimacion: M
avance: 100
fecha_inicio: 2026-11-12
fecha_fin: 2026-11-12
origen: "[[2026-11-12 Plan de integracion FilmCraft y copiloto MCP]]"
afecta:
  - "[[ADR-006 Integración con FilmCraft y copiloto MCP]]"
actualizado: 2026-11-12
etiquetas: [requerimientos, historia, area/nle, spike, filmcraft]
estado_historia: hecho
inicio: 2026-11-12
fin: 2026-11-12
progreso: 100
---

# 📗 HU-005 — Spike: entender FilmCraft en Windows

> [!abstract] En pocas palabras
> Verificar de forma práctica el funcionamiento real de FilmCraft 0.20.1 en Windows: ejecutables, CLI, formato JSON `.fcproj`, base de tiempo en ticks, servidor MCP nativo e importación de medios locales.

> [!info] Historia de usuario
> **Como** equipo de ingeniería,
> **quiero** validar las capacidades y el formato de datos de FilmCraft directamente en el entorno de desarrollo,
> **para** diseñar los exportadores sobre certezas técnicas y no sobre supuestos.

## ✅ Criterios de aceptación
- [x] Localizar y verificar los binarios `filmcraft.exe` y `filmcraft-cli.exe` en Windows.
- [x] Inspeccionar el formato nativo del proyecto `.fcproj`: confirmar estructura JSON UTF-8 (`schema_version: 17`) y compatibilidad con guardado determinista.
- [x] Determinar la base de tiempo interna: confirmada en `254,016,000,000` ticks por segundo.
- [x] Verificar el funcionamiento de `filmcraft-cli` (`probe`, `inspect`, `exec file.saveAs`, `import`).
- [x] Evaluar el servidor MCP nativo de `filmcraft-cli mcp`: confirmadas 17 herramientas operativas con soporte de `--bridge`.
- [x] Decisión arquitectónica registrada en [[ADR-006 Integración con FilmCraft y copiloto MCP]].

## 🛠️ Tareas técnicas
- [x] Detección de binarios en `C:\Users\sebas\AppData\Local\Programs\ArtCraft\FilmCraft\`.
- [x] Extracción y análisis del proyecto demo con `filmcraft-cli --demo inspect`.
- [x] Prueba de importación de clip MP4 local con `filmcraft-cli import` y `probe`.
- [x] Prueba de protocolo MCP por stdio (handshake `initialize` y `tools/list`).

## 📝 Bitácora
- 2026-11-12 · Sin iniciar → **En progreso** · Comienzo de pruebas exploratorias de FilmCraft en Windows.
- 2026-11-12 · En progreso → **Hecho** · Spike completado exitosamente: formato JSON determinista, ticks identificados y servidor MCP verificado.

---

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[2026-11-12 Plan de integracion FilmCraft y copiloto MCP]]
- [[ADR-006 Integración con FilmCraft y copiloto MCP]]
