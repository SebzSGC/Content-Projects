---
titulo: "Plan de integración FilmCraft y copiloto MCP"
tipo: nota-origen
estado: vigente
audiencia: [todos]
fecha: 2026-11-12
actualizado: 2026-11-12
autor: Equipo FarmClips
etiquetas: [requerimientos, origen, nle, filmcraft, mcp]
---

# 📝 Plan de integración FarmClips ↔ FilmCraft (+ MCP)

> [!abstract] Resumen
> Propuesta y requerimientos para exportar clips desde FarmClips a un proyecto nativo de FilmCraft (NLE de escritorio en Rust) y ofrecer asistencia conversacional mediante servidores MCP en Claude Desktop y Antigravity.

## Contexto y objetivos
1. FarmClips genera un `EditPlan v2` con cortes sincronizados, keyframes de encuadre, captions Hormozi y mezcla de audio.
2. El creador necesita una vía de escape profesional a un editor no lineal (NLE) completo para ajustes de alta precisión.
3. Se selecciona **FilmCraft** por ser ligero, con soporte nativo de GPU, formato determinista `.fcproj` (JSON) y servidor MCP incorporado.
4. Se diseña una arquitectura desacoplada con el paquete `clipsinterchange`, endpoints de exportación y apertura en FastAPI, y un servidor `farmclips-mcp` en stdio.

## Derivación
- Épica: [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- Historias:
  - [[HU-005 Spike entender FilmCraft en Windows]]
  - [[HU-006 Exportador EditPlan v2 a FilmCraft]]
  - [[HU-007 Fallback OTIO OpenTimelineIO]]
  - [[HU-008 Abrir en FilmCraft desde el Web Studio]]
  - [[HU-009 Servidor farmclips-mcp y mcp-config]]
  - [[HU-010 Copiloto en Claude Desktop y Antigravity]]
- Decisión: [[ADR-006 Integración con FilmCraft y copiloto MCP]]

---

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[ADR-006 Integración con FilmCraft y copiloto MCP]]
- [[Requerimientos]]
