---
titulo: Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps
tipo: nota-origen
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
fecha: 2026-11-07
fuente: solicitud-usuario
actualizado: 2026-11-07
etiquetas: [requerimientos, origen, area/frontend, editor, wysiwyg, rendimiento]
---

# 🗒️ Nota de origen — Editor interactivo WYSIWYG, reencuadre visual y rendimiento 60 fps

> [!abstract] En pocas palabras
> Solicitud para rediseñar completamente el Editor Web de Clips hacia un modelo 100% interactivo y visual (WYSIWYG), incorporando reencuadre directo con ratón, plantillas de disposición en un solo clic, sincronización a 60 fps sin parones y mezclador simplificado de audio.

## 🗣️ Solicitud original del usuario

> Tu objetivo es rediseñar y modernizar completamente el Editor Web de Clips (`apps/web/src/app/editor/[clipId]/page.tsx`), sus componentes auxiliares y sincronización con el contrato `EditPlan v2`, enfocándote en USABILIDAD VISUAL (WYSIWYG), RENDIMIENTO A 60 FPS y SIMPLICIDAD DE MODIFICACIÓN.
> 
> Implementa detalladamente los siguientes 4 módulos de mejoras:
> - **Módulo 1: Reencuadre Visual de Cámara y Subtítulos en Pantalla (Drag & Drop WYSIWYG)**: Arrastre directo de cámara con el ratón en visor 9:16 sin escribir coordenadas numéricas; guía magnética visual de centrado vertical roja/dorada en cx = 0.5; zoom visual por rueda o control deslizante 1.0x-2.5x; tirador vertical interactivo de subtítulos para no tapar la mira ni HUD.
> - **Módulo 2: Presets Rápidos de Disposición (Layout Templates en 1 Clic)**: Barra de plantillas (Clásico Gaming 40/60, Gameplay Prioritario 25/75, Reacción Total 100% cámara 2s, Juego Completo 100% gameplay) con inserción fluida en `plan.layout`.
> - **Módulo 3: Optimización de Rendimiento a 60 FPS y Sincronización Fluida**: Eliminar video jitter suprimiendo llamadas continuas a `currentTime`; reloj maestro en cámara con sincronización tolerante de deriva (> 40 ms); `requestVideoFrameCallback` con fallback a RAF; caché de renderizado en `<canvas>` para textos estáticos y aceleración GPU con `translateZ(0)`.
> - **Módulo 4: Usabilidad de Edición de Audio y Controles**: Mezclador simplificado con deslizador de Volumen de Voz (0% a 150%) y selector de 4 niveles de atenuación de juego; historial completo de Deshacer / Rehacer (Undo/Redo con `Ctrl+Z` y `Ctrl+Y`).

## 🔍 Interpretación técnica
1. **Reencuadre Directo y Posicionador de Subtítulos**: Manipulación visual mediante eventos Pointer con soporte táctil y de ratón, guía magnética vertical al centro y nuevo campo `vertical_ratio` en el contrato `CaptionsPlan`.
2. **Plantillas en 1 Clic**: Presets de pantalla dividida 40/60, 25/75, reacción completa y gameplay total.
3. **Reproducción 60 FPS sin Jitter**: Cámara como reloj maestro de hardware, sincronización tolerante de deriva (> 40 ms) para el juego, rVFC y caché en Canvas.
4. **Mezclador de Audio y Deshacer/Rehacer**: Conversión de dB a porcentaje (0-150%) y pilas de historial `undoStack`/`redoStack`.

## Historias derivadas
- [[HU-003 Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps]] (Épica: [[EP-02 Claridad y Experiencia de Usuario en Web Studio]])

---

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[HU-003 Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps]]
- [[Motor de Edición Web Studio]]
- [[Contrato EditPlan v2]]
- [[Motor de Renderizado y Subtítulos]]
