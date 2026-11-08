---
titulo: Historial de cambios
tipo: cambios
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/cambios, area/general]
---

# Historial de cambios de FarmClips

> [!abstract] En pocas palabras
> Registro cronológico de las versiones de FarmClips, nuevas funcionalidades, optimizaciones de rendimiento y ajustes en la arquitectura del sistema.

---

## [2.3.2] — 2026-11-07 (Versión actual)

### ⚡ Exportación no bloqueante y detección de proyecto activo en DaVinci Resolve

Esta actualización resuelve de raíz los tiempos de espera y congelamientos del navegador reportados al exportar clips o sesiones completas hacia DaVinci Resolve mientras la aplicación o un proyecto ya se encuentran abiertos en el equipo local.

#### Qué cambió
- **Detección no invasiva de proyecto activo (`resolve_open_project`)**: Comprueba `pm.GetCurrentProject()` antes de forzar la apertura de un nuevo proyecto. Si el usuario ya está trabajando en un proyecto en DaVinci Resolve, ClipsApp reutiliza directamente el proyecto activo sin intentar cerrarlo, eliminando diálogos modales de guardado y bloqueos del hilo de scripting.
- **Organización limpia en bandeja dedicada (`FarmClips` bin)**: Los medios importados (gameplay, cámara y efectos de audio) se agrupan dentro de una subcarpeta específica del MediaPool, evitando desorden en la raíz del proyecto del usuario.
- **Despacho asíncrono no bloqueante (`async_mode: true`)**: La API (`POST /clips/{clip_id}/resolve` y `POST /sessions/{session_id}/resolve`) responde de inmediato en menos de 50 ms devolviendo el estado `queued`. Las operaciones de importación y construcción de la línea de tiempo se ejecutan en segundo plano y transmiten su progreso paso a paso mediante eventos SSE (`resolve_mcp_progress` y `clip_resolve_exported`).
- **Fluidez absoluta en Web Studio**: Se liberan las conexiones concurrentes del navegador (límite de 6 en HTTP/1.1), impidiendo que la reproducción de video en el reproductor, el *scrubbing* en el `<canvas>` a 60 fps y los endpoints de audio queden en cola de espera.
- **Protección con timeout de conexión IPC (`_try_connect_resolve_scripting`)**: Se introduce una caché con TTL de 3.0s y un límite estricto de 1.6s en hilo secundario para la detección de `DaVinciResolveScript`, evitando cuelgues si DaVinci Resolve no tiene scripting externo habilitado.

> [!warning] ⚠️ Cambia para ti
> - Al hacer clic en **«Editar en DaVinci Resolve (MCP)»**, la interfaz de Web Studio ya no se queda cargando indefinidamente ni ralentiza la página; puedes seguir previsualizando o reproduciendo videos de inmediato mientras Resolve procesa la línea de tiempo.
> - Si ya tienes un proyecto abierto en DaVinci Resolve, ClipsApp agregará la línea de tiempo vertical y los medios en la carpeta `FarmClips` de ese mismo proyecto sin molestarte con advertencias de guardado.

---

## [2.3.1] — 2026-11-07

### ✨ Simplificación, lenguaje digerible y experiencia de usuario clara en Web Studio

Esta actualización rediseña por completo los textos, descripciones, tooltips, notificaciones en tiempo real y paneles del estudio web, transformando la jerga técnica y saturada en explicaciones amigables para creadores de contenido de gaming que aclaran el «por qué» detrás de cada función.

#### Qué cambió
- **Notificaciones en tiempo real y orquestador (`engine.py`, `pipelineSteps.ts`, `TopNav.tsx`)**: Reemplazo de mensajes con nombres de funciones internas por avisos paso a paso transparentes: «Escuchando partida», «Eligiendo mejores momentos», «Sincronizando audio con precisión», «Armando encuadre vertical» y «Creando videos finales».
- **Gestión de sesiones y subida de partidas (`/sessions` y `/sessions/[id]`)**: Explicación clara de por qué se detectan juegos y palabras clave, por qué se unen dos videos en 9:16 vertical, cómo se calcula la curva de emoción combinando voz y jugabilidad, y cómo corregir la sincronización de audio manualmente.
- **Estudio de edición de clips (`/editor/[clipId]`)**: Traducción de términos de edición técnica (curvas `outBack`, *Jump Cuts*, atenuación *ducking*) a resultados tangibles: «Zoom de reacción», «Cámara en pantalla completa», «El juego baja solo cuando hablas» y «Saltos automáticos en silencios».
- **Configuración centralizada (`/settings`)**: Las 5 secciones eliminan nombres de variables de entorno del título y explican con claridad qué hace cada proveedor, por qué usarlo y qué requisitos tiene (como activar scripting en DaVinci Resolve o autorizar OAuth en Google Drive).
- **Control de consumo y simulación (`/analytics`)**: Sustitución de terminología cruda de facturación por explicaciones accesibles de saldo disponible, capacidad restante en horas y clips, planes gratuitos y una calculadora para estimar el costo de procesar un stream antes de iniciarlo.

> [!warning] ⚠️ Cambia para ti
> - La plataforma ahora habla tu mismo idioma: entenderás exactamente qué está haciendo el sistema en cada momento sin lidiar con siglas técnicas crudas.
> - En el editor, los controles de cámara, audio y subtítulos muestran su efecto visual o auditivo de forma directa.
> - En `/settings` y `/analytics` sabrás con exactitud cuánto inviertes, cuánto te rinde el saldo y cómo aprovechar los planes gratuitos sin sorpresas.

---

## [2.3.0] — 2026-11-07

### 🎞️ Edición externa en DaVinci Resolve mediante MCP local y arquitectura dual de edición

Esta versión incorpora un motor de edición híbrido que permite trasladar el montaje no lineal de los clips curados (`EditPlan` v2) hacia **DaVinci Resolve** ejecutándose localmente mediante **Model Context Protocol (MCP)**, manteniendo disponible el motor nativo (`FastCompositor` + Web Studio) como opción local o combinada.

#### Qué cambió
- **Servidor MCP JSON-RPC 2.0 y puente con `DaVinciResolveScript` (`packages/render-engine/clipsrender/resolve_mcp.py`, `clipsserver resolve-mcp`)**:
  - Servidor MCP integrable por `stdio` o HTTP con 6 herramientas declarativas (`resolve_get_status`, `resolve_open_project`, `resolve_import_media`, `resolve_build_vertical_timeline`, `resolve_add_timeline_markers`, `resolve_trigger_render`).
  - Detección automática en Windows, macOS y Linux de la instalación local de DaVinci Resolve, librería `fusionscript.dll` / `.so`, módulos de scripting y estado del proceso `Resolve.exe`.
- **Compilador de paquetes multipista para DaVinci Resolve (`compile_fcpxml_v19`, `compile_srt`, `compile_resolve_python_script`)**:
  - Genera en `data/sessions/<session_id>/clips/<clip_id>/resolve/` un timeline `.fcpxml` v1.9 vertical (`1080×1920` a 60 fps) con pistas separadas (`V1` Gameplay, `V2` Facecam sincronizada con recorte y zoom de MediaPipe, `V3` Títulos, `A1` Micrófono, `A2` Juego con *ducking*, `A3` Efectos SFX), marcadores de IA por palabra de énfasis y emojis, subtítulos `.srt` y `.ass`, y el script autónomo `resolve_build_timeline.py`.
- **Orquestador y nuevos endpoints REST (`engine.py`, `routes.py`, `config.py`)**:
  - Soporte de `CLIPS_EDITOR_BACKEND=local|resolve_mcp|both` y `CLIPS_RESOLVE_MCP_MODE=auto|mcp_stdio|mcp_http|direct_script|bundle_only`.
  - Nuevos endpoints `GET /resolve/status`, `POST /clips/{clip_id}/resolve`, `POST /sessions/{session_id}/resolve` y `GET /clips/{clip_id}/resolve/download/{artifact}`.
- **Integración completa en Web Studio (`apps/web`)**:
  - Botón **«Editar en DaVinci Resolve (MCP)»** y barra de descarga directa de artefactos (`FCPXML v1.9`, `SRT`, `ASS`, `Script .py`, `Plan MCP`) en `/editor/[clipId]`.
  - Exportación en lote de toda la sesión a DaVinci Resolve en `/sessions/[id]`.
  - Nueva sección **«4. Motor de Edición de Video y DaVinci Resolve (MCP Local)»** en `/settings` con diagnóstico en vivo del entorno Resolve local.

> [!warning] ⚠️ Cambia para ti
> - En `/settings` puedes elegir si deseas editar tus clips con el **Motor Local integrado** (`local`), enviarlos directamente a **DaVinci Resolve vía MCP** (`resolve_mcp`) o usar **ambos motores simultáneamente** (`both`).
> - En `/editor/[clipId]` y `/sessions/[id]` dispones del botón **«Editar en DaVinci Resolve (MCP)»** para abrir el timeline vertical multipista en DaVinci Resolve o descargar los archivos `.fcpxml`, `.srt` y `.py` listos para importar incluso con DaVinci Resolve cerrado.

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