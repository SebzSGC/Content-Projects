---
id: HU-004
titulo: Edición confiable de clips tramos frases y guardado automático
tipo: historia
epica: EP-02
estado: en-revision
audiencia: [creadores, streamers]
responsable: Equipo FarmClips
prioridad: alta
estimacion: L
avance: 90
fecha_inicio: 2026-11-09
origen: "[[2026-11-09 Mejoras del editor de clips]]"
afecta:
  - "[[Motor de Edición Web Studio]]"
  - "[[Motor de Renderizado y Subtítulos]]"
  - "[[Cómo usar el Editor Web Studio]]"
  - "[[Cómo exportar y renderizar clips]]"
  - "[[Referencia API REST y SSE]]"
actualizado: 2026-11-09
etiquetas: [requerimientos, historia, area/frontend, area/render, editor]
progreso: 86
---

# 📗 HU-004 — Edición confiable de clips: tramos, frases y guardado automático

> [!abstract] En pocas palabras
> El editor deja de perder o esconder cambios, permite corregir frases completas y mover el inicio y el final del clip, guarda solo, y en Mac exporta casi el doble de rápido con la misma calidad.

> [!info] Historia de usuario
> **Como** streamer que revisa sus clips,
> **quiero** que el editor responda como espero (pausar, deshacer, ver el cambio al instante), corregir frases y ajustar dónde empieza y termina el clip sin perder lo editado,
> **para** dejar cada clip listo para publicar en pocos minutos y sin rehacer trabajo.

## ✅ Criterios de aceptación
- [x] `Espacio` reproduce y pausa siempre; dentro de un campo de texto escribe un espacio.
- [x] En pausa, cualquier cambio (texto, posición de subtítulos, cámara, deshacer) se ve al instante en el visor y el contador de tiempo muestra la duración actual.
- [x] Deshacer después de arrastrar los subtítulos vuelve exactamente a la posición anterior; cada arrastre y cada palabra corregida es un solo paso.
- [x] Una frase puede corregirse completa aunque tenga otro número de palabras; no quedan palabras vacías.
- [x] El clip puede empezar o terminar en otro segundo (entre 5 s y 3 min) y con o sin cortes rápidos, conservando el texto corregido y el título.
- [x] Los cambios se guardan solos 2.5 s después del último y el navegador avisa al salir con cambios sin guardar.
- [x] En Mac el render usa VideoToolbox con VMAF igual o mayor que libx264; en Windows/Linux la cadena sigue siendo NVENC → libx264.
- [ ] Revisión y aprobación del Pull Request.

## 🛠️ Tareas técnicas
- [x] `useEditHistory`, `useEditorShortcuts`, `useAutosave` y `captionText` en `apps/web/src/lib/editor/`.
- [x] `engine.retime_clip`, `CuratedClip.jump_cuts` y `POST /clips/{id}/retime`; contrato OpenAPI regenerado.
- [x] `encoder_chain()` con VideoToolbox solo en macOS y ajuste `CLIPS_VIDEOTOOLBOX`.
- [x] Pruebas: `test_encoder_selection.py`, escenario de tramo en `test_golden_e2e.py`; 34 pruebas pasan.
- [x] Verificación en navegador: `Espacio`, frase completa, deshacer de frase y de subtítulos, tramo con y sin cortes, guardado automático.
- [ ] Separar las pestañas del editor en componentes (la lógica ya está en *hooks*; queda pendiente dividir la página).

## 📝 Bitácora

- 2026-11-09 · Sin iniciar → **En progreso** · Plan de mejora del editor aprobado (VideoToolbox solo en Mac)
- 2026-11-09 · En progreso → **En revisión** · Cambios hechos, probados y documentados; falta aprobar el Pull Request

---

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[2026-11-09 Mejoras del editor de clips]]
- [[HU-003 Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps]]
- [[Motor de Edición Web Studio]]
- [[Motor de Renderizado y Subtítulos]]
