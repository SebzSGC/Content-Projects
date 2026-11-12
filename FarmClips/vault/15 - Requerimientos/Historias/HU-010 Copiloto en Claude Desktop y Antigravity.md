---
id: HU-010
titulo: Copiloto en Claude Desktop y Antigravity
tipo: historia
epica: EP-03
estado: hecho
audiencia: [creadores, streamers]
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
etiquetas: [requerimientos, historia, copiloto, mcp, claude]
estado_historia: hecho
inicio: 2026-11-12
fin: 2026-11-12
progreso: 100
---

# 📗 HU-010 — Copiloto en Claude Desktop y Antigravity

> [!abstract] En pocas palabras
> Integración combinada del MCP de FarmClips y el MCP de FilmCraft para permitir flujos de asistencia conversacional («haz zoom al streamer cuando dice tal frase», «abre el clip 2 en FilmCraft», «renderiza el clip actual»).

> [!info] Historia de usuario
> **Como** creador de contenido,
> **quiero** dar instrucciones en lenguaje natural al copiloto teniendo ambos MCP conectados,
> **para** editar y navegar mis clips sin operaciones manuales complejas.

## ✅ Criterios de aceptación
- [x] Guía paso a paso de configuración y uso conjunto en `vault/50 - Guías/Cómo usar el copiloto con Claude Desktop y Antigravity.md`.
- [x] Flujo validado: consulta de clips → apertura en FilmCraft → ajuste semántico vía transcripción.
- [x] Transparencia de privacidad documentada conforme a [[ADR-001 Arquitectura Híbrida IA Nube y Proceso Local]] y [[ADR-006 Integración con FilmCraft y copiloto MCP]].

## 🛠️ Tareas técnicas
- [x] Redacción de guía detallada con advertencias de privacidad y costos.
- [x] Ejemplos de prompts conversacionales para creadores.
- [x] Vinculación con los comandos CLI `mcp-config`.

---

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[HU-009 Servidor farmclips-mcp y mcp-config]]
- [[ADR-006 Integración con FilmCraft y copiloto MCP]]
