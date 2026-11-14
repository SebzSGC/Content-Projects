---
titulo: Selector de cantidad de clips por sesión
tipo: nota-origen
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
fecha: 2026-11-13
fuente: solicitud-usuario
actualizado: 2026-11-13
etiquetas: [requerimientos, origen, area/frontend, area/backend, curacion]
---

# 🗒️ Nota de origen — Selector de cantidad de clips por sesión

> [!abstract] En pocas palabras
> El usuario solicita poder elegir cuántos clips desea extraer de una sesión de grabación (tanto al crearla como por defecto o al reprocesar), ya que actualmente el sistema no ofrece esta opción en la interfaz.

## 🗣️ Solicitud original del usuario

> crea este nuevo requeirmiento en otra rama, necesito que la aplicacion tenga la opcion de que el usuario pueda seleccionar cuantos clips sacar, actualmente no tiene esta opcion, desarrollala, y despues de que todo este correcto yo te digo si la mergeamos a develop

## 🔍 Interpretación técnica
1. **Persistencia y API (`db.py`, `routes.py`, `config.py`)**:
   - Añadir campo `max_clips` (rango `1..20`, opcional) a la tabla `sessions`, a los cuerpos `CreateSessionBody`, `CreateDriveSessionBody` y `RerunSessionBody` (`POST /sessions/{id}/run`), y exponer `auto_render_top_k` editable en `POST /settings`.
2. **Orquestador y Curación (`engine.py`, `api_pool.py`)**:
   - Usar `max_clips` de la sesión (o `settings.auto_render_top_k` por defecto) al invocar `curate_window_cached` (incluyendo `max_clips` en el `task_hash` de caché), acotar los clips resultantes de `resolve_curated_clips` al máximo pedido y auto-renderizar hasta ese tope.
3. **Web Studio (`apps/web`)**:
   - `/sessions`: selector rápido de cantidad de clips (`3`, `5`, `8`, `10` o valor personalizado `1–20`) en el formulario de creación de sesión (PC, subida y Google Drive).
   - `/sessions/[id]`: selector junto a «Reprocesar gratis» para ajustar la cantidad deseada al regenerar clips.
   - `/settings`: campo de cantidad predeterminada de clips por sesión (`auto_render_top_k`).

## 📤 Qué salió de aquí
- [[HU-013 Selección de cantidad de clips a extraer por sesión]] (Épica: [[EP-02 Claridad y Experiencia de Usuario en Web Studio]])

---

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[HU-013 Selección de cantidad de clips a extraer por sesión]]
- [[FastAPI y Orquestador]]
- [[Motor de Edición Web Studio]]
