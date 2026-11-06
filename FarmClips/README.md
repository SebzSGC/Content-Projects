# FarmClips — Arquitectura Híbrida: IA por API, Proceso Local

Convierte grabaciones largas de gaming separadas (`gameplay.mp4` + `camara.mp4`) en **Shorts verticales 9:16 (`1080×1920`, −14 LUFS)** listos para YouTube Shorts, TikTok y Reels con estilo **Hormozi Gaming**, combinando **IA en la nube por API** (transcripción y curación narrativa) con **procesamiento multimedia 100 % local** (FFmpeg, sincronización FFT, MediaPipe en CPU por clip y NVENC/libx264).

---

## Principios implementados

1. **El video nunca sale de la máquina**: solo viaja audio Opus mono 16 kHz (`~7 MB/h`) del micrófono de la cámara a STT y una línea de tiempo compacta de texto al LLM.
2. **Fuentes separadas (`gameplay.mp4` + `camara.mp4`)**: sin separación de voces (Demucs), sin diarización (SpeechBrain), sin PANNs ni OCR pesado.
3. **El LLM elige por IDs de frase (`u0001`..`u9999`), el código corta al milisegundo**: el código local resuelve los IDs a tiempos exactos por palabra (`20–60 s`) y ajusta ataques acústicos a 100 Hz.
4. **Nunca se paga dos veces**: caché idempotente en SQLite (`artifacts` + `api_calls`) con respuestas crudas archivadas antes de normalizar y tope de presupuesto en USD (`CLIPS_MAX_BUDGET_USD=9.00` por defecto).
5. **Tracking facial por clip en CPU**: MediaPipe Face Detector (`blaze_face_short_range.tflite`) corre solo en los clips elegidos (`15 fps`, `640 px` por pipe de FFmpeg), con interpolación de huecos (`<1 s` / `>1 s`), filtro **One Euro**, zona muerta y simplificación **Ramer–Douglas–Peucker** guardada en Parquet.
6. **Servidor único + 3 pools separados**:
   - `ApiPool` (`asyncio` + `httpx`): limitador triple (concurrencia, RPM, unidades/hora), reintentos `429` (`Retry-After`), subdivisión automática de audio en `413` y cortacircuitos con respaldo (`Deepgram Nova-3 ↔ Groq whisper-large-v3-turbo`, `Gemini 3.5 Flash-Lite ↔ OpenAI-compat gpt-6-luna`).
   - `CpuPool` (`ProcessPoolExecutor`, `núcleos − 1`): señales en Parquet, envolventes 100 Hz, movimiento OpenCV 2 fps y MediaPipe.
   - `RenderPool` (cola con prioridad, `2–3` sesiones NVENC o `núcleos/4` `libx264` detrás de `RenderBackend`).
7. **Edición declarativa (`EditPlan` v2) + Mezclador Web Audio API**: el editor web (`/editor/[clipId]`) reproduce el `EditPlan` instantáneamente sobre las fuentes originales con CSS transforms, `<canvas>` a 60 fps, selector visual de 42 emojis supersampled y mezcla de audio en tiempo real (`Web Audio API` con `mic_gain_db`, ducking sidechain sobre pista limpia y disparo de SFX `boom.wav`), y exporta bajo demanda en `540p` (borrador) o `1080p` (final + reemplazo concurrente/resumible en `Salidas/`).
8. **Motor de composición acelerado (`cv2.warpAffine` C++ + `loudnorm` lineal en 2 pasadas)**: el renderizador compone paneos y zooms sub-píxel (`outBack` / `inOutSine`) directamente en C++ hacia `h264_nvenc` / `libx264` + `libass` estático, y normaliza el audio en 2 pasadas a `−14 LUFS` lineal, junto con perfiles automáticos de `keyterms` por juego, telemetría de HUD/Killfeed a 2 fps, webhooks (Discord / Slack / HTTP) y limpieza automática TTL de temporales.

---

## Estructura del Monorepo

```text
FarmClips/
  apps/
    web/              Next.js 15 Studio (/sessions, /sessions/[id], /editor/[clipId])
    server/           Servidor único FastAPI + Orquestador SQLite WAL + SSE + 3 Pools
  packages/
    styles/           Preset `hormozi-gaming`, fuente Montserrat ExtraBold, 42 emojis RGBA supersampled, keyterms por juego y SFX
    editplan/         Contrato EditPlan v2 (Pydantic + JSON Schema + generador TypeScript)
    core/             Señales (Parquet con HUD/Killfeed 2 fps), línea de tiempo compacta, selección por IDs, One Euro/RDP y director
    media/            FFmpeg/FFprobe multi-pista, Opus 16 kHz, silencedetect, sync FFT y conector Google Drive (resumible/paralelo)
    providers/        Adaptadores HTTP async (Deepgram Nova-3, Groq Whisper, Gemini 3.5, OpenAI-compat), resiliencia y webhooks
    tracking/         MediaPipe Face Detector en CPU por clip (15 fps / 640 px -> Parquet)
    render-engine/    Compositor rápido C++ (`cv2.warpAffine`) + ASS animado + `loudnorm` lineal 2 pasadas + filtergraph FFmpeg
  data/               SQLite (`clipsapp.db`), artefactos Parquet/JSON, respuestas crudas de API y espejo de Drive
  infra/              Script de arranque (`dev.ps1`), `Dockerfile` y `docker-compose.yml`
  tests/
    golden/           Generador y videos de referencia (`gameplay.mp4` + `camara.mp4`)
    fixtures/api/     Respuestas grabadas de Deepgram, Groq y Gemini para pruebas sin costo
```

---

## Inicio Rápido (Windows)

### 1. Configurar variables de entorno

```powershell
Copy-Item .env.example .env
# Edita .env con tus claves DEEPGRAM_API_KEY, GROQ_API_KEY, GEMINI_API_KEY (u OPENAI_API_KEY).
# Para probar sin gastar saldo en APIs, puedes definir:
#   CLIPS_STT_PRIMARY=fixture
#   CLIPS_LLM_PRIMARY=fixture
#   CLIPS_FIXTURES_DIR=tests/fixtures/api
```

### 2. Iniciar Servidor Híbrido + Estudio Web

```powershell
powershell -ExecutionPolicy Bypass -File infra\dev.ps1
```

- **Web Studio**: `http://127.0.0.1:3040`
- **API & SSE Server**: `http://127.0.0.1:8790/health`

### 3. Ejecutar pruebas completas (Unitarias + Resiliencia + Golden E2E con FFmpeg y MediaPipe)

```powershell
.\.venv\Scripts\pytest.exe -v
```

### 4. Regenerar contratos JSON Schema, TypeScript y OpenAPI

```powershell
.\.venv\Scripts\python.exe -m clipsserver.main codegen --web-dir apps/web
```
