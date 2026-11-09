---
titulo: Variables de Entorno
tipo: guia
estado: vigente
audiencia: [tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-09
etiquetas: [tipo/guia, area/configuracion]
---

# Diccionario de Variables de Entorno (`.env`)

> [!abstract] En pocas palabras
> Catálogo completo de parámetros de configuración que controlan el comportamiento de FarmClips, sus rutas locales, puertos de red, límites de gasto y proveedores de inteligencia artificial.

---

## 🌐 1. Servidor y Almacenamiento Local

| Variable | Valor por defecto | Descripción |
|---|:---:|---|
| `CLIPS_DATA_DIR` | `data` | Directorio local de almacenamiento de SQLite, artefactos y renders. |
| `CLIPS_SERVER_HOST` | `127.0.0.1` | Dirección IP de enlace para el servidor FastAPI. |
| `CLIPS_SERVER_PORT` | `8790` | Puerto TCP de escucha para la API y eventos SSE. |
| `CLIPS_PUBLIC_WEB_URL` | `http://127.0.0.1:3040` | URL pública o local del estudio web para enlaces de notificación. |
| `CLIPS_STYLE_PRESET` | `hormozi-gaming` | Preset de diseño audiovisual predeterminado. |
| `CLIPS_TEMP_TTL_DAYS` | `7.0` | Días de retención para purga automática de temporales Opus/WAV. |

---

## 💰 2. Control de Presupuesto y Límites

| Variable | Valor por defecto | Descripción |
|---|:---:|---|
| `CLIPS_MAX_BUDGET_USD` | `9.00` | Límite máximo acumulado en USD antes de bloquear peticiones de IA. |
| `CLIPS_AUTO_RENDER_MIN_SCORE` | `60.0` | Puntuación mínima (sobre 100) para exportar un clip en 1080p automáticamente. |
| `CLIPS_AUTO_RENDER_TOP_K` | `5` | Número máximo de clips que se renderizan automáticamente por sesión. |

---

## ⚡ 3. Hardware y Concurrencia de Pools

| Variable | Valor por defecto | Descripción |
|---|:---:|---|
| `CLIPS_CPU_WORKERS` | `núcleos - 1` | Número de procesos paralelos para cómputo numérico y tracking. |
| `CLIPS_USE_NVENC` | `true` | Habilita codificación por hardware en GPU NVIDIA. |
| `CLIPS_NVENC_SLOTS` | `3` | Sesiones de codificación simultáneas permitidas en la GPU. |
| `CLIPS_ENABLE_GAMEPLAY_MOTION`| `true` | Activa análisis visual de movimiento y Killfeed a 2 fps en el juego. |

---

## 🎙️ 4. Proveedores de Transcripción ([[Glosario#STT|STT]])

| Variable | Valor por defecto | Descripción |
|---|:---:|---|
| `CLIPS_STT_PRIMARY` | `deepgram` | Proveedor primario (`deepgram`, `groq` o `fixture`). |
| `CLIPS_STT_BACKUP` | `groq` | Proveedor secundario de contingencia. |
| `DEEPGRAM_API_KEY` | *(vacío)* | Clave de API de Deepgram. |
| `DEEPGRAM_MODEL` | `nova-3` | Modelo de reconocimiento fonético de Deepgram. |
| `GROQ_API_KEY` | *(vacío)* | Clave de API de Groq Cloud. |
| `GROQ_STT_MODEL` | `whisper-large-v3-turbo` | Modelo de Whisper ejecutado en hardware LPU de Groq. |
| `CLIPS_CHUNK_TARGET_SEC` | `600.0` | Tamaño objetivo en segundos para partir el audio Opus (10 min). |
| `CLIPS_STT_SPEECH_ONLY` | `true` | Envía a la transcripción solo los tramos con voz (recorta silencios $\ge 2\text{ s}$ y devuelve las palabras a su tiempo original). Reduce los minutos facturados. |

---

## 🧠 5. Proveedores de Selección ([[Glosario#LLM|LLM]])

| Variable | Valor por defecto | Descripción |
|---|:---:|---|
| `CLIPS_LLM_PRIMARY` | `gemini` | Proveedor primario (`gemini`, `openai_compat` o `fixture`). |
| `GEMINI_API_KEY` | *(vacío)* | Clave de API de Google AI Studio. |
| `GEMINI_MODEL` | `gemini-3.5-flash-lite` | Modelo de lenguaje de alta velocidad de Google. |
| `CLIPS_LLM_BACKUP` | `openai_compat` | Proveedor secundario de contingencia. |
| `OPENAI_API_KEY` | *(vacío)* | Clave de API para OpenAI o proveedores compatibles. |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | URL base para OpenAI, Ollama o vLLM. |
| `OPENAI_MODEL` | `gpt-6-luna` | Modelo a solicitar en el endpoint compatible. |

---

## ☁️ 6. Google Drive y Webhooks

| Variable | Valor por defecto | Descripción |
|---|:---:|---|
| `CLIPS_DRIVE_MODE` | `local` | Modalidad de Drive (`local`, `oauth` o `service_account`). |
| `CLIPS_DRIVE_LOCAL_DIR` | `data/drive_mirror` | Carpeta local vinculada a Google Drive en la máquina. |
| `CLIPS_DRIVE_CLIENT_ID` | *(vacío)* | Client ID de OAuth 2.0 en Google Cloud Console (modalidad `oauth`). |
| `CLIPS_DRIVE_CLIENT_SECRET` | *(vacío)* | Client Secret de OAuth 2.0 (persiste `refresh_token` en `data/drive_oauth_token.json`). |
| `CLIPS_DRIVE_SERVICE_ACCOUNT_JSON` | *(vacío)* | Ruta al archivo JSON de credenciales de Google Cloud (`service_account`). |
| `CLIPS_DRIVE_ROOT_FOLDER_ID` | *(vacío)* | ID alfanumérico de la carpeta raíz en Google Drive (`root` si se omite en `oauth`). |
| `CLIPS_DRIVE_POLL_SEC` | `15.0` | Frecuencia en segundos para buscar nuevas grabaciones. |
| `CLIPS_WEBHOOK_URL` | *(vacío)* | URL para notificaciones automáticas HTTP POST (Discord o Slack). |

---

## 🔗 Relacionado
- [[Referencia API REST y SSE]]
- [[Motor de Renderizado y Subtítulos]]
- [[Cómo configurar Proveedores de IA]]
- [[Despliegue y Ejecución]]