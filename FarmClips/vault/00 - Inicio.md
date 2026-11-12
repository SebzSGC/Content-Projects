---
titulo: FarmClips · Documentación Oficial
tipo: inicio
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-09
etiquetas: [tipo/inicio]
commit_codigo: e86767b
---

# 🏠 FarmClips — Arquitectura Híbrida

> [!abstract] En pocas palabras
> Sistema automatizado que convierte grabaciones largas de videojuegos en Shorts verticales virales para TikTok, YouTube Shorts y Reels con estilo Hormozi Gaming, combinando inteligencia artificial ligera en la nube con procesamiento multimedia 100 % local.

| 📌 Estado | 👤 Responsable | 🗓️ Actualizado | 🔗 Repositorio / Código |
|---|---|---|---|
| En producción (v2.6.0) | Equipo FarmClips | 2026-11-09 | `ClipsApp` (Monorepo unificado) |

---

## 🧭 ¿Por dónde empiezo?

| Si eres… | Lee primero | Luego |
|---|---|---|
| 👩‍💼 **De negocio / Streamer** | [[Resumen ejecutivo]] | [[Alcance y objetivos]] |
| 🆕 **Nuevo desarrollador** | [[Primeros pasos]] | [[Arquitectura general]] |
| 🛠️ **Soporte o DevOps** | [[Runbooks]] | [[Despliegue y Ejecución]] |
| 🤔 **Buscas un término o concepto** | [[Glosario]] | [[FAQ]] |

---

## 🗺️ El proyecto de un vistazo

```mermaid
flowchart LR
    %% Vista de alto nivel de FarmClips
    streamer([👤 Streamer / Creador]) -->|Deposita gameplay + cámara| fc[⚡ FarmClips Local]
    fc <-->|Audio comprimido de voz y texto| ai[(🤖 APIs de IA: Deepgram & Gemini)]
    fc -->|Genera video vertical con audio calibrado| shorts[📱 Shorts 9:16 en 1080p]
    fc -->|Notifica por HTTP POST| webhook[(📢 Discord / Slack Webhook)]
    
    style fc fill:#2563eb,stroke:#1d4ed8,color:#fff
    style shorts fill:#059669,stroke:#047857,color:#fff
    style ai fill:#7c3aed,stroke:#6d28d9,color:#fff
```

> [!tip] Vista visual completa e interactiva
> Abre el mapa del proyecto en Obsidian: ![[Mapa del proyecto.canvas]]

---

## 📚 Mapa de Contenidos del Vault

- 🎯 **[[Visión general]]**: Propuesta de valor, objetivos del sistema, matriz de actores RACI y [[Glosario]] central.
- 📋 **[[Requerimientos]]**: Historias de usuario, épicas y su seguimiento en el [[Tablero de avance]].
- 🏗️ **[[Arquitectura]]**: Diagramas de contexto C4, separación de los 3 pools y catálogo de [[Componentes]].
- 🔄 **[[Flujos y procesos]]**: Pipeline en 6 fases continuas, desde la ingesta hasta la entrega de video normalizado.
- 📊 **[[Datos]]**: Modelo relacional SQLite WAL, esquemas de archivos Parquet y fórmulas de cálculo de puntuación y sonoridad.
- 🧭 **[[Guías]]**: Tutoriales prácticos paso a paso para arrancar, usar el editor interactivo y renderizar clips.
- 🚑 **[[Operación]]**: Monitoreo de eventos en tiempo real, control de presupuesto y catálogo de [[Runbooks]].
- ⚖️ **[[Decisiones]]**: Registro de decisiones de diseño de arquitectura (ADR) con sus motivos y alternativas descartadas.
- 📖 **[[Referencia]]**: Especificación de endpoints REST/SSE, variables de entorno y comandos de terminal.
- 🗂️ **[[Recursos]]**: Preguntas frecuentes resueltas ([[FAQ]]) e [[Historial de cambios]].

---

- **2026-11-09 (v2.6.0)**: Editor más confiable (Espacio pausa, deshacer correcto, el visor se actualiza en pausa), corrección de frases completas, inicio/final del clip y cortes desde el editor, guardado automático, y render casi el doble de rápido en Mac con VideoToolbox (Windows sin cambios) → [[Historial de cambios]].
- **2026-11-09 (v2.5.1)**: Transcripción solo de voz (silencios largos recortados antes de pagar la API, mismos tiempos y texto) y costo real de Gemini con tokens de razonamiento → [[Historial de cambios]].
- **2026-11-07 (v2.3.0)**: Optimización integral de fluidez en Web Studio (`SharedSseManager` singleton, GPU compositing), carga instantánea de `/settings` (< 10 ms) y lenguaje claro y digerible en toda la interfaz → [[Historial de cambios]].
- **2026-11-07 (v2.0.0)**: Lanzamiento del monorepo unificado, motor de edición declarativo EditPlan v2, renderizado acelerado en C++ (`FastCompositor`), normalización en 2 pasadas a -14 LUFS y panel de ajustes en caliente `/settings` → [[Historial de cambios]].