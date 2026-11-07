---
titulo: Núcleo de Señales y Selección
tipo: componente
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/componente, area/core]
---

# Núcleo de Señales y Selección (`clipscore`)

> [!abstract] En pocas palabras
> Es el motor matemático y narrativo de FarmClips. Analiza la euforia en la voz y el movimiento del juego a 100 Hz, compacta la transcripción en un formato ultra liviano para el LLM y traduce las decisiones del modelo de IA en cortes de video exactos al milisegundo.

---

## 🎯 Estructura de módulos (`packages/core/clipscore/`)

```mermaid
flowchart TD
    subgraph clipscore["clipscore (Motor Central)"]
        SIG["signals/analyzer.py<br/>(Envolventes 100 Hz, Movimiento OpenCV 2 fps, Killfeed)"]
        TIME["timeline/builder.py<br/>(Agrupación en Utterances y ventanas de timeline)"]
        SEL["selection/resolver.py<br/>(Mapeo de IDs u0001..u9999 y ataques acústicos)"]
        DIR["directors/hormozi.py<br/>(Reglas de ritmo, silencios y colocación de títulos)"]
        FRAM["framing/camera_math.py<br/>(One Euro Filter, RDP y Deadband)"]
    end

    SIG --> TIME
    TIME --> SEL
    SEL --> DIR
    DIR --> FRAM
```

---

## 📊 1. Analizador de Señales (`signals/analyzer.py`)

Genera una serie temporal completa por cada segundo de la grabación VOD y la serializa en formato Apache Parquet (`signals.parquet`):
- **`mic_loudness` y `mic_burst`**: Calculados sobre la pista WAV a 16 kHz mediante envolventes RMS con ventanas de 10 ms. Miden volumen sostenido y gritos repentinos de emoción.
- **`game_loudness`**: Volumen de los efectos sonoros y disparos del juego.
- **`motion` y `motion_cx`**: Cuantificación del flujo óptico o diferencia de cuadros a 2 fps en el gameplay para detectar tiroteos o giros rápidos de cámara.
- **`hud_activity`**: Análisis focalizado en la esquina superior derecha (típica zona de *Killfeed* en juegos como Valorant o CS2) para detectar bajas sucesivas.
- **`excitement`**: Función combinada ponderada:
  $$\text{excitement}(t) = 0.40 \cdot \text{mic\_burst} + 0.25 \cdot \text{reaction} + 0.20 \cdot \text{motion} + 0.15 \cdot \text{hud}$$

---

## 📝 2. Constructor de Línea de Tiempo (`timeline/builder.py`)

Transforma miles de palabras individuales en una transcripción estructurada en frases (**[[Glosario#Utterance|Utterances]]**):
- Asigna un identificador corto y único (`u0001`, `u0002`, ..., `u9999`).
- Fusiona silencios naturales de respiración ($< 0.4\text{ s}$).
- Compacta el texto para enviar al LLM:
  ```text
  [u0045] 00:04:12 (exc: 0.85) ¡No puede ser, viene por la espalda!
  [u0046] 00:04:15 (exc: 0.94) ¡Doble baja, bro, ganamos la ronda!
  ```
- **Ahorro de tokens**: Reduce el consumo de contexto del LLM en más de un 80 % comparado con enviar estructuras JSON completas con tiempos flotantes.

---

## ⏱️ 3. Resolvedor de Tiempos y Cortes (`selection/resolver.py`)

El LLM devuelve una propuesta como `{"start_id": "u0045", "end_id": "u0046"}`. El resolvedor local realiza el trabajo de precisión:
1. Extrae la primera palabra de `u0045` y la última de `u0046`.
2. **Ajuste del ataque acústico**: Retrocede entre 50 y 150 ms en la envolvente sonora a 100 Hz para encontrar el punto de silencio exacto antes de la primera consonante explosiva (p. ej. la "N" o la "P").
3. **Márgenes de seguridad**: Añade un pequeño *padding* configurable (0.2 s al inicio y 0.5 s al final) para que las frases no suenen truncadas ni artificiales.
4. **Validación de duración**: Descarta propuestas de clips menores a 20 s o mayores a 60 s, garantizando compatibilidad con YouTube Shorts y TikTok.

---

## 🔗 Relacionado
- [[Arquitectura general]]
- [[Contrato EditPlan v2]]
- [[Proveedores de IA y Resiliencia]]
- [[Tracking Facial en CPU]]
- [[ADR-002 Selección por IDs de Frase en LLM]]