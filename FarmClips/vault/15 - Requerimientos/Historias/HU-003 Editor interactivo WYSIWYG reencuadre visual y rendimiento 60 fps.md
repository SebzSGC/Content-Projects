---
id: HU-003
titulo: Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps
tipo: historia
epica: EP-02
estado: hecho
audiencia: [creadores, streamers]
responsable: Equipo FarmClips
prioridad: alta
estimacion: L
avance: 100
fecha_inicio: 2026-11-07
fecha_fin: 2026-11-07
origen: "[[2026-11-07 Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps]]"
afecta:
  - "[[Motor de Edición Web Studio]]"
  - "[[Motor de Renderizado y Subtítulos]]"
  - "[[Contrato EditPlan v2]]"
actualizado: 2026-11-07
etiquetas: [requerimientos, historia, area/frontend, editor, wysiwyg, 60fps]
estado_historia: hecho
inicio: 2026-11-07
fin_real: 2026-11-07
progreso: 100
---

# 📗 HU-003 — Editor interactivo WYSIWYG, reencuadre visual y rendimiento 60 fps

> [!abstract] En pocas palabras
> Modernización integral del Editor Web de Clips hacia un paradigma 100% visual (WYSIWYG) con manipulación directa de cámara con el ratón, guía magnética vertical, zoom continuo, posicionador de subtítulos arrastrable, plantillas de disposición en 1 clic, motor de sincronización a 60 fps sin jitter y mezclador intuitivo con deshacer/rehacer.

> [!info] Historia de usuario
> **Como** creador de contenido o streamer de videojuegos,
> **quiero** mover mi cámara y subtítulos directamente con el ratón en la pantalla 9:16, cambiar de encuadre con un solo clic y ajustar el volumen de mi voz sin números raros ni parones de video,
> **para** obtener shorts listos para publicar de forma rápida, fluida y sin frustración.

## ✅ Criterios de aceptación
- [x] **Reencuadre Directo de Cámara**: El usuario puede hacer clic y arrastrar su cámara en el visor 9:16 en los ejes X e Y sin escribir coordenadas numéricas, con ajuste inmediato sobre los keyframes de `EditPlan.camera_crop`.
- [x] **Guía Magnética de Centrado**: Al acercarse a $cx = 0.50$ ($\pm 2.5\%$), el encuadre se acopla magnéticamente al centro y despliega una línea dorada/roja vertical con badge informativo.
- [x] **Zoom Visual Continuo**: La rueda del ratón (`wheel`) y los botones $+/-$ flotantes permiten ajustar el zoom entre $1.0\times$ y $2.5\times$ con respuesta visual instantánea.
- [x] **Posicionador Vertical de Subtítulos**: Un tirador interactivo arrastrable en el visor permite reubicar la altura de los subtítulos (`vertical_ratio` y `preset.captions.gameplay_top_third_ratio`) para no ocultar la mira ni el HUD.
- [x] **Plantillas Rápidas de Disposición**: Barra de plantillas en 1 clic: *Clásico Gaming* (40/60), *Gameplay Prioritario* (25/75), *Reacción Total* (100% cámara 2s) y *Juego Completo* (100% gameplay).
- [x] **Rendimiento a 60 FPS sin Video Jitter**: Uso del video de la cámara como reloj maestro (`master clock`), con sincronización tolerante de deriva ($> 40\text{ ms}$) para el video del juego, aceleración por hardware con `translateZ(0)` y soporte de `requestVideoFrameCallback`.
- [x] **Caché Inteligente de Subtítulos**: Omisión del redibujo de texto estático en `<canvas>` cuando no hay cambios de fotograma, reduciendo el consumo de GPU/CPU local.
- [x] **Mezclador de Audio Intuitivo**: Control de volumen de voz con slider porcentual ($0\%$ a $150\%$) y selector visual de atenuación de juego (Apagado, Suave, Normal, Fuerte).
- [x] **Historial Deshacer / Rehacer**: Soporte completo de pilas de deshacer (`undoStack`) y rehacer (`redoStack`) mediante botones en cabecera y atajos de teclado (`Ctrl+Z`, `Ctrl+Y`).

## 🛠️ Tareas técnicas
- [x] Añadir `vertical_ratio` a `CaptionsPlan` en `packages/editplan/clipseditplan/models.py`.
- [x] Actualizar `ass_compiler.py`, `fast_compositor.py` y `filtergraph.py` para respetar la posición vertical de subtítulos personalizada.
- [x] Sincronizar contratos TypeScript y OpenAPI mediante `python -m clipsserver.main codegen --web-dir apps/web`.
- [x] Rediseñar por completo el visor y paneles en `apps/web/src/app/editor/[clipId]/page.tsx`.
- [x] Verificar compilación sin fallos con `npm run build` en `apps/web`.
- [x] Validar suite de 22 pruebas unitarias y de integración pasando al 100%.

## 📝 Bitácora

- 2026-11-07 · Sin iniciar → **En progreso** · Iniciando rediseño WYSIWYG, optimización 60fps y plantillas del editor web
- 2026-11-07 · En progreso → **Hecho** · Editor interactivo completamente operativo, verificado y documentado

---

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[2026-11-07 Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps]]
- [[Motor de Edición Web Studio]]
- [[Motor de Renderizado y Subtítulos]]
- [[Contrato EditPlan v2]]
