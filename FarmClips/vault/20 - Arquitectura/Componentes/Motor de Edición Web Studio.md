---
titulo: Motor de Edición Web Studio
tipo: componente
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/componente, area/frontend]
---

# Motor de Edición Web Studio (`apps/web`)

> [!abstract] En pocas palabras
> Es la interfaz visual en Next.js 15 donde los creadores revisan y ajustan sus clips en tiempo real. Reproduce el video vertical combinando las fuentes originales con transformaciones CSS y mezclando el sonido en el navegador con la Web Audio API, sin obligarte a esperar un renderizado completo cada vez que cambias un subtítulo.

---

## 🎨 Pantallas principales de la aplicación

La app web corre por defecto en `http://127.0.0.1:3040` y consta de las siguientes rutas:
- `/sessions`: Listado general de grabaciones procesadas, en curso y fallidas, con barra de progreso general.
- `/sessions/[id]`: Vista de detalle de una sesión, ranking de clips curados con sus puntuaciones y botón de reprocesamiento.
- `/editor/[clipId]`: Estudio de edición interactivo de un clip particular.
- `/settings`: Panel de control dinámico para editar API Keys, seleccionar modelos y configurar límites de presupuesto sin tocar archivos de texto a mano.
- `/analytics`: Métricas de consumo de tokens, uso de cuota en dólares y tiempos promedio de renderizado.

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
3. **Línea de tiempo de palabras recortables**: Cada palabra de la frase puede activarse o desactivarse; si se desactiva, el reproductor aplica un salto milimétrico instantáneo (**[[Glosario#Jump Cut|Jump Cut]]**).
4. **Catálogo de 42 emojis RGBA con caché inmutable**: Selector visual para sustituir o añadir iconos animados en cualquier segundo del video (servidos con `Cache-Control: immutable`).
5. **Exportación bajo demanda (síncrona o en segundo plano)**: Botón para solicitar renderizado borrador (540p) o final (1080p con NVENC), soportando encolado no bloqueante (`async_mode`).
6. **Experiencia de usuario con lenguaje claro y digerible**: Toda la interfaz (`/sessions`, `/editor/[clipId]`, `/settings`, `/analytics` y mensajes SSE del backend) explica el «por qué» detrás de cada control y proceso en lenguaje natural para creadores de gaming, sustituyendo tecnicismos y siglas crudas por resultados visuales y auditivos tangibles.
7. **Event Bus SSE unificado y aceleración por GPU (`SharedSseManager` y `GlassCard`)**: Un único socket persistente EventSource en cliente compartido por toda la aplicación distribuye eventos en memoria a `TopNav`, páginas y modales sin abrir múltiples conexiones HTTP/1.1 (evitando agotar el límite de 6 conexiones del navegador). Se combina con tarjetas `GlassCard` aceleradas en GPU (`transform-gpu`, `backdrop-blur-md`) y desacoplamiento de diagnósticos en `/settings` para ofrecer 60 fps constantes y carga inmediata (< 10 ms).
8. **Reencuadre Directo de Cámara y Subtítulos WYSIWYG**: El usuario interactúa directamente sobre el visor vertical $9:16$ con el puntero del ratón (`PointerEvents` con `setPointerCapture`) para centrar su rostro y mover la altura del bloque de subtítulos (`vertical_ratio` persistido en `EditPlan.captions` y respetado en el renderizado final de FFmpeg y C++ FastCompositor). Incluye una **guía magnética de centrado** que encaja suavemente en $cx = 0.50$ con una línea vertical dorada y control de zoom continuo con la rueda del ratón (`wheel`).
9. **Plantillas Rápidas de Disposición (1 Clic)**: Barra de ajustes inmediatos para alternar entre *Clásico Gaming* (40/60 split), *Gameplay Prioritario* (25/75), *Reacción Total* (100% cámara 2s) y *Juego Completo* (100% gameplay) sin necesidad de editar manualmente los bloques de la línea temporal.
10. **Sincronización a 60 FPS sin Jitter (Hardware Master Clock)**: La cámara actúa como reloj maestro continuo evitando reasignar forzadamente `video.currentTime` en cada cuadro de animación; el video secundario del juego solo se sincroniza cuando la deriva temporal supera los $40\text{ ms}$, eliminando micro-parones en decodificadores GPU locales y aprovechando `requestVideoFrameCallback` cuando el navegador lo soporta.
11. **Mezclador de Audio Intuitivo e Historial de Deshacer/Rehacer**: Controles visuales con deslizador de volumen de voz ($0\%$ a $150\%$), selector de atenuación del juego (Apagado, Suave, Normal, Fuerte) y soporte completo de atajos de teclado (`Ctrl+Z` / `Ctrl+Y`) respaldados por pilas inmutables de historial.

---

## 🔗 Relacionado
- [[FastAPI y Orquestador]]
- [[Contrato EditPlan v2]]
- [[Cómo usar el Editor Web Studio]]
- [[Sistema de Estilos y Presets]]
- [[HU-002 Simplificación y lenguaje claro en toda la plataforma|HU-002]]
- [[HU-003 Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps|HU-003]]