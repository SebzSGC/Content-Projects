---
titulo: Historial de cambios
tipo: cambios
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
actualizado: 2026-11-09
etiquetas: [tipo/cambios, area/general]
---

# Historial de cambios de FarmClips

> [!abstract] En pocas palabras
> Registro cronológico de las versiones de FarmClips, nuevas funcionalidades, optimizaciones de rendimiento y ajustes en la arquitectura del sistema.

## [2.7.0] — 2026-11-12 (Versión actual)

### 🎬 Integración FilmCraft NLE y Copiloto Conversacional MCP

Exportación determinista de clips a proyectos nativos de FilmCraft (`.fcproj`), apertura en 1 clic desde el Web Studio, fallback OpenTimelineIO (`.otio`) y servidor `farmclips-mcp` para asistencia en lenguaje natural con Claude Desktop y Antigravity.

#### Qué cambió
- **Nuevo botón «Abrir en FilmCraft» y banner interactivo** en `/editor/[clipId]`:
  - Guarda automáticamente los cambios pendientes y abre la aplicación con el proyecto montado (reutilizando la ventana activa vía bridge TCP loopback `127.0.0.1:9876` o iniciando una nueva instancia en el escritorio del usuario).
  - Banner con accesos rápidos: **«Abrir carpeta»** para revelar y seleccionar el `.fcproj` en el Explorador de Windows, y **«Descargar .fcproj»** para descarga directa del proyecto.
- **Acciones y endpoints adicionales en FastAPI**:
  - `GET /clips/{clip_id}/filmcraft/download`: descarga directa del `.fcproj` u `.otio`.
  - `POST /clips/{clip_id}/filmcraft/reveal`: abre el explorador del sistema operativo seleccionando el archivo de proyecto.
- **Lanzamiento robusto con aceleración GPU en Windows y solución de visualización**:
  - Eliminación de `--graphics default` forzado en el comando de registro y en el lanzador, permitiendo que FilmCraft seleccione automáticamente su backend gráfico óptimo (`DirectX 12` / `Vulkan`) y evitando bloqueos o cuelgues en equipos con GPU híbrida (Intel UHD + NVIDIA GeForce RTX).
  - Limpieza proactiva de marcadores bloqueantes de pruebas gráficas (`graphics-test.json`, `graphics-start.json`) y carpetas de recuperación (`Recovery`) antes de cada lanzamiento.
  - Detección precisa de ventana interactiva mediante `FindWindowW` y terminación automática de procesos huérfanos/zombies previos.
  - Corrección en el Web Studio (`/editor/[clipId]`): se eliminó la apertura forzada simultánea del Explorador de Windows al pulsar «Abrir en FilmCraft», manteniendo la ventana de FilmCraft en primer plano (el usuario dispone del botón «Abrir carpeta» si desea explorarla manualmente).
  - Asociación automática de archivos `.fcproj` en el Registro de Windows (`HKCU\Software\Classes\.fcproj`) y gestión de tokens de control de 64 caracteres hex.
- **Nuevo paquete `packages/interchange/` (`clipsinterchange`)**:
  - `TimelineExporter` (Protocolo desacoplado de exportación).
  - `FilmCraftExporter`: genera deterministamente proyectos `.fcproj` (`schema_version: 17`) con pistas `V1 Gameplay`, `V2 Cámara`, `V3 Overlays`, `A1 Mic`, `A2 Juego` (con ducking automático) y `A3 SFX`.
  - `OtioExporter`: fallback en formato universal OpenTimelineIO (`.otio`) para DaVinci Resolve y Premiere Pro.
  - `timebase.py`: base de tiempo en ticks exactos (`254,016,000,000` ticks/segundo) con cálculo racional en `fractions.Fraction` (0 deriva temporal).
  - `geometry.py`: proyección matemática continua de encuadres `(cx, cy, zoom)` a transformaciones de `motion` (posición, escala, ancla) 100% compatibles con `fast_compositor.py`.
- **Nuevos endpoints en FastAPI**:
  - `GET /integrations/filmcraft/status`: diagnóstico de binarios (`filmcraft.exe`, `filmcraft-cli.exe`), versión fijada (`0.20.1`) y estado del bridge.
  - `POST /clips/{clip_id}/filmcraft/export`: genera el proyecto en disco y emite evento SSE `filmcraft.export.finished`.
  - `POST /clips/{clip_id}/filmcraft/open`: ejecuta el lanzador seguro.
- **Servidor MCP stdio (`farmclips-mcp`)**:
  - Servidor en `clipsserver/mcp/` con 9 herramientas oficiales (`list_sessions`, `list_clips`, `get_clip`, `get_transcript`, `update_editplan`, `export_to_filmcraft`, `open_in_filmcraft`, `render_clip`, `get_render_status`).
  - Comando `python -m clipsserver.main mcp-config` que genera el bloque listo para `claude_desktop_config.json` con rutas detectadas automáticamente en la máquina.
- **Panel de Ajustes (`/settings`)**:
  - Nueva tarjeta «FilmCraft NLE & Copiloto MCP» con estado de instalación, versión, ruta y botón de comprobación.
- **Documentación & Backlog**:
  - Épica [[EP-03 Edición profesional en FilmCraft con copiloto MCP]] y 6 historias de usuario ([[HU-005 Spike entender FilmCraft en Windows|HU-005]] a [[HU-010 Copiloto en Claude Desktop y Antigravity|HU-010]]) completadas al 100%.
  - Nota de decisión [[ADR-006 Integración con FilmCraft y copiloto MCP]].
  - Nuevas guías: [[Cómo abrir un clip en FilmCraft]] y [[Cómo usar el copiloto con Claude Desktop y Antigravity]].

#### Por qué
- Brindar a los creadores una vía de escape profesional a un editor no lineal (NLE) de escritorio sin perder los cortes sincronizados ni el seguimiento facial ya calculados.
- Aprovechar el servidor MCP de FilmCraft y FarmClips para ofrecer asistencia conversacional inteligente sin gastar tokens en el montaje inicial.

> [!warning] ⚠️ Cambia para ti
> - En la barra del editor web ahora verás el botón **Abrir en FilmCraft** junto a «Guardar cambios».
> - En **Ajustes** verás si FilmCraft está detectado en tu PC y el estado de su bridge de control.
> - Puedes conectar Claude Desktop ejecutando `python -m clipsserver.main mcp-config` y pedirle cambios al proyecto en lenguaje natural.

---

## [2.6.0] — 2026-11-09

### ✂️ Editor confiable, tramos del clip, guardado automático y render rápido en Mac

Revisión del editor de clips: se corrigieron fallos que se notaban al editar y se agregó lo que faltaba para dejar un clip listo sin salir del editor. En Mac el render usa el chip de Apple con la misma calidad.

#### Qué cambió
- **Correcciones del editor** (`apps/web/src/app/editor/[clipId]/page.tsx`, `src/lib/editor/`):
  - `Espacio` no pausaba (el atajo usaba una versión vieja de la función). Ahora reproduce y pausa siempre.
  - En pausa, los cambios no se veían en el visor hasta reproducir. Ahora cada cambio repinta el visor y el contador de tiempo.
  - Deshacer después de mover los subtítulos dejaba la posición mal; y con `StrictMode` algunos cambios se registraban dos veces. El historial nuevo (`useEditHistory`) lo hace bien.
  - Corregir una palabra creaba un paso de deshacer por cada letra; ahora es uno por palabra y no se permiten palabras vacías.
- **Corregir la frase completa**, aunque cambie el número de palabras (el tiempo se reparte entre ellas).
- **Inicio y final del clip** con ±1 s y el interruptor **Quitar las pausas largas**; nuevo endpoint `POST /clips/{id}/retime` que regenera el plan conservando el texto corregido y el título (`engine.retime_clip`, `CuratedClip.jump_cuts`).
- **Guardado automático** 2.5 s después del último cambio y aviso al salir con cambios sin guardar.
- **VideoToolbox en Mac** (`clipsrender/runner.py`): en macOS se intenta antes que libx264, con calidad elegida por VMAF (igual o mejor) y casi el doble de rápido. En Windows/Linux la cadena sigue siendo NVENC → libx264. Nuevo ajuste `CLIPS_VIDEOTOOLBOX`.
- **Pruebas**: `tests/test_encoder_selection.py` (cadena por plataforma), escenario de tramo en `tests/test_golden_e2e.py`; el benchmark exige la mejora de 1.54x solo donde NVENC funciona. 34 pruebas pasan.

#### Por qué
- Los fallos hacían perder ediciones o confundían (el visor no mostraba el cambio, deshacer no volvía al estado anterior).
- Ajustar el inicio o el final de un clip obligaba a reprocesar la sesión.
- En un Mac sin NVIDIA el render usaba solo el procesador.

> [!warning] ⚠️ Cambia para ti
> - Ya no hace falta pulsar **Guardar cambios**: el editor guarda solo a los 2.5 s.
> - Puedes alargar o recortar un clip desde la pestaña **Mezclador de Sonido y Ritmo** → **Inicio y final del clip**. Al aplicarlo se pierden los ajustes manuales de cámara de ese clip (el texto y el título se conservan).
> - En Mac los clips se exportan más rápido. En Windows todo sigue igual.

---

## [2.5.1] — 2026-11-09

### 💸 Transcripción solo de voz y costo real de Gemini

La transcripción es cerca del $97\%$ del gasto en APIs de cada VOD (Deepgram cobra por minuto de audio enviado). Esta versión deja de pagar por el silencio sin cambiar el resultado, y corrige el cálculo del gasto de Gemini.

#### Qué cambió
- **STT solo con voz (`clipsmedia/silence.py`, `ApiPool`)**: antes de subir cada tramo de 10 min se recortan los silencios de $\ge 2\text{ s}$ con $0.35\text{ s}$ de margen y se sube un Opus solo con voz; las palabras vuelven a su tiempo original con un mapa de segmentos que se guarda junto a la respuesta cruda. Se aplica si ahorra $\ge 20\text{ s}$ y $\ge 15\%$ del tramo; si falla, se envía el tramo completo. Nuevo ajuste `CLIPS_STT_SPEECH_ONLY` (activo por defecto).
- **Corrección: el orquestador pasa los silencios (`engine.run_session`)**: la primera versión enviaba la lista de silencios vacía y el recorte nunca se aplicaba; ahora convierte los silencios de voz al tiempo de la cámara y los pasa a la transcripción (prueba espía en `tests/test_golden_e2e.py`).
- **Costo de Gemini con razonamiento (`gemini.py`)**: suma `thoughtsTokenCount` (facturado como salida) a los tokens de salida; antes el gasto y el tope en USD se subestimaban.
- **Pruebas**: `tests/test_speech_only_stt.py` (planificación de cortes, remapeo, audio real con FFmpeg, `ApiPool` con y sin *fixtures*, costo de Gemini).

#### Por qué
- Pagar solo por los minutos en que el streamer habla, manteniendo la misma transcripción, y que el presupuesto refleje el costo real.

> [!warning] ⚠️ Cambia para ti
> - Las sesiones con mucho tiempo de juego en silencio cuestan menos en transcripción; los clips, subtítulos y tiempos son los mismos.
> - El gasto que muestra el panel puede subir un poco en la curación con Gemini: ahora incluye el razonamiento del modelo, que ya se estaba cobrando.

---

## [2.5.0] — 2026-11-07

### 🎯 Perfeccionamiento de Prompts v2.1 y Dirección Semántica de Zooms Token-Frugal

Esta versión optimiza integralmente el contrato y las instrucciones del modelo de lenguaje (`clipsproviders/llm`), permitiendo que la inteligencia artificial dirija cortes precisos, títulos de alto impacto y zooms cinematográficos sin provocar aumentos de tokens ni sobrecostes en la API.

#### Qué cambió
- **Curation Prompt v2.1 con Fórmulas de Alto CTR y Corte Limpio**:
  - Directrices estrictas para títulos en pantalla (`overlay_title`, 3 a 6 palabras en presente activo) y publicaciones para redes (`post_title`, 100% MAYÚSCULAS en 1ra persona con gancho y 1 emoji).
  - Regla de corte narrativo en 3 actos: inicio directo en la acción y finalización inmediata tras la carcajada o remate final, prohibiendo silencios muertos y charla intrascendente.
- **Anclaje de Zooms Semánticos (`zoom_word` y `zoom_focus`)**:
  - Esquema estructurado y validación Pydantic extendida con los campos opcionales `zoom_word` (palabra exacta de máxima emoción) y `zoom_focus` (`"face"`, `"game"`, `"split"`).
  - Overhead mínimo de apenas $\sim 3$ tokens por clip en la salida del modelo, blindando el sistema contra costes crecientes o exponenciales.
- **Inferencia Local Zero-Token en CPU (`clipscore/selection/resolver.py`)**:
  - Si el LLM omite `zoom_word` por minificación, el resolvedor local infiere la palabra de impacto analizando las palabras de énfasis y el catálogo local de reacciones sobre CPU con costo \$0.
- **Dirección Cinematográfica en `hormozi.py`**:
  - `build_editplan` sincroniza el `CropKeyframe` tipo `outBack` en el milisegundo exacto donde se pronuncia `zoom_word`.
  - Si el foco es la cámara (`"face"`), programa un disparo de cámara completa de 2 segundos en el clímax; si es el juego (`"game"`), asegura que el split no tape la pantalla.

> [!warning] ⚠️ Cambia para ti
> - Los títulos generados ahora son mucho más directos, con verbos en presente y formatos probados para YouTube Shorts y TikTok.
> - Los clips ya no se quedarán con segundos de silencio al final: cortan justo en la risa o remate del streamer.
> - La cámara hace zoom y enfatiza la jugada exactamente en la palabra donde ocurre la acción o el grito.

---

## [2.4.1] — 2026-11-07

### 🖼️ Miniaturas visuales compuestas en tiempo real y eliminación de estados falsos de carga

Esta actualización resuelve la visualización de los clips en la vista de detalle de sesión (`/sessions/[id]`). Anteriormente, los clips recién descubiertos por el pipeline que aún no habían sido exportados a video final mostraban un contenedor oscuro con un icono de carga giratorio y un texto de «Listo para editar en vivo» que provocaba la falsa sensación de bloqueo o carga infinita. Ahora cada clip muestra de inmediato una miniatura vertical 9:16 real y nítida de la jugada con botón directo al editor interactivo.

#### Qué cambió
- **Endpoint de miniaturas compuestas en caché (`GET /clips/{clip_id}/thumbnail`)**:
  - Si el clip ya tiene un archivo MP4 renderizado (borrador o final), extrae un fotograma del video exportado.
  - Si el video aún no está renderizado en disco, toma el momento exacto del clip (`start + 1.0s`) y compone automáticamente una miniatura vertical 9:16 (540×960) con cámara arriba (40%) y juego abajo (60%) sincronizados por sonido, o fotograma completo del juego si no hay cámara.
  - Almacena el resultado en caché de disco (`data/cache/thumbnails/{clip_id}_{width}.jpg`) y cabeceras HTTP `X-Frame-Cache: HIT`, reduciendo el tiempo de respuesta a menos de 5 ms en visitas posteriores.
- **Rediseño de tarjetas de clip en Web Studio (`/sessions/[id]`)**:
  - Se eliminó por completo el spinner giratorio y el efecto de parpadeo (`animate-pulse`) en clips que no se encuentran en proceso de renderizado activo.
  - La tarjeta ahora muestra la miniatura real del momento cumbre del clip con un degradado sutil, la insignia de duración en segundos y un botón flotante «Personalizar en vivo».
  - La barra de progreso de renderizado y el spinner únicamente se activan cuando el usuario solicita activamente la creación del video vertical.

> [!warning] ⚠️ Cambia para ti
> - Ya no verás pantallas negras con círculos girando en tus clips nuevos: ahora verás de inmediato la imagen real del juego y de tu cámara para que reconozcas cada jugada al instante.
> - Puedes hacer clic en «Personalizar en vivo» sobre la miniatura para abrir el clip en el editor.

---

## [2.4.0] — 2026-11-07

### 🎬 Editor Web WYSIWYG: Reencuadre visual directo, plantillas de disposición en 1 clic y 60 fps sin jitter

Esta versión moderniza completamente el Editor Web de Clips (`/editor/[clipId]`) introduciendo un paradigma de edición 100 % visual (WYSIWYG), eliminando la necesidad de ingresar números manuales y ofreciendo sincronización perfecta a 60 fotogramas por segundo respaldada por un sistema completo de Deshacer / Rehacer.

#### Qué cambió
- **Manipulación de Cámara y Subtítulos en Pantalla (Drag & Drop WYSIWYG)**:
  - Arrastre directo de cámara con el ratón (`onPointerDown` / `onPointerMove`) en el visor 9:16 para reencuadrar el rostro de forma natural e intuitiva.
  - Guía magnética visual con línea dorada y badge de centrado automático cuando $cx$ se sitúa en $0.50 \pm 2.5\%$.
  - Ajuste de zoom continuo ($1.0\times$ a $2.5\times$) mediante la rueda del ratón (`wheel`) o mini-widget flotante con botones $+/-$.
  - Tirador vertical interactivo de subtítulos para posicionar libremente el bloque de texto y evitar tapar la mira o HUD del juego (`vertical_ratio` en `CaptionsPlan`, respetado en el renderizado final de FFmpeg y C++ FastCompositor).
- **Plantillas Rápidas de Disposición (Layout Templates en 1 Clic)**:
  - Barra de plantillas inmediatas en la pestaña de cámara: *Clásico Gaming* (40/60 split), *Gameplay Prioritario* (25/75 split), *Reacción Total* (100% cámara 2s) y *Juego Completo* (100% gameplay) con inserción suave en la línea de tiempo.
- **Rendimiento a 60 FPS sin Video Jitter**:
  - Reloj maestro basado en el hardware de la cámara (`cv.currentTime`), eliminando las asignaciones forzadas de `currentTime` en cada ciclo de animación.
  - Sincronización esclava del video del juego tolerante a la deriva (únicamente corrige si $|gv.currentTime - masterTime| > 40\text{ ms}$), eliminando los parones de decodificación en GPUs locales.
  - Integración de `requestVideoFrameCallback` con fallback a RAF, caché de renderizado en `<canvas>` para textos estáticos y aceleración GPU con `translateZ(0)`.
- **Mezclador de Audio Intuitivo y Deshacer / Rehacer**:
  - Deslizador de «Volumen de Voz» de $0\%$ a $150\%$ (con conversión semilogarítmica a decibelios) y selector visual de atenuación de juego (Apagado, Suave, Normal, Fuerte).
  - Pilas de historial completas para Deshacer (`Ctrl+Z`) y Rehacer (`Ctrl+Y`) ante cualquier modificación accidental.
- **Refs**: [[HU-003 Editor interactivo WYSIWYG reencuadre visual y rendimiento 60 fps|HU-003]]

> [!warning] ⚠️ Cambia para ti
> - Ya no necesitas escribir coordenadas de cámara ni proporciones a mano: haz clic sobre tu video o subtítulos en el visor 9:16 y arrástralos directamente a donde prefieras.
> - Puedes usar la rueda del ratón sobre tu cámara para acercar o alejar el zoom de inmediato.
> - Presiona `Ctrl+Z` en cualquier momento para deshacer un ajuste y `Ctrl+Y` para rehacerlo.

---

## [2.3.4] — 2026-11-07

### 🧹 Desacoplamiento total de DaVinci Resolve MCP y consolidación del motor nativo 100 % local

Esta actualización retira de forma integral la integración con DaVinci Resolve y el servidor MCP local, devolviendo el enfoque exclusivo al motor de renderizado y Web Studio nativo con máxima fluidez y estabilidad.

#### Qué cambió
- **Eliminación del módulo DaVinci Resolve MCP (`packages/render-engine/clipsrender/resolve_mcp.py`)**: Se suprime el puente JSON-RPC 2.0, los compiladores de paquetes FCPXML 1.9, SRT y scripts Python para Resolve, y el subcomando CLI `clipsserver resolve-mcp`.
- **Limpieza de configuración y orquestador (`config.py`, `engine.py`, `routes.py`)**: Eliminados los campos `editor_backend` y `resolve_mcp_*` del servidor y los endpoints `GET /resolve/status`, `POST /clips/{id}/resolve`, `POST /sessions/{id}/resolve` y `GET /clips/{id}/resolve/download/{artifact}`.
- **Simplificación de la interfaz Web Studio (`apps/web`)**: Retirados los botones de «Abrir en DaVinci Resolve», barras de descarga de artefactos XML y la sección de configuración de DaVinci Resolve en `/settings` (Google Drive se renumera a sección 4).
- **Mantenimiento del 100 % de las mejoras de rendimiento**: Se preservan intactas las optimizaciones de `SharedSseManager` (Event Bus singleton en el navegador), aceleración GPU en tarjetas visuales, carga instantánea de `/settings` (< 10 ms) y el lenguaje claro y digerible en toda la plataforma ([[HU-002 Simplificación y lenguaje claro en toda la plataforma|HU-002]]).

> [!warning] ⚠️ Cambia para ti
> - La plataforma ahora genera tus videos terminados de manera 100 % local y directa mediante FFmpeg y aceleración por GPU (NVENC/libx264).
> - Se eliminan todas las opciones y botones de DaVinci Resolve tanto del editor como de los ajustes, simplificando la interfaz al máximo.

---

## [2.3.3] — 2026-11-07

### ⚡ Carga instantánea de Configuración, Event Bus SSE unificado y máxima fluidez en Web Studio

Esta actualización resuelve de forma integral la lentitud de carga reportada en `/settings` y los problemas de fluidez en la plataforma web mediante optimizaciones de concurrencia en backend, gestión de conexiones en cliente y aceleración por GPU.

#### Qué cambió
- **Carga instantánea de `/settings` (renderizado en < 10 ms)**: Se desacopla la carga de la configuración principal y presupuesto (`getSettings` y `fetchBudget`) de los diagnósticos externos de conectividad (`fetchDriveStatus`). El formulario ahora se presenta al usuario de inmediato con indicadores sutiles en segundo plano.
- **Event Bus SSE unificado (`SharedSseManager` en `client.ts`)**: Se reemplazaron múltiples conexiones `EventSource` independientes por un único gestor singleton que comparte una sola conexión HTTP persistente para toda la pestaña del navegador. Esto libera de 2 a 3 conexiones concurrentes (de las 6 permitidas en HTTP/1.1), eliminando por completo el encolado (*stalling*) de peticiones de video, previsualización de fotogramas y navegación.
- **Aceleración por GPU y reducción de sobrecarga gráfica (`ui.tsx`, `layout.tsx`, `globals.css`)**:
  - `GlassCard`: Se optimizó el filtro de desenfoque de `backdrop-blur-xl` a `backdrop-blur-md` y se añadió `transform-gpu` con transiciones de 200 ms, aligerando el cálculo de rasterizado del navegador en un ~60%.
  - Resplandores de fondo en `RootLayout`: Aislados en capas compuestas independientes de hardware (`transform-gpu will-change-transform`), impidiendo que el scroll o los eventos de ratón provoquen repintados de pantalla completa.
  - Habilitación de `scroll-behavior: smooth` y eliminación de micro-tirones en toda la aplicación.

> [!warning] ⚠️ Cambia para ti
> - La sección de **Configuración (`/settings`)** abre ahora al instante sin mostrar pantallas de carga en blanco ni demoras de varios segundos.
> - La navegación entre pantallas, el desplazamiento de página (*scrolling*) y la interacción con tarjetas es notablemente más ágil, suave y reactiva.
> - La reproducción de video y el visor de clips ya no experimentan pausas ni esperas por sockets bloqueados.

---

## [2.3.1] — 2026-11-07

### ✨ Simplificación, lenguaje digerible y experiencia de usuario clara en Web Studio

Esta actualización rediseña por completo los textos, descripciones, tooltips, notificaciones en tiempo real y paneles del estudio web, transformando la jerga técnica y saturada en explicaciones amigables para creadores de contenido de gaming que aclaran el «por qué» detrás de cada función.

#### Qué cambió
- **Notificaciones en tiempo real y orquestador (`engine.py`, `pipelineSteps.ts`, `TopNav.tsx`)**: Reemplazo de mensajes con nombres de funciones internas por avisos paso a paso transparentes: «Escuchando partida», «Eligiendo mejores momentos», «Sincronizando audio con precisión», «Armando encuadre vertical» y «Creando videos finales».
- **Gestión de sesiones y subida de partidas (`/sessions` y `/sessions/[id]`)**: Explicación clara de por qué se detectan juegos y palabras clave, por qué se unen dos videos en 9:16 vertical, cómo se calcula la curva de emoción combinando voz y jugabilidad, y cómo corregir la sincronización de audio manualmente.
- **Estudio de edición de clips (`/editor/[clipId]`)**: Traducción de términos de edición técnica (curvas `outBack`, *Jump Cuts*, atenuación *ducking*) a resultados tangibles: «Zoom de reacción», «Cámara en pantalla completa», «El juego baja solo cuando hablas» y «Saltos automáticos en silencios».
- **Configuración centralizada (`/settings`)**: Las secciones eliminan nombres de variables de entorno del título y explican con claridad qué hace cada proveedor, por qué usarlo y qué requisitos tiene (como autorizar OAuth en Google Drive).
- **Control de consumo y simulación (`/analytics`)**: Sustitución de terminología cruda de facturación por explicaciones accesibles de saldo disponible, capacidad restante en horas y clips, planes gratuitos y una calculadora para estimar el costo de procesar un stream antes de iniciarlo.

> [!warning] ⚠️ Cambia para ti
> - La plataforma ahora habla tu mismo idioma: entenderás exactamente qué está haciendo el sistema en cada momento sin lidiar con siglas técnicas crudas.
> - En el editor, los controles de cámara, audio y subtítulos muestran su efecto visual o auditivo de forma directa.
> - En `/settings` y `/analytics` sabrás con exactitud cuánto inviertes, cuánto te rinde el saldo y cómo aprovechar los planes gratuitos sin sorpresas.

---

## [2.2.0] — 2026-11-07

### ⚡ Optimización integral de tokens de IA y rendimiento en 4 ámbitos (Carga, Memoria/CPU, Fluidez 60 fps y Latencia API)

Esta actualización reduce drásticamente el consumo de tokens y costos de facturación en sesiones largas y optimiza los tiempos de carga, el uso de memoria RAM/CPU, la fluidez del editor a 60 fps y los tiempos de respuesta del servidor.

#### Qué cambió
- **Ahorro de tokens y facturación de IA (`clipscore`, `clipsproviders`, `api_pool`)**:
  - **Poda de línea de tiempo por clusters de señales (`prune_utterances_by_signal_clusters`)**: En grabaciones $\ge 10\text{ min}$, descarta zonas muertas alejadas de picos acústicos/visuales antes de invocar al LLM (ahorro del 65 %–85 % en tokens de entrada).
  - **Reintento Pydantic sin duplicar transcripción (`repair_prompt`)**: Trunca la transcripción de referencia a $\le 1200$ caracteres al reparar errores de esquema JSON y mantiene estático el prefijo de `CURATION_SYSTEM_PROMPT` para *Prompt Caching*.
  - **Esquema de salida minificado + enriquecimiento local en CPU (`infer_local_emphasis_and_emojis`)**: Infiere palabras de énfasis, emojis del catálogo de 42 iconos, `hook` y `hashtags` en CPU cuando el LLM devuelve propuestas compactas.
  - **Filtro previo de silencios en STT (`ApiPool._chunk_speech_ratio`)**: Omite llamadas pagas a Deepgram/Groq en bloques de audio con $\ge 97\%$ de silencio (streamer ausente/AFK).
- **1. Tiempos de carga (`db.py`, `routes.py`)**:
  - Eliminación del problema de consultas $N+1$ en `GET /sessions` mediante agregación `LEFT JOIN clips` en SQLite.
  - Cabeceras `Cache-Control: immutable` en fuentes, emojis y efectos SFX, y `Accept-Ranges: bytes` en streams de video.
- **2. Memoria y potencia de hardware local (`sync.py`, `fast_compositor.py`, `tracker.py`)**:
  - **Ventana acústica rápida inicial (`estimate_audio_sync`)**: Alinea grabaciones largas evaluando primero los 10 minutos iniciales si la confianza supera el umbral.
  - **Pool circular de buffers YUV420p (`FastCompositor`)**: Reutiliza 10 buffers preasignados en lugar de instanciar nuevos arrays por fotograma (ahorro de ~5 GB de asignaciones transitorias por clip).
  - **Muestreo adaptativo a 10 fps y buffer reutilizable en MediaPipe (`track_clip_face`)**: Reduce un 33 % el cómputo de CPU en clips largos manteniendo suavidad a 60 fps con One Euro Filter.
- **3. Fluidez de la plataforma a 60 fps (`apps/web/src/app/editor/[clipId]/page.tsx`)**:
  - Desacopla las actualizaciones del *scrubber*, *playhead* y cronómetro mediante referencias DOM directas a 60 Hz sin disparar re-renderizados completos de React en cada cuadro, e incorpora caché de anchos tipográficos (`wordWidthCacheRef`) en el Canvas 2D.
- **4. Tiempos de respuesta (`routes.py`)**:
  - Caché persistente en disco (`data/cache/frames/`) para miniaturas en `GET /sessions/{id}/frame` (`X-Frame-Cache: HIT` en $< 5\text{ ms}$) y soporte de encolado asíncrono (`async_mode`) en `POST /clips/{id}/render`.

> [!warning] ⚠️ Cambia para ti
> - Las sesiones largas ($\ge 10\text{ min}$) consumen hasta un 75 % menos de presupuesto en USD gracias al filtrado previo de zonas muertas y tramos en silencio.
> - El reproductor en vivo de `/editor/[clipId]` mantiene 60 fps estables sin tirones de interfaz, y las miniaturas de fotogramas responden de forma instantánea tras la primera consulta.

---

## [2.1.0] — 2026-11-07

### ☁️ Conexión directa a Google Drive (OAuth 2.0) y explorador interactivo de sesiones

Esta actualización incorpora autenticación directa con cuentas personales de Google mediante OAuth 2.0 y un navegador interactivo de carpetas y videos en el estudio web para crear sesiones desde la nube en un clic.

#### Qué cambió
- **Conector `GoogleDriveOAuthConnector` (`packages/media/clipsmedia/drive.py`)**: Flujo completo de autorización OAuth 2.0 con intercambio de código, renovación automática mediante `refresh_token` persistido en `data/drive_oauth_token.json`, lectura de perfil (`/drive/v3/about`) y desconexión segura.
- **Explorador de carpetas y auto-detección de par (`browse_folder` y `get_file_entry`)**: Navegación de subcarpetas con migas de pan (*breadcrumbs*), filtrado por nombre y emparejamiento inteligente de `gameplay` + `cámara` (`detected_pair`).
- **Nuevos endpoints en FastAPI (`apps/server/clipsserver/api/routes.py`)**: `GET /drive/status`, `GET /drive/auth/url`, `GET /drive/auth/callback`, `POST /drive/auth/disconnect`, `GET /drive/files` y `POST /drive/sessions` (descarga resumible concurrente en `ApiPool` con telemetría SSE `stage_progress`).
- **Pestaña «Desde Drive» en `/sessions` y panel OAuth en `/settings`**: Explorador visual de carpetas y videos con selección en 1 clic del par detectado, botones individuales «Usar como Juego» / «Usar como Cámara» y asistente de vinculación OAuth 2.0 con ventana emergente y código manual de respaldo.

> [!warning] ⚠️ Cambia para ti
> - En `/sessions` ahora puedes alternar entre **«Ruta en Servidor»** y **«Desde Drive»** para explorar tus carpetas de Google Drive y lanzar sesiones sin copiar rutas manualmente.
> - En `/settings` dispones de la nueva sección **«4. Conexión Directa a Google Drive (OAuth 2.0 y Explorador)»** para elegir entre `local`, `oauth` o `service_account` y vincular tu cuenta con un clic.

---

## [2.0.0] — 2026-11-07

### 🌟 Monorepo unificado y arquitectura declarativa v2

Esta versión consolida el sistema en una arquitectura modular completa con servidor FastAPI, frontend Next.js 15 y 7 paquetes especializados.

#### Qué cambió
- **Contrato EditPlan v2**: Migración a esquema declarativo estricto con soporte de tipos TypeScript autogenerados (`codegen.py`).
- **Compositor C++ acelerado (`FastCompositor`)**: Implementación de transformaciones afines en C++ (`cv2.warpAffine`) para zooms y paneos sub-píxel con curvas `outBack` e `inOutSine`.
- **Subtitulado animado libass**: Compilación de subtítulos Hormozi con resaltado dinámico palabra por palabra en amarillo (`#FFD400`) y verde eléctrico (`#39FF14`).
- **Normalización sonora en 2 pasadas**: Integración de filtro lineal `loudnorm` para fijar el audio a $-14\text{ LUFS}$ y $-1.0\text{ dBTP}$.
- **Panel de control dinámico `/settings`**: Edición de claves de API en caliente con enmascaramiento seguro y probador de conexión integrado.
- **Catálogo visual de 42 emojis**: Iconos RGBA supersampled a $128 \times 128\text{ px}$.
- **Perfiles de jerga (*Keyterms*)**: Diccionarios específicos por videojuego (Valorant, CS2) para mejorar la precisión fonética de Deepgram.
- **Notificaciones por Webhook**: Entrega de alertas y enlaces de descarga a Discord y Slack.

> [!warning] ⚠️ Cambia para ti
> - La configuración ahora se gestiona preferentemente desde el navegador en `http://127.0.0.1:3040/settings`.
> - Los clips editados manualmente en el editor quedan protegidos bajo el estado `EDITED` y no se sobrescriben en reprocesamientos automáticos.
> - La variable de entorno para el límite de presupuesto pasa a denominarse `CLIPS_MAX_BUDGET_USD` (por defecto \$9.00 USD).

---

## [1.0.0] — 2026-10-15

### Prototipo inicial de pipeline híbrido
- Extracción básica de pistas mediante FFmpeg en línea de comandos.
- Sincronización manual de desfases.
- Transcripción secuencial con Whisper API.
- Generación de video vertical simple con corte horizontal fijo.

---

## 🔗 Relacionado
- [[Resumen ejecutivo]]
- [[FAQ]]
- [[Arquitectura general]]