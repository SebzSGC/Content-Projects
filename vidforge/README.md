# VidForge Studio — Generador Modular de Vídeos IA (Clean-Room)

Implementación completa, limpia (*Clean-Room*) y 100% funcional para Windows x64, optimizada para ejecución local con aceleración por hardware **NVIDIA NVENC** (`h264_nvenc`), síntesis de voz offline, alineación forzada palabra por palabra y exportación directa a **CapCut Desktop**, **OpenTimelineIO (`.otio`)**, **SRT/ASS** y **MP4 a 60 FPS**.

---

## Características Principales

- **Pipeline de Renderizado Local**: Orquestación asíncrona de FastAPI + FFmpeg con aceleración por hardware NVENC.
- **Sidecar WebGL/HTML5**: Motor en Node.js + Puppeteer para renderizado de plantillas dinámicas a WebM VP9 con canal alfa (`alpha_mode=1`) y transiciones GLSL.
- **Sincronización Palabra por Palabra**: Alineación forzada precisa mediante RapidFuzz + Faster-Whisper / VAD para subtítulos dinámicos estilo TikTok / Reels.
- **Exportación Multi-Destino**: Generación de MP4 60 FPS, borradores nativos para **CapCut Desktop** (`draft_content.json`), OpenTimelineIO (`.otio`) y subtítulos SRT/ASS.
- **UI React 18 + Vite**: Interfaz con 5 espacios de trabajo especializados (*Director & Prompts*, *Multimedia & AudioLab*, *Sync & Plantillas*, *Editor Studio*, *Hardware & Claves*) y modo **Autopilot 1-Click**.

---

## Estructura del Proyecto

```
vidforge/
├── apps/
│   ├── backend/          # Servidor FastAPI REST + SSE, colas y servicios de render/audio
│   ├── launcher/         # Lanzador de escritorio nativo (WebView2) sin ventana de consola
│   ├── render-sidecar/   # Sidecar en Node.js para animación de plantillas y transiciones WebGL
│   └── web/              # Frontend SPA en React 18 + Vite
├── installer/            # Script Inno Setup reproducible (vidforge.iss)
├── packages/
│   ├── contracts/        # Esquemas JSON Schema 2020-12 compartidos
│   └── templates/        # Plantillas HTML5/CSS animadas (lower-thirds, stat-highlights, etc.)
├── tools/                # Scripts de automatización, verificación y descarga de runtimes
├── Iniciar-VidForge.bat  # Lanzador modo ventana de escritorio
└── Iniciar-Servidor-Web.bat # Lanzador modo servidor web local
```

---

## Requisitos y Preparación

- **Sistema Operativo**: Windows 10/11 x64.
- **GPU**: NVIDIA con soporte NVENC (opcional, fallback por software en CPU).
- **Runtimes**:
  Para descargar y configurar automáticamente los runtimes aislados (Python 3.12 portable, `uv`, y FFmpeg con NVENC):
  ```powershell
  powershell -ExecutionPolicy Bypass -File tools/fetch-runtimes.ps1
  ```

---

## Cómo Iniciar la Aplicación

Dispones de dos modos de inicio rápido:

1. **Modo Aplicación de Escritorio (WebView2):**
   - Ejecuta `Iniciar-VidForge.bat` o desde terminal:
     ```powershell
     .\Iniciar-VidForge.bat
     ```

2. **Modo Navegador Web Estándar (`http://127.0.0.1:8765`):**
   - Ejecuta `Iniciar-Servidor-Web.bat` o desde terminal:
     ```powershell
     .\Iniciar-Servidor-Web.bat
     ```

---

## Arquitectura Implementada

| Fase | Componente | Ubicación |
| :--- | :--- | :--- |
| **Fase 1** | Runtime aislado (`CPython 3.12.15`, `uv`, `FFmpeg NVENC`), resolución de rutas, Job Objects de Windows (`CREATE_NO_WINDOW`) y detección de GPU (`h264_nvenc`) | `runtime/`, `apps/backend/src/vidforge/infra/` |
| **Fase 2** | Servidor FastAPI REST + SSE (`/api/v1/*`), `JobManager` con semáforos por recurso, AudioLab (`join`, `trim_silence`, `loudnorm`), alineación forzada (`RapidFuzz` + `faster-whisper`/VAD) y bóveda de secretos (`DPAPI` + `AES-256-GCM`) | `apps/backend/src/vidforge/api/`, `jobs/`, `services/`, `infra/` |
| **Fase 3** | Sidecar en Node.js + `puppeteer-core` para plantillas HTML/CSS/SVG a WebM VP9 con canal alfa y transiciones WebGL GLSL, pipeline FFmpeg con efecto Ken Burns y exportador CapCut Desktop | `apps/render-sidecar/`, `packages/templates/`, `services/render.py`, `services/export.py` |
| **Fase 4** | SPA en React 18 + Vite con los 5 espacios de trabajo y modo Autopilot 1-Click | `apps/web/src/` |
| **Fase 5** | Contratos JSON Schema 2020-12, verificador de manifiesto SHA-256 (`tools/verify-install.py`), instalador Inno Setup (`installer/vidforge.iss`) y suite de pruebas | `packages/contracts/`, `apps/backend/tests/` |

---

## Verificación y Pruebas

```powershell
# Verificar integridad de la instalación y manifiesto
python tools/verify-install.py

# Ejecutar suite de pruebas unitarias y de propiedades
pytest apps/backend/tests/test_vidforge_suite.py -v
```
