---
titulo: "2026-11-12 Exportación global de sesión a FilmCraft"
tipo: nota-origen
fecha: 2026-11-12
estado: vigente
audiencia: [equipo]
actualizado: 2026-11-12
etiquetas: [requerimientos, origen, filmcraft]
---

# 📝 2026-11-12 — Exportación global de sesión a FilmCraft

> [!abstract] En pocas palabras
> Requerimiento del usuario para exportar y abrir en **FilmCraft** toda una sesión en un único proyecto `.fcproj` (VOD Master completo + sub-secuencias anidadas por marcas de tiempo para los clips seleccionados).

> [!info] Requerimiento del usuario
> Pasar de exportar clip por clip (1 a 1) a una exportación **global a nivel de sesión/proyecto completo** hacia FilmCraft, con selección manual de qué clips incluir.
>
> En **FilmCraft**:
> - Incluir la **línea completa del proyecto** (el VOD entero de `gameplay` y `camera` con sus audios sincronizados) como secuencia principal (**Master**).
> - Colocar la edición de los clips seleccionados **según sus marcas de tiempo exactas** sobre el timeline global usando **sub-secuencias anidadas** (sub-secuencias verticales 9:16 dentro del mismo `.fcproj`), además de marcadores de secuencia.
> - El usuario puede elegir en `/sessions/[id]` cuáles clips de la sesión desea incluir en la exportación global.

## 📤 Qué salió de aquí
- [[HU-011 Exportación global de sesión a FilmCraft con sub-secuencias]]

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[Requerimientos]]
