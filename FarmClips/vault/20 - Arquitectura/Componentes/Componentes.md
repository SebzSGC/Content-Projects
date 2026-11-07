---
titulo: Componentes de software
tipo: indice
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/indice, area/arquitectura]
---

# 20.1 · Componentes de FarmClips

> [!abstract] En pocas palabras
> Catálogo detallado de los módulos, paquetes y subsistemas que integran FarmClips, abarcando desde el servidor backend y los pools de ejecución hasta el frontend y los paquetes de procesamiento audiovisual.

---

## 📑 Módulos del monorepo

| Componente | Paquete / Ruta | Descripción | Estado |
|---|---|---|---|
| [[FastAPI y Orquestador]] | `apps/server/clipsserver` | Servidor HTTP, SSE, base de datos SQLite WAL y máquina de estados. | `#estado/vigente` |
| [[Pools de Trabajo]] | `apps/server/.../pools` | Aislamiento en 3 pools: `ApiPool`, `CpuPool` y `RenderPool`. | `#estado/vigente` |
| [[Motor de Edición Web Studio]] | `apps/web` | Estudio interactivo en Next.js 15, Web Audio API y preview en Canvas. | `#estado/vigente` |
| [[Núcleo de Señales y Selección]] | `packages/core/clipscore` | Análisis de euforia acústica a 100 Hz, compactador de timeline y resolver. | `#estado/vigente` |
| [[Contrato EditPlan v2]] | `packages/editplan` | Especificación JSON Schema v2, modelos Pydantic y tipados TypeScript. | `#estado/vigente` |
| [[Procesamiento Multimedia]] | `packages/media/clipsmedia` | Wrappers de FFmpeg, extracción de audio Opus y sincronización XCorr FFT. | `#estado/vigente` |
| [[Proveedores de IA y Resiliencia]] | `packages/providers` | Adaptadores STT/LLM, limitadores triples de cuota y presupuesto en USD. | `#estado/vigente` |
| [[Tracking Facial en CPU]] | `packages/tracking` | MediaPipe BlazeFace acotado por clip, One Euro Filter y simplificación RDP. | `#estado/vigente` |
| [[Motor de Renderizado y Subtítulos]] | `packages/render-engine` | FastCompositor C++, compilador libass animado y loudnorm en 2 pasadas. | `#estado/vigente` |
| [[Sistema de Estilos y Presets]] | `packages/styles` | Presets de diseño Hormozi, tipografía Montserrat, 42 emojis y SFX. | `#estado/vigente` |

---

## 🔗 Relacionado
- [[Arquitectura general]]
- [[Integraciones]]
- [[Flujos y procesos]]