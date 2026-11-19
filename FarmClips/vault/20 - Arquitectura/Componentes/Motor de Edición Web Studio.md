---
titulo: Motor de Edición Web Studio
tipo: componente
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-13
etiquetas: [tipo/componente, area/frontend]
---

# Motor de Edición Web Studio (`apps/web`)

> [!abstract] En pocas palabras
> Es la interfaz visual en Next.js 15 inspirada en **Astryx de Meta** y aplicaciones nativas de escritorio macOS donde los creadores gestionan sesiones y ajustan sus clips en tiempo real. Reproduce el video vertical combinando las fuentes originales con transformaciones CSS y mezclando el sonido en el navegador con la Web Audio API, sin obligarte a esperar un renderizado completo cada vez que cambias un subtítulo.

---

## 🎨 Sistema de Diseño Astryx y Marco de Escritorio (`AppShell`)

El frontend utiliza un sistema de tokens semánticos propio inspirado en `@astryxdesign/core` y `@astryxdesign/theme-neutral` (`apps/web/src/app/globals.css`, `apps/web/src/components/ui.tsx` y `apps/web/src/components/TopNav.tsx`):
- **Jerarquía de superficies en 5 niveles**: `body` (`#0b0d11`) → `surface` (`#11141b`) → `card` (`#161922`) → `popover` (`#1d222e`) → `muted` (`#0e1016`), con soporte de alternancia en caliente entre los temas **Obsidiana Estudio (`dark`)** y **Grafito Puro (`graphite`)**.
- **Elevación por bisel de 1 px estilo macOS**: Las superficies emplean `--shadow-low`, `--shadow-med` y `--shadow-high` con iluminación cenital interna (`inset 0 1px 0 0 rgba(255,255,255,0.07)`) y radios concéntricos (`--radius-inner: 6px`, `--radius-element: 8px`, `--radius-container: 12px`, `--radius-page: 16px`).
- **Tipografía de precisión**: Fuente geométrica **`Figtree`** para controles y lectura general, combinada con **`JetBrains Mono`** (`tabular-nums`) para códigos de tiempo, métricas financieras y rutas, conservando `"Montserrat ExtraBold"` exclusivamente para el renderizado de subtítulos en el lienzo `<canvas>` 9:16.
- **Marco `AppShell` + `SideNav` colapsable**: Barra lateral izquierda estilo macOS que muestra telemetría del motor (`NVENC`/`CPU`, `STT`, `LLM`) y saldo en vivo, plegándose automáticamente al entrar en `/editor/[clipId]` para maximizar el área del visor a 60 fps.

## 🖥️ Pantallas principales de la aplicación

La app web corre por defecto en `http://127.0.0.1:3040` y consta de las siguientes rutas:
- `/sessions`: Creación de sesiones (PC, subida o explorador de Google Drive con filas estilo Finder y detección de pares en 1 clic) y listado de grabaciones con buscador instantáneo y filtro por estado (`Todas`, `En curso`, `Listas`, `Con aviso`).
- `/sessions/[id]`: Vista de detalle con pista de progreso `StepProgress` de 7 pasos, mapa de emoción con rejilla de referencia, selección de clips (**Incluido / Incluir**, **Todos / Ninguno**) para exportación global a FilmCraft (`.fcproj`) y galería de tarjetas verticales 9:16.
- `/editor/[clipId]`: Estudio de edición interactivo a 60 fps unificado bajo los tokens de Astryx, con barra de herramientas NLE, atajos de teclado `Kbd` (`Espacio`, `⌘Z`, `⌘Y`), inspector organizado con `TabList` y confirmación modal accesible (`AlertDialog`) al recalcular el tramo del clip.
- `/settings`: Panel de control con arquitectura maestro-detalle (`settings-sidebar`) que permite navegar por categorías (`1. Voz y Subtítulos`, `2. Curación IA`, `3. Presupuesto y Avisos`, `4. Google Drive`, `5. FilmCraft & MCP`) o ver todas las secciones en simultáneo.
- `/analytics`: Telemetría financiera con tarjetas KPI tabulares (`tabular-nums`), monitor de capa gratuita por proveedor, simulador de costos y tabla de auditoría.

---

## ⚡ Reproductor Declarativo de Alto Rendimiento

En lugar de renderizar un archivo de video temporal en el disco cada vez que el usuario mueve un control, el editor `/editor/[clipId]` superpone los dos videos originales (`gameplay.mp4` y `camara.mp4`) en un contenedor vertical de aspect ratio $9:16$:

```mermaid
flowchart TD
    subgraph Viewport["Lienzo Vertical 9:16 (Editor Web)"]
        CAM["Cámara frontal<br/>(CSS Transform: translate + zoom por keyframe)"]
        LINE["Línea de corte / seam"]
        GAME["Gameplay horizontal recortado"]
        CANVAS["Canvas 2D (60 fps)<br/>Subtítulos Hormozi + Emojis supersampled"]
    end

    subgraph AudioEngine["Mezclador Web Audio API (Navegador)"]
        MIC_GAIN["Ganancia de micrófono (+2 dB)"]
        DUCK["Atenuación sobre gameplay (-9 dB)"]
        SFX_PLAYER["Disparador de sfx/boom.wav"]
    end

    Viewport --- AudioEngine
```

---

## 🛠️ Capacidades interactivas y optimizaciones a 60 fps

1. **Desacoplamiento del loop a 60 fps respecto a React**: El ciclo `requestAnimationFrame` actualiza directamente mediante referencias DOM (`scrubberInputRef`, `timeLabelRef`, `playheadBarRef`) la barra de tiempo y el cursor visual a 60 Hz, sincronizando el estado de React a una tasa controlada (~8 Hz) para eliminar *micro-stutters* y reconciliaciones innecesarias del Virtual DOM.
2. **Caché de métricas tipográficas en `<canvas>` (`wordWidthCacheRef`)**: Precalcula y memoriza el ancho en píxeles (`ctx.measureText`) de cada palabra y tamaño de fuente para evitar recalcular la geometría tipográfica en cada fotograma.
3. **Inicio, final y cortes del clip**: El bloque *Inicio y final del clip* cambia el tramo de la grabación y enciende o apaga los **[[Glosario#Jump Cut|Jump Cut]]**; el servidor regenera el plan (`POST /clips/{id}/retime`) conservando el texto corregido y el título.
4. **Catálogo de 42 emojis RGBA con caché inmutable**: Selector visual para sustituir o añadir iconos animados en cualquier segundo del video (servidos con `Cache-Control: immutable`).
5. **Exportación bajo demanda (síncrona o en segundo plano)**: Botón para solicitar renderizado borrador (540p) o final (1080p con NVENC), soportando encolado no bloqueante (`async_mode`).
6. **Experiencia de usuario con lenguaje claro y digerible**: Toda la interfaz (`/sessions`, `/editor/[clipId]`, `/settings`, `/analytics` y mensajes SSE del backend) explica el «por qué» detrás de cada control y proceso en lenguaje natural para creadores de gaming, sustituyendo tecnicismos y siglas crudas por resultados visuales y auditivos tangibles.
7. **Event Bus SSE unificado y aceleración por GPU (`SharedSseManager` y `GlassCard`)**: Un único socket persistente EventSource en cliente compartido por toda la aplicación distribuye eventos en memoria a `TopNav`, páginas y modales sin abrir múltiples conexiones HTTP/1.1 (evitando agotar el límite de 6 conexiones del navegador). Se combina con tarjetas `GlassCard` aceleradas en GPU (`transform-gpu`, `backdrop-blur-md`) y desacoplamiento de diagnósticos en `/settings` para ofrecer 60 fps constantes y carga inmediata (< 10 ms).
8. **Reencuadre Directo de Cámara y Subtítulos WYSIWYG**: El usuario interactúa directamente sobre el visor vertical $9:16$ con el puntero del ratón (`PointerEvents` con `setPointerCapture`) para centrar su rostro y mover la altura del bloque de subtítulos (`vertical_ratio` persistido en `EditPlan.captions` y respetado en el renderizado final de FFmpeg y C++ FastCompositor). Incluye una **guía magnética de centrado** que encaja suavemente en $cx = 0.50$ con una línea vertical dorada y control de zoom continuo con la rueda del ratón (`wheel`).
9. **Plantillas Rápidas de Disposición (1 Clic)**: Barra de ajustes inmediatos para alternar entre *Clásico Gaming* (40/60 split), *Gameplay Prioritario* (25/75), *Reacción Total* (100% cámara 2s) y *Juego Completo* (100% gameplay) sin necesidad de editar manualmente los bloques de la línea temporal.
10. **Sincronización a 60 FPS sin Jitter (Hardware Master Clock)**: La cámara actúa como reloj maestro continuo evitando reasignar forzadamente `video.currentTime` en cada cuadro de animación; el video secundario del juego solo se sincroniza cuando la deriva temporal supera los $40\text{ ms}$, eliminando micro-parones en decodificadores GPU locales y aprovechando `requestVideoFrameCallback` cuando el navegador lo soporta.
11. **Mezclador de Audio Intuitivo e Historial de Deshacer/Rehacer**: Controles visuales con deslizador de volumen de voz ($0\%$ a $150\%$), selector de atenuación del juego (Apagado, Suave, Normal, Fuerte) y atajos `Ctrl+Z` / `Ctrl+Shift+Z` / `Ctrl+Y` / `Espacio`. Un arrastre o una palabra corregida es un solo paso de deshacer.
12. **Corrección de frases completas**: Además de cada palabra, una frase puede reescribirse con otro número de palabras; su tiempo se reparte según el largo de cada palabra para que el resaltado tipo karaoke siga al audio.
13. **Guardado automático**: 2.5 s después del último cambio (nunca durante un arrastre, un guardado o un render) y aviso del navegador al salir con cambios sin guardar.

> [!info]- Detalle técnico: dónde vive la lógica del editor
> `apps/web/src/lib/editor/`:
> - `useEditHistory.ts`: plan + deshacer/rehacer (máx. 30 pasos). `planRef` se actualiza en el acto, así el bucle de 60 fps, los arrastres y las llamadas asíncronas siempre leen el último plan. Nada se registra dentro de un actualizador de `setState` (en `StrictMode` corre dos veces).
> - `useEditorShortcuts.ts`: atajos con *handlers* leídos de una referencia (evita el `togglePlay` viejo que impedía pausar con `Espacio`).
> - `useAutosave.ts`: temporizador de guardado y aviso `beforeunload`.
> - `captionText.ts`: `retextCaptionGroup` (misma cantidad de palabras: conserva tiempos y énfasis; distinta: reparte el tiempo).
>
> En pausa `requestVideoFrameCallback` no se dispara, así que cada cambio del plan repinta el visor y refresca la etiqueta de tiempo.

---

## 🔗 Relacionado
- [[FastAPI y Orquestador]]
- [[Contrato EditPlan v2]]
- [[Cómo usar el Editor Web Studio]]
- [[Cómo abrir un clip en FilmCraft]]
- [[Sistema de Estilos y Presets]]
- [[HU-002 Simplificación y lenguaje claro en toda la plataforma|HU-002]]
- [[HU-003 Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps|HU-003]]
- [[HU-004 Edición confiable de clips tramos frases y guardado automático|HU-004]]
- [[HU-011 Exportación global de sesión a FilmCraft con sub-secuencias|HU-011]]
- [[HU-012 Rediseño integral del Web Studio inspirado en Astryx de Meta|HU-012]]