# ClippersIppers — Réplica Local de OpusClip (4.0 Revamp & Classic Studio)

Réplica frontend local de alta fidelidad de **OpusClip (`https://clip.opus.pro/dashboard`)** y su suite **AI Video Editor (`https://www.opus.pro/ai-video-editor`)**, construida mediante ingeniería inversa asistida por **REA (Reverse Engineer Anything)**.

---

## Clips de gaming (flujo principal)

La ruta `/sessions` convierte la grabación de un stream en **Shorts verticales** con cámara arriba, gameplay abajo y título en la unión. Acepta dos tipos de fuente:

- **Cámara + juego por separado** (recomendado): el video del juego con el audio mezclado y el de la cámara (plugin Source Record de OBS).
- **Stream compuesto**: un `.mp4`/`.mkv` local o un **link de Kick**, marcando en la UI dónde está la facecam.

El análisis corre en el worker de Python [`worker/`](./worker/README.md): sincronización, Demucs, Whisper, MediaPipe, PANNs y OCR, más una IA que elige las historias. La IA es **intercambiable**: Claude, OpenAI, Gemini o cualquier API compatible con OpenAI (Groq, OpenRouter, Ollama…). Next.js habla con el worker vía `/api/worker/*`.

```powershell
# Terminal 1: worker
cd worker
pip install -e ".[claude]"     # o .[openai], .[gemini], .[all-llm]
cp env.example .env            # proveedor de IA, claves y rutas de modelos
gameclips serve

# Terminal 2: interfaz
cp env.example .env.local      # CLIPS_WORKER_URL (por defecto http://127.0.0.1:8790)
npm install
npm run dev                    # http://localhost:3040 → /sessions
```

Las pantallas heredadas (Studio, Proyectos, Plantillas…) siguen disponibles y son el flujo anterior, solo para YouTube.

---

## Características Principales

- **Dashboard Revamp 4.0 & Classic**: Selector de recetas de clipeo, uploader multipart, listado de proyectos con estados de render en tiempo real y cohortes activas.
- **Workflow & Recortes Inteligentes**: Selección de rango temporal (`startSec`–`endSec`), prompts `ClipAnything`, cálculo dinámico de créditos y presets de relación de aspecto (9:16 vertical, 1:1 cuadrado, 16:9 horizontal).
- **Curated Clip Results & Virality Score**: Puntuación de viralidad (0–99) con desglose en cuatro pilares: *Hook*, *Flow*, *Value* y *Trend*.
- **Editor NLE Multipista de 4 Zonas**: Editor de transcripción palabra por palabra, selector de pausas y muletillas, visualización interactiva con caja de arrastre `Moveable` y línea de tiempo de 5 pistas.
- **Brand Kits & Plantillas Karaoke**: Personalización de estilos de subtítulos karaoke (colores, fuentes tipográficas, animaciones CSS de entrada y resalte).
- **Exportación Versátil**: Generación de subtítulos `.SRT` y proyectos `.XML` para importación directa en Adobe Premiere Pro y DaVinci Resolve.

---

## Estructura del Proyecto

```
ClippersIppers/
├── public/
│   └── locales/en/       # Archivos de localización i18n (clip, editor, subscription, etc.)
├── src/
│   ├── app/              # Rutas Next.js App Router (/dashboard, /workflow, /clip, /editor-ux, etc.)
│   ├── components/       # Componentes visuales, controles NLE y reproductores de medios
│   ├── data/             # Datos semilla simulados (seedData.ts)
│   └── types/            # Definiciones de tipos TypeScript
├── next.config.mjs       # Configuración de compilación Next.js
├── package.json          # Dependencias y scripts del proyecto
├── postcss.config.mjs    # Configuración de PostCSS / Tailwind
└── tsconfig.json         # Configuración de TypeScript
```

---

## Inicio Rápido en Local

### Requisitos
- Node.js >= 18.x
- npm / pnpm / yarn

### Instalación y Ejecución

```powershell
# 1. Instalar dependencias
npm install

# 2. Iniciar el servidor de desarrollo en http://localhost:3040
npm run dev

# 3. Compilar para producción (opcional)
npm run build
npm run start
```

---

## Módulos y Vistas Replicadas

| Ruta | Módulo Original | Descripción Funcional |
| :--- | :--- | :--- |
| `/dashboard` | `DashboardRevampEntry` 4.0 | Carga de video local, cohorte en vivo, demos, novedades y tabla de proyectos. |
| `/workflow` | `RecipeStudio` | Configuración de recetas de recorte, prompts de IA y calculadora de créditos. |
| `/clip/[id]` | `CuratedClipResults` | Resultados con Virality Score (0–99), desglose de métricas, preview karaoke y exportación SRT/XML. |
| `/editor-ux/[clipId]` | `NLEEditor` | Editor multipista de 4 zonas: transcripción editable, recorte de pausas, caja Moveable y timeline. |
| `/brand-template` | `BrandKitStudio` | Personalización de colores karaoke, tipografías y 6 animaciones CSS. |
| `/projects` | `ProjectsMaster` | Archivo de proyectos con retención permanente/temporal y estados de render. |
| `/collections` | `CollectionsManager` | Carpetas y colecciones públicas/privadas de proyectos. |
| `/favorites` | `FavoritesView` | Proyectos y clips marcados como favoritos. |
| `/library` | `AssetLibrary` | Biblioteca de activos multimedia (logos, fuentes TTF, intros/outros, Auto SFX). |
| `/calendar` | `SocialScheduler` | Calendario y programador multicanal (YouTube Shorts, TikTok, Reels, X, LinkedIn). |
| `/analytics` | `AnalyticsView` | Métricas de retención de los primeros 60 segundos y correlación con Virality Score. |
| `/campaigns` | `CampaignInvite` | Marketplace de campañas para creadores y clippers. |
| `/opus-labs` | `Statsig` | Conmutador en vivo de Feature Gates de Statsig y benchmark de CPU en Web Worker. |
