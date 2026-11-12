---
id: HU-008
titulo: Abrir en FilmCraft desde el Web Studio
tipo: historia
epica: EP-03
estado: hecho
audiencia: [creadores, streamers]
responsable: Equipo FarmClips
prioridad: alta
estimacion: M
avance: 100
fecha_inicio: 2026-11-12
fecha_fin: 2026-11-12
origen: "[[2026-11-12 Plan de integracion FilmCraft y copiloto MCP]]"
afecta:
  - "[[Motor de Edición Web Studio]]"
  - "[[Referencia API REST y SSE]]"
  - "[[Variables de Entorno]]"
actualizado: 2026-11-12
etiquetas: [requerimientos, historia, area/frontend, area/backend, filmcraft]
estado_historia: hecho
inicio: 2026-11-12
fin: 2026-11-12
progreso: 100
---

# 📗 HU-008 — Abrir en FilmCraft desde el Web Studio

> [!abstract] En pocas palabras
> Botón «Abrir en FilmCraft» en `/editor/[clipId]` y panel de configuración en `/settings` para lanzar y conectar la aplicación de escritorio con guardado automático previo y gestión segura de procesos.

> [!info] Historia de usuario
> **Como** creador que revisa un clip en la interfaz web,
> **quiero** pulsar un botón «Abrir en FilmCraft» para que la aplicación de escritorio se abra con mi proyecto montado al instante,
> **para** continuar la edición profesional sin manipular archivos manualmente en el explorador.

## ✅ Criterios de aceptación
- [x] Endpoints en FastAPI: `GET /integrations/filmcraft/status`, `POST /clips/{id}/filmcraft/export` y `POST /clips/{id}/filmcraft/open`.
- [x] Botón «Abrir en FilmCraft» en la cabecera de `/editor/[clipId]` con estados: normal, cargando, abierto o error claro.
- [x] Al pulsar el botón, se fuerza el guardado de cualquier cambio pendiente en el editor antes de exportar.
- [x] Reutilización de instancia: si FilmCraft está activo con su bridge TCP, se abre en la ventana existente sin abrir procesos duplicados.
- [x] Sección de integración en `/settings` con detección automática de ruta, versión y botón de comprobación.

## 🛠️ Tareas técnicas
- [x] Clase `FilmCraftLauncher` en `clipsserver/filmcraft.py`.
- [x] Rutas FastAPI en `clipsserver/api/routes.py`.
- [x] Regeneración de contratos OpenAPI y tipos TypeScript con `codegen`.
- [x] Botón y lógica en `apps/web/src/app/editor/[clipId]/page.tsx` y tarjeta en `apps/web/src/app/settings/page.tsx`.
- [x] Pruebas unitarias de la API en `tests/test_filmcraft_api.py`.

---

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[HU-006 Exportador EditPlan v2 a FilmCraft]]
- [[Motor de Edición Web Studio]]
