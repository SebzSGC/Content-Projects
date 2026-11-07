---
titulo: "ADR-003 Tracking Facial por Clip en CPU"
tipo: decision
estado: vigente
audiencia: [tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/decision, area/vision]
---

# ADR-003: Tracking Facial Acotado por Clip en CPU con MediaPipe

> [!abstract] En pocas palabras
> Detalla por qué no se analiza el video de la cámara completo de 2 horas y por qué se ejecuta MediaPipe en el procesador principal (CPU) en lugar de competir por la memoria de la tarjeta gráfica (GPU).

---

## 🎯 Contexto y Problema

Rastrear el rostro del streamer a lo largo de una transmisión continua de 2 o 3 horas a 60 fps implica procesar más de 640.000 fotogramas de alta resolución.
Si esta tarea se ejecuta en la GPU:
1. Compite directamente con el videojuego o el software de streaming por la memoria de video (VRAM).
2. Desperdicia más del 95 % de los cálculos, ya que solo unos 3 a 5 minutos de video terminarán convirtiéndose en clips de salida.

---

## ⚖️ Decisión adoptada

1. **Diferir el tracking hasta después de la curación**: El orquestador no analiza la cámara durante la ingesta. Espera a que el LLM y el analizador de señales elijan los clips ganadores.
2. **Ejecutar MediaPipe Face Detector en CPU**: Utiliza el modelo ultraliviano `blaze_face_short_range.tflite` sobre el procesador estándar en subprocesos aislados (`CpuPool`).
3. **Submuestreo y acotamiento temporal**: Solo se decodifican los fragmentos de los clips elegidos (con 2 segundos de margen de seguridad) a una tasa reducida de **15 cuadros por segundo** y ancho de **640 píxeles**.

---

## ✅ Consecuencias

- **Positivas**:
  - El tiempo de tracking pasa de 35 minutos a tan solo **30 a 45 segundos** en total por sesión.
  - La tarjeta gráfica queda 100 % libre para el renderizado final NVENC o para jugar.
  - Cero calentamiento excesivo o conflictos de controladores en Windows.
- **Negativas / Mitigaciones**:
  - A 15 fps existe riesgo de perder movimientos bruscos de cabeza; se mitiga aplicando el filtro adaptativo **[[Glosario#One Euro Filter|One Euro Filter]]** e interpolación lineal de pérdidas cortas.

---

## 🔗 Relacionado
- [[Tracking Facial en CPU]]
- [[Pools de Trabajo]]
- [[Flujo 4 Tracking y Generación EditPlan]]