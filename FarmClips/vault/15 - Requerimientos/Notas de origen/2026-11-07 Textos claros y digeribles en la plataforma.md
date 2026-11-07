---
titulo: Textos claros y digeribles en la plataforma
tipo: nota-origen
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
fecha: 2026-11-07
fuente: solicitud-usuario
actualizado: 2026-11-07
etiquetas: [requerimientos, origen, area/frontend]
---

# 🗒️ Nota de origen — Textos claros y digeribles en la plataforma

> [!abstract] En pocas palabras
> Solicitud inicial para transformar todos los textos de la interfaz web y mensajes del orquestador en un lenguaje digerible, cercano y orientado a creadores, eliminando saturación técnica.

## Solicitud original del usuario
> "Necesito que la información que se muestre en la página sea texto más agradable para entender el por qué de las cosas, que sea más resumido sin quitar importancia. Actualmente dice cosas muy técnicas y muy precisas de modo a que se siente mucha saturación de información; necesito que el texto que vea el usuario sea algo más digerible."

## Puntos clave identificados
1. **Explicar el «por qué» en lenguaje humano**: Reemplazar jerga interna (`Opus mono 16 kHz`, `FFT`, `Parquet`, `u0001..u9999`, `outBack`, `sidechain`, `CLIPS_STT_PRIMARY`, `task_hash`) por explicaciones breves y naturales sobre qué logra cada paso o ajuste para el creador.
2. **Reducir la saturación visual**: Resumir descripciones largas en frases cortas y directas, dejando los datos técnicos únicamente dentro de paneles desplegables o ayudas puntuales (`InfoTip`) redactadas de forma amigable.
3. **Cubrir todas las vistas del Estudio Web**:
   - Barra de navegación (`TopNav.tsx`) y pasos del proceso (`pipelineSteps.ts`).
   - Página principal de Sesiones (`/sessions`).
   - Detalle de Sesión (`/sessions/[id]`) y mensajes de progreso en vivo (`engine.py`).
   - Editor de Clips en vivo (`/editor/[clipId]`).
   - Panel de Consumo y Presupuesto (`/analytics`).
   - Panel de Configuración (`/settings`).

## Historias derivadas
- [[HU-002 Simplificación y lenguaje claro en toda la plataforma]] (Épica: [[EP-02 Claridad y Experiencia de Usuario en Web Studio]])

---

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[HU-002 Simplificación y lenguaje claro en toda la plataforma]]
- [[Motor de Edición Web Studio]]
