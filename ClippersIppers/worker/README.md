# gameclips — worker de procesamiento

Servicio en Python que convierte la grabación de un stream de videojuegos en **Shorts verticales 9:16** con el formato de referencia: **cámara del streamer arriba, gameplay abajo, título en la unión** y subtítulos opcionales palabra por palabra.

La interfaz de Next.js (`../src/app/sessions`) lo usa a través de `/api/worker/*`. Todo el trabajo pesado (horas de audio y video) corre aquí, en local y con GPU. La IA de texto solo recibe la transcripción y unos pocos fotogramas.

## Entradas soportadas

| Modo | Qué recibe | Notas |
|---|---|---|
| `split` (recomendado) | `gameplay.mkv` con **el audio mezclado** + `camara.mkv` | Cámara a resolución nativa. Si la cámara también trae una copia de la mezcla, la sincronización es exacta. |
| `composite` | Un solo video con la facecam encima (archivo local o **link de Kick**) | En la UI se marca dónde está la cámara y dónde el juego. De Kick se baja una copia de 480p para analizar y solo los tramos elegidos en 1080p para renderizar. |

### Grabar en OBS para el modo `split`
1. Grabación normal del gameplay en MKV (lleva la mezcla del stream).
2. Plugin **Source Record** sobre la fuente de la webcam, en la misma sesión de OBS. Si se puede, incluye el audio de la mezcla en ese archivo: no hace falta separarlo, solo sirve para sincronizar.

## Pipeline

```
ingesta → medios (proxies 480p/10fps + WAV) → Demucs (voces / resto) → cara (MediaPipe)
        → sincronización → Whisper → OCR de diálogos del juego → movimiento → risas/gritos/eventos (PANNs)
        → quién habla → señales → IA elige historias → IA revisa los mejores → (render por clip)
```

| Etapa | Herramienta | Archivo |
|---|---|---|
| Kick | yt-dlp + curl_cffi | `ingest/kick.py` |
| Adaptador de fuentes | FFmpeg | `ingest/adapter.py` |
| Sincronización cámara ↔ juego | correlación cruzada de audio; si la cámara no tiene audio, sincronía labios-voz | `sync.py` |
| Separar voces | Demucs `htdemucs_ft` | `audio/separation.py` |
| Transcripción | faster-whisper `large-v3-turbo` + VAD | `audio/transcribe.py` |
| Risas, gritos, eventos del juego | PANNs CNN14 (etiquetas AudioSet) | `audio/events.py` |
| Huella de voz del streamer | SpeechBrain ECAPA-TDNN | `audio/voiceprint.py` |
| Cara: encuadre, boca, sonrisa, sorpresa | MediaPipe Face Landmarker (blendshapes) | `vision/face.py` |
| Diálogos del juego en pantalla | PaddleOCR | `vision/ocr.py` |
| Movimiento y cortes de escena | OpenCV | `vision/motion.py` |
| Quién habla (STREAMER / JUEGO) | boca + huella de voz + OCR | `speakers.py` |
| Curva de "emoción" | fusión de señales | `signals.py` |
| Elegir historias y revisar clips | **cualquier LLM** (ver abajo) | `selection/` |
| Render 9:16 | FFmpeg + ASS + NVENC (cae a x264) | `render/` |

Cada etapa guarda su resultado en `data/sessions/<id>/`. Si algo falla, el siguiente análisis retoma desde ahí.

## Proveedor de IA (intercambiable)

Se elige con `CLIPS_LLM_PROVIDER` y solo hace falta instalar el SDK de ese proveedor:

| Proveedor | `CLIPS_LLM_PROVIDER` | Extra de pip | Clave |
|---|---|---|---|
| Claude | `anthropic` (por defecto) | `.[claude]` | `ANTHROPIC_API_KEY` o `ant auth login` |
| OpenAI | `openai` | `.[openai]` | `OPENAI_API_KEY` |
| Gemini | `gemini` | `.[gemini]` | `GEMINI_API_KEY` |
| Groq, OpenRouter, DeepSeek, Ollama, LM Studio, vLLM… | `openai_compatible` + `CLIPS_LLM_BASE_URL` | `.[openai]` | `CLIPS_LLM_API_KEY` (opcional en servidores locales) |

- `CLIPS_LLM_MODEL` elige el modelo. Vacío = el modelo por defecto del proveedor.
- Si el modelo no acepta imágenes, pon `CLIPS_LLM_VISION=0`: la revisión usará solo la transcripción.
- Las claves viven solo en el worker; el navegador nunca las ve.
- Para añadir otro proveedor: una clase con `generate_json` en `selection/providers.py`.

## Instalación

Requisitos: Python ≥ 3.10, FFmpeg en el PATH (con NVENC si hay GPU NVIDIA) y, de preferencia, CUDA.

```bash
cd worker
python -m venv .venv
.venv/Scripts/activate        # Windows (en macOS/Linux: source .venv/bin/activate)
pip install -e ".[claude]"    # o .[openai], .[gemini], .[all-llm]
cp env.example .env          # y completa las claves
```

Modelo de MediaPipe (una vez): descarga `face_landmarker.task` desde la URL de `env.example` y apunta `CLIPS_FACE_LANDMARKER_MODEL` a ese archivo.

Fuentes del título: copia Montserrat/Poppins (por ejemplo, `vidforge/apps/web/public/fonts/subtitles` del monorepo) a una carpeta y define `CLIPS_FONTS_DIR`.

## Uso

```bash
gameclips serve                       # API en http://127.0.0.1:8790 (la usa la UI)
gameclips analyze --gameplay juego.mkv --camera cam.mkv --title "Le enseño a manejar a mi hermana"
gameclips render ses_xxxxxxxxxxxx cand_xxxxxxxxxxxx
gameclips enroll juanjo muestra_voz.wav   # huella de voz (≈30 s hablando solo)
```

## Pruebas

```bash
pip install -e ".[dev]"
pytest
```

`tests/test_pure_logic.py` cubre la lógica sin dependencias pesadas: quién habla, señales, cortes, encuadre, ASS, comando de FFmpeg, URLs de Kick y proveedores. `tests/test_sync.py` prueba la sincronización con señales sintéticas.
