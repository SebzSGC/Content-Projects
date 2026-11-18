---
id: HU-014
titulo: Selección editorial recopilaciones y aprendizaje con optimización de costos
tipo: historia
epica: EP-04
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
prioridad: alta
estimacion: L
avance: 50
fecha_inicio: 2026-11-18
fecha_fin: 2026-11-18
origen: "[[Plan de Mejora - Calidad de Clips, Costos y Personalización]]"
afecta:
  - "[[Flujo 3 Curación con LLM]]"
  - "[[Flujo 4 Tracking y Generación EditPlan]]"
  - "[[Cómo configurar Proveedores de IA]]"
  - "[[Motor de Edición Web Studio]]"
  - "[[FastAPI y Orquestador]]"
actualizado: 2026-11-18
etiquetas: [requerimientos, historia, area/core, area/providers, area/backend, area/frontend]
estado_historia: hecho
inicio: 2026-11-18
fin: 2026-11-18
progreso: 100
fin_real: 2026-11-18
---

# 📗 HU-014 — Selección editorial, recopilaciones y aprendizaje con optimización de costos

> [!abstract] En pocas palabras
> Acopla la selección editorial de formatos (`individual` y `recopilacion` multi-tramo con mínimo `40 s` de exportación) con marcas de pausa y emoción en el timeline, cola dinámica por decaimiento de audio, soporte nativo de DeepSeek con tarifas reales y aprendizaje continuo desde las valoraciones (`Valorar clip`) y ediciones del creador.

> [!info] Historia de usuario
> **Como** creador de contenido en FarmClips,
> **quiero** que el sistema seleccione clips individuales o recopilaciones con contexto completo, cierre las reacciones sin cortar risas a mitad, soporte modelos económicos como DeepSeek y aprenda de mis valoraciones y recortes en el editor,
> **para** obtener Shorts de mayor retención y coherencia narrativa a menor costo de API.

## ✅ Criterios de aceptación
- [x] **Dado** un VOD procesado en una sesión, **cuando** el curador evalúa la transcripción y señales con el perfil *FarmClips 1.0*, **entonces** distingue entre formato `individual` y `recopilacion` multi-tramo (con `evidence_ids`, orden cronológico en ventana de `600 s` y suelo de `40 s` verificado con `FFprobe` antes de exportar el MP4 final, reteniendo clips breves en `REVIEW_SHORT`).
- [x] **Dada** la construcción del timeline compacto y la resolución de cortes (`timeline/builder.py`, `selection/resolver.py`, `directors/hormozi.py`), **cuando** existen señales acústicas, **entonces** el timeline incluye marcas de pausa (`--- [PAUSA Xs] ---` para silencios $\ge 3\text{ s}$) y etiquetas de reacción (`[ALTA REACCIÓN]` / `[REACCIÓN]`), el `tail_pad` se ajusta según el decaimiento de la reacción vocal y los *jump cuts* protegen ráfagas vocales a `100 Hz` con SFX CC0 (`boom`, `whoosh`, `pop`).
- [x] **Dado** el adaptador `OpenAICompatibleAdapter` y el panel `/settings`, **cuando** se configura `deepseek-chat`, `deepseek-flash`, `deepseek-reasoner` o `gemini-3.1-flash-lite`, **entonces** el cálculo de presupuesto aplica las tarifas reales (incluyendo `prompt_cache_hit_tokens` en DeepSeek) y envía `json_object` + `max_tokens` directamente en endpoints de DeepSeek.
- [x] **Dado** el módulo de revisión editorial y el editor `/editor/[clipId]`, **cuando** el usuario valora clips en **Valorar clip** o guarda ajustes de tramos/títulos en el editor, **entonces** las decisiones y diffs quedan registrados en `highlight_revisions` y `build_learned_editorial_guidance` sintetiza preferencias de categoría y hasta 3 *Golden Clips* aprobados para guiar futuras curaciones.

## 🛠️ Tareas técnicas
- [x] Implementar el comparador offline `/experimental/highlights`, `ClipReview.tsx`, resolución de recopilaciones (`EditorialSegment`, `EditPlan.source.ranges`) y verificación de duración final de `40 s` con `FFprobe`.
- [x] Enriquecer `build_compact_timeline` con marcas de pausa entera y reacción, y añadir `compute_dynamic_tail_pad` en `selection/resolver.py`.
- [x] Ampliar `compute_jump_cut_ranges` con protección a `100 Hz` y `ensure_sfx_wav` con síntesis CC0 para `boom`, `whoosh` y `pop`.
- [x] Incorporar tarifas y compatibilidad directa de DeepSeek (`deepseek-chat`, `deepseek-flash`, `deepseek-reasoner`) y `gemini-3.1-flash-lite` en `openai_compat.py`, `gemini.py` y `/settings`.
- [x] Habilitar valoraciones por defecto, registrar diffs del editor (`edicion_estudio`) y conectar `build_learned_editorial_guidance` al flujo de curación en `engine.py`.

## 📝 Bitácora

- 2026-11-18 · Sin iniciar → **En progreso** · Integración de selección editorial, recopilaciones y Plan de Mejora de calidad, costos y aprendizaje

---
- 2026-11-18 · En progreso → **Hecho** · Integrados criterios editoriales, recopilaciones, timeline con pausas/reacción, cola dinámica, DeepSeek y aprendizaje continuo (77 tests pasados)

## 🔗 Relacionado
- [[EP-04 Selección Editorial Calidad de Clips y Aprendizaje Continuo]]
- [[Plan de Mejora - Calidad de Clips, Costos y Personalización]]
- [[Flujo 3 Curación con LLM]]
- [[Flujo 4 Tracking y Generación EditPlan]]
- [[Cómo configurar Proveedores de IA]]
