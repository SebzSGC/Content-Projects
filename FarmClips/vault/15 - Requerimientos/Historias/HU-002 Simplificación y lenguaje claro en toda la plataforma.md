---
id: HU-002
titulo: Simplificación y lenguaje claro en toda la plataforma
tipo: historia
epica: EP-02
estado: hecho
audiencia: [todos]
responsable: Equipo FarmClips
prioridad: alta
estimacion: M
avance: 100
fecha_inicio: 2026-11-07
fecha_fin: 2026-11-07
origen: "[[2026-11-07 Textos claros y digeribles en la plataforma]]"
afecta:
  - "[[Motor de Edición Web Studio]]"
  - "[[Cómo configurar Proveedores de IA]]"
  - "[[Monitoreo y Presupuesto]]"
actualizado: 2026-11-07
etiquetas: [requerimientos, historia, area/frontend]
estado_historia: hecho
inicio: 2026-11-07
fin_real: 2026-11-07
progreso: 100
---

# 📗 HU-002 — Simplificación y lenguaje claro en toda la plataforma

> [!abstract] En pocas palabras
> Sustitución de terminología técnica densa y críptica por lenguaje claro, agradable y orientado a resultados que explica el porqué de cada opción para creadores de contenido.

> [!info] Historia de usuario
> **Como** creador de contenido en FarmClips,
> **quiero** que los textos de toda la plataforma sean breves, agradables y expliquen el porqué de cada opción sin jerga técnica excesiva,
> **para** entender de un vistazo qué está haciendo el sistema y tomar decisiones rápidas sin sentirme saturado de información.

## ✅ Criterios de aceptación
- [x] Los pasos del flujo (`pipelineSteps.ts`), la barra superior (`TopNav.tsx`) y los mensajes en vivo del orquestador (`engine.py`) usan frases cortas y naturales que explican el propósito de cada etapa sin siglas crípticas (`FFT`, `Parquet`, `Opus 16 kHz`, `u0001..u9999`).
- [x] La vista de **Sesiones** (`/sessions`) y **Detalle de Sesión** (`/sessions/[id]`) presentan textos concisos y explican con sencillez por qué cada clip fue elegido, qué muestra la curva de emoción y para qué sirve sincronizar o exportar a DaVinci Resolve.
- [x] El **Editor de Clips** (`/editor/[clipId]`) reemplaza términos técnicos (`outBack`, `inOutSine`, `Sidechain`, `Jump Cuts`, `cx`, `EditPlan v2`) por etiquetas claras y orientadas al resultado visual y sonoro.
- [x] Las vistas de **Consumo y Presupuesto** (`/analytics`) y **Configuración** (`/settings`) resumen las descripciones, ocultan nombres de variables internas innecesarios en los títulos y explican en una línea por qué conviene cada opción.

## 🛠️ Tareas técnicas
- [x] Actualizar `apps/web/src/lib/pipelineSteps.ts`, `apps/web/src/components/TopNav.tsx` y `apps/server/clipsserver/orchestrator/engine.py`.
- [x] Simplificar textos y ayudas en `apps/web/src/app/sessions/page.tsx` y `apps/web/src/app/sessions/[id]/page.tsx`.
- [x] Humanizar las etiquetas y controles del editor en `apps/web/src/app/editor/[clipId]/page.tsx`.
- [x] Reducir la densidad de información y tecnicismos en `apps/web/src/app/analytics/page.tsx` y `apps/web/src/app/settings/page.tsx`.

## 📝 Registro de avance
- **2026-11-07**: Historia creada a partir de la solicitud del usuario.

## 📝 Bitácora

- 2026-11-07 · Sin iniciar → **En progreso** · Iniciando simplificación de textos y experiencia de usuario en el Estudio Web
- 2026-11-07 · En progreso → **Hecho** · Textos humanizados, simplificados y digeribles en toda la plataforma Web Studio y el orquestador

---

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[2026-11-07 Textos claros y digeribles en la plataforma]]
- [[Motor de Edición Web Studio]]
- [[Cómo configurar Proveedores de IA]]
- [[Monitoreo y Presupuesto]]
