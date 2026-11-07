---
titulo: Preguntas Frecuentes (FAQ)
tipo: faq
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/faq, area/general]
---

# Preguntas Frecuentes (FAQ)

> [!abstract] En pocas palabras
> Respuestas rápidas a las dudas más comunes sobre la operación, costos, compatibilidad de hardware y personalización visual en FarmClips.

---

## ❓ Preguntas Generales y de Negocio

### ¿Cuánto cuesta procesar una partida de 2 horas?
En promedio entre **\$0.06 y \$0.15 USD** (menos de 600 pesos colombianos). Esto incluye la transcripción con Deepgram Nova-3 y la curación narrativa con Gemini 3.5 Flash-Lite. FarmClips incluye un límite estricto configurable en `.env` (`CLIPS_MAX_BUDGET_USD=9.00`) para garantizar que nunca se supere tu presupuesto.

### ¿Mis videos o mi rostro se suben a internet?
**No. El video nunca sale de tu computadora.** Solo se envía una pista de audio comprimida en formato Opus mono a $16\text{ kHz}$ ($\approx 7\text{ MB}$ por hora) y la transcripción de texto al modelo de lenguaje. El rastreo facial, los recortes y el renderizado final se ejecutan al 100 % en local.

### ¿Puedo publicar directamente los videos generados en TikTok y YouTube Shorts?
Sí. Los archivos finales se exportan en formato vertical $1080 \times 1920$ a 60 fps, codificados en H.264 y con el audio estrictamente normalizado a **$-14\text{ LUFS}$** (estándar internacional para plataformas móviles), garantizando que no sufran bajadas de volumen ni saturación.

---

## 🔧 Preguntas Técnicas y de Operación

### ¿Qué pasa si no tengo una tarjeta gráfica NVIDIA?
FarmClips detecta automáticamente si no hay un codificador **[[Glosario#NVENC|NVENC]]** disponible o si está saturado, y conmuta sin interrupciones a **[[Glosario#libx264|libx264]]** ejecutado en el procesador (CPU). La exportación tardará un poco más (1 a 2 minutos por clip en lugar de 40 segundos), pero la calidad visual será idéntica.

### ¿Cómo corrijo si la cámara y el juego están desfasados por unos segundos?
En el 98 % de los casos, el algoritmo **[[Glosario#XCorr FFT|XCorr FFT]]** alinea ambas pistas de audio automáticamente. Si el streamer usó auriculares y el micrófono no captó el juego, puedes ingresar a `/sessions/[id]` y definir el desfase manual con `shift_sec` (ver [[Runbook · Desincronización de Audio o Video]]).

### ¿Puedo editar los subtítulos o cambiar un emoji antes de exportar?
Sí. El estudio web (`/editor/[clipId]`) te permite reproducir el clip en tiempo real, hacer clic sobre palabras para corregir textos, desactivar silencios y elegir entre 42 emojis en alta resolución. Al pulsar "Guardar", tus cambios quedan protegidos con el estado `EDITED` para que no se sobrescriban.

### ¿Cómo pruebo FarmClips sin gastar saldo de API?
En el panel `/settings`, cambia el proveedor de STT a `fixture` y el de LLM a `fixture`. El sistema utilizará grabaciones de prueba locales sin conectarse a internet.

---

## 🔗 Relacionado
- [[Resumen ejecutivo]]
- [[Primeros pasos]]
- [[Cómo configurar Proveedores de IA]]
- [[Runbooks]]