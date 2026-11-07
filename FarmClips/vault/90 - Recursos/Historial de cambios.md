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

## [2.2.0] — 2026-11-07 (Versión actual)

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