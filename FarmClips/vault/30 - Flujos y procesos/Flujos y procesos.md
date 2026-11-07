---
titulo: Flujos y procesos
tipo: indice
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/indice, area/procesos]
---

# 30 · Flujos y procesos

> [!abstract] En pocas palabras
> Guía secuencial paso a paso de los 6 procesos que transforman una grabación larga de videojuegos en Shorts verticales de alta calidad listos para publicar en redes sociales.

---

## 📑 Secuencia completa del pipeline

| Paso | Proceso | Qué ocurre | Estado |
|:---:|---|---|---|
| **01** | [[Flujo 1 Ingesta y Sincronización]] | Detección de archivos, extracción Opus 16 kHz y sincronización XCorr FFT. | `#estado/vigente` |
| **02** | [[Flujo 2 Transcripción y Señales]] | Transcripción concurrente en la nube y análisis de euforia acústica a 100 Hz. | `#estado/vigente` |
| **03** | [[Flujo 3 Curación con LLM]] | Selección de momentos virales mediante IDs de frase (`u0001`..`u9999`) y scoring. | `#estado/vigente` |
| **04** | [[Flujo 4 Tracking y Generación EditPlan]] | MediaPipe Face Detector acotado al clip y compilación del EditPlan v2. | `#estado/vigente` |
| **05** | [[Flujo 5 Edición Interactiva en Web Studio]] | Previsualización en vivo en Next.js 15, mezcla Web Audio API y edición manual. | `#estado/vigente` |
| **06** | [[Flujo 6 Renderizado y Normalización]] | Exportación en GPU (NVENC), subtítulos libass, audio a -14 LUFS y Webhooks. | `#estado/vigente` |

---

## 🔗 Relacionado
- [[00 - Inicio]]
- [[Visión general]]
- [[Arquitectura general]]
- [[Datos]]