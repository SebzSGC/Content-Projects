# Content-Projects 🎬⚡

Repositorio monorepo que reúne soluciones y proyectos independientes de **generación de video con IA**, **edición inteligente (clipping)** y **automatización audiovisual**, construidos y optimizados para flujos de trabajo de alto rendimiento.

---

## 📦 Proyectos Incluidos

| Proyecto | Tipo | Stack Principal | Descripción | README |
| :--- | :--- | :--- | :--- | :--- |
| [**VidForge Studio**](./vidforge) | Aplicación Completa (Desktop & Web) | Python 3.12 (FastAPI), React 18 (Vite), Node.js (Puppeteer WebGL), FFmpeg NVENC | Generador modular de videos asistido por IA (*Clean-Room*), con aceleración por GPU NVIDIA, alineación forzada de audio palabra por palabra, renderizado de plantillas HTML5/WebGL y exportación directa a CapCut Desktop, OpenTimelineIO y MP4 a 60 FPS. | [Ver README](./vidforge/README.md) |
| [**ClippersIppers**](./ClippersIppers) | Aplicación Web (Frontend NLE) | Next.js 14, React 18, TypeScript, Tailwind CSS | Réplica frontend de alta fidelidad inspirada en la arquitectura de OpusClip (4.0 Revamp & Classic Studio), con cálculo de Virality Score (0–99), editor NLE multipista con transcripción editable, animaciones karaoke y exportación SRT/XML. | [Ver README](./ClippersIppers/README.md) |

---

## 📂 Estructura del Monorepo

```
Content-Projects/
├── ClippersIppers/          # Suite de clipeo viral de video y editor NLE (Next.js)
│   ├── public/              # Activos y diccionarios de internacionalización
│   ├── src/                 # Rutas App Router, componentes y lógica NLE
│   ├── package.json         # Dependencias de ClippersIppers
│   └── README.md            # Documentación específica de ClippersIppers
│
├── vidforge/                # Generador modular de videos IA con aceleración NVENC
│   ├── apps/
│   │   ├── backend/         # API REST/SSE en FastAPI, colas y servicios multimedia
│   │   ├── launcher/        # Lanzador nativo WebView2 para Windows
│   │   ├── render-sidecar/  # Motor Node.js para renderizado WebGL/HTML5 a WebM
│   │   └── web/             # Interfaz web SPA en React 18 + Vite
│   ├── packages/            # Contratos JSON Schema y plantillas visuales
│   ├── tools/               # Scripts de aprovisionamiento y pruebas
│   ├── Iniciar-VidForge.bat # Lanzador rápido modo escritorio
│   └── README.md            # Documentación específica de VidForge Studio
│
├── .gitignore               # Configuración de exclusión para dependencias y binarios
└── README.md                # Documentación general del repositorio
```

---

## 🚀 Inicio Rápido

Cada proyecto es completamente autónomo y puede ejecutarse de manera independiente:

### 1. VidForge Studio

Para iniciar VidForge en Windows con soporte de aceleración por hardware:

```powershell
cd vidforge

# 1. Aprovisionar runtimes portables (Python 3.12, uv, FFmpeg NVENC)
powershell -ExecutionPolicy Bypass -File tools/fetch-runtimes.ps1

# 2. Iniciar en modo escritorio nativo (WebView2)
.\Iniciar-VidForge.bat

# O en modo servidor web local (http://127.0.0.1:8765)
.\Iniciar-Servidor-Web.bat
```

Consulta los detalles técnicos y arquitectura en [`vidforge/README.md`](./vidforge/README.md).

---

### 2. ClippersIppers

Para ejecutar la interfaz de clipeo inteligente y editor NLE:

```powershell
cd ClippersIppers

# 1. Instalar dependencias
npm install

# 2. Iniciar el servidor de desarrollo en http://localhost:3040
npm run dev
```

Consulta las rutas, módulos y componentes en [`ClippersIppers/README.md`](./ClippersIppers/README.md).

---

## 🛠️ Tecnologías y Herramientas

- **Backend & Orquestación Multimedia**: Python 3.12, FastAPI, Pydantic, FFmpeg (soporte NVENC), Faster-Whisper, RapidFuzz.
- **Frontend & UI/UX**: Next.js 14, React 18, Vite, Tailwind CSS, Lucide Icons, Moveable.
- **Render Dinámico & Sidecar**: Node.js, Puppeteer Core, WebGL, GLSL Shaders, WebM VP9 Alpha.
- **Interoperabilidad & Formatos**: CapCut Desktop Drafts (`draft_content.json`), OpenTimelineIO (`.otio`), Adobe Premiere / DaVinci Resolve (`.xml`), `.srt`, `.ass`.

---

## 📄 Licencia

Este repositorio agrupa desarrollos con fines educativos, de investigación y producción de herramientas de contenido audiovisual.
