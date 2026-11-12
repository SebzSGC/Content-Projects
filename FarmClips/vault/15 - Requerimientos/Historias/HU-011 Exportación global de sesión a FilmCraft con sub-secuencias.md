---
id: HU-011
titulo: Exportación global de sesión a FilmCraft con sub-secuencias
tipo: historia
epica: EP-03
estado: vigente
audiencia: [creadores, streamers]
responsable: Equipo FarmClips
prioridad: alta
estimacion: L
avance: 0
fecha_inicio: 2026-11-12
fecha_fin: 2026-11-12
origen: "[[2026-11-12 Exportación global de sesión a FilmCraft]]"
afecta:
  - "[[Motor de Edición Web Studio]]"
  - "[[Referencia API REST y SSE]]"
  - "[[Integraciones]]"
  - "[[ADR-006 Integración con FilmCraft y copiloto MCP]]"
actualizado: 2026-11-12
etiquetas: [requerimientos, historia, area/interchange, area/backend, area/frontend, filmcraft]
estado_historia: hecho
inicio: 2026-11-12
fin: 2026-11-12
progreso: 100
fin_real: 2026-11-12
---

# 📗 HU-011 — Exportación global de sesión a FilmCraft con sub-secuencias

> [!abstract] En pocas palabras
> Permitir exportar y abrir en **FilmCraft** un único proyecto `.fcproj` para toda la sesión, con la línea completa del VOD como secuencia principal (Master), marcadores en cada momento clave y **sub-secuencias anidadas 9:16** colocadas en sus marcas de tiempo exactas para los clips elegidos por el usuario.

> [!info] Historia de usuario
> **Como** creador de contenido con múltiples clips detectados en una sesión,
> **quiero** seleccionar qué clips incluir y exportarlos en un solo proyecto global hacia FilmCraft con la grabación completa arriba/en la línea base y las sub-secuencias de cada clip ubicadas en sus marcas de tiempo,
> **para** editar y ajustar todos mis Shorts desde un único archivo `.fcproj` sin abrir ni gestionar proyectos individuales uno por uno.

## ✅ Criterios de aceptación
- [x] `FilmCraftExporter.export_session(...)` genera un `.fcproj` único con el bin `Footage` compartido (`gameplay` + `camera`), una secuencia principal **Master** con el VOD completo de punta a punta y sus audios sincronizados, marcadores por clip y una sub-secuencia 9:16 por cada clip seleccionado anidada en sus marcas de tiempo exactas del VOD.
- [x] Las sub-secuencias 9:16 conservan la fidelidad de `EditPlan` v2 (cámara con keyframes de reencuadre, gameplay, overlays, ducking de audio y subtítulos nativos C1) sin colisionar entre sí en archivos auxiliares (`clips/<clip_id>/`).
- [x] Endpoints en FastAPI a nivel de sesión: `POST /sessions/{session_id}/filmcraft/export`, `POST /sessions/{session_id}/filmcraft/open`, `GET /sessions/{session_id}/filmcraft/download` y `POST /sessions/{session_id}/filmcraft/reveal`, aceptando una lista opcional `clip_ids` para filtrar qué clips incluir.
- [x] En `/sessions/[id]` del Web Studio, el usuario puede seleccionar/deseleccionar clips (con atajos «Todos» / «Ninguno») y pulsar **«Abrir proyecto en FilmCraft»** (con opciones de descargar `.fcproj` o abrir carpeta).
- [x] El proyecto `.fcproj` multi-secuencia generado pasa validación con `filmcraft-cli.exe inspect` y las pruebas automatizadas en `pytest`.

## 🛠️ Tareas técnicas
- [x] Implementar `export_session` (y método de construcción de secuencia reutilizable por clip) en `packages/interchange/clipsinterchange/filmcraft/exporter.py`.
- [x] Añadir endpoints de sesión para FilmCraft en `apps/server/clipsserver/api/routes.py` y regenerar contratos (`codegen`).
- [x] Añadir cliente API y selector de clips + botón global «Abrir proyecto en FilmCraft» en `apps/web/src/app/sessions/[id]/page.tsx`.
- [x] Añadir pruebas unitarias e integración en `tests/test_interchange.py` y `tests/test_filmcraft_api.py`.

---

## 📝 Bitácora

- 2026-11-12 · Por hacer → **En progreso** · Inicio implementación exportación global de sesión a FilmCraft (Opción B + selector de clips)
- 2026-11-12 · En progreso → **En revisión** · Implementado en backend, interchange y web studio; 53/53 pruebas pytest activas y tsc sin errores
- 2026-11-12 · En revisión → **Hecho** · Verificado con filmcraft-cli inspect, pytest y validación del vault

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[HU-006 Exportador EditPlan v2 a FilmCraft]]
- [[HU-008 Abrir en FilmCraft desde el Web Studio]]
- [[Referencia API REST y SSE]]
