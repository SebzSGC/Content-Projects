---
titulo: Flujo 6 Renderizado y Normalización
tipo: flujo
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/flujo, area/render]
---

# Flujo 6 · Renderizado en GPU y normalización sonora

> [!abstract] En pocas palabras
> Paso final del pipeline: exporta el video vertical en resolución $1080 \times 1920$ a 60 fps con aceleración en tarjeta gráfica NVIDIA, quema los subtítulos animados en el video, fija el volumen a -14 LUFS y lo entrega en tu carpeta de salida y por Discord.

---

## 🗺️ Diagrama del proceso de exportación

```mermaid
sequenceDiagram
    autonumber
    participant O as Orquestador
    participant RP as RenderPool
    participant GPU as NVENC / C++ Compositor
    participant D as Almacén (Drive Salidas / Local)
    participant WH as Webhook (Discord / Slack)

    O->>RP: Encola render 1080p con prioridad (score del clip)
    RP->>GPU: Ejecuta FastCompositor C++ + libass + loudnorm 2 pasadas
    loop Progreso de codificación
        GPU-->>RP: FPS, tiempo y porcentaje
        RP-->>O: Publica evento SSE render_progress
    end
    GPU-->>RP: Archivo MP4 final generado (1080x1920, -14 LUFS)
    RP-->>O: Ruta del archivo en disco
    O->>D: Copia o sube a Salidas/<grabación>/clip_XX.mp4
    O->>WH: Envía payload con títulos, enlaces y duración
    O-->>O: Actualiza estado a DELIVERED
```

---

## 🧭 Paso a paso detallado

### Paso 1: Encolado con prioridad en `RenderPool`
Las peticiones de render se ordenan dinámicamente según la puntuación de calidad del clip (`final_score`). Los mejores momentos se exportan primero.
- Se adquiere un slot en el semáforo de hardware NVIDIA (**[[Glosario#NVENC|NVENC]]**).
- Si la GPU está ocupada o no existe, conmuta automáticamente a la CPU con **[[Glosario#libx264|libx264]]**.

### Paso 2: Renderizado compuesto en C++ y quemado de subtítulos
1. **`FastCompositor`**: Genera la composición vertical combinando los fotogramas del juego y la cámara mediante transformaciones afines en C++ (`cv2.warpAffine`), aplicando los zooms y paneos dinámicos.
2. **`libass`**: Renderiza la pista de subtítulos `.ass`, aplicando el resaltado de color palabra por palabra, escalado de énfasis tipográfico y títulos en la línea divisoria.

### Paso 3: Normalización sonora estricta en 2 pasadas
Para garantizar que el clip no suene ni muy bajo ni saturado en redes sociales:
- **Pasada 1**: Mide la sonoridad integrada del audio mezclado.
- **Pasada 2**: Aplica la ganancia lineal exacta para fijar el audio en **$-14\text{ LUFS}$** con verdadero pico (*True Peak*) a $-1.0\text{ dBTP}$.

### Paso 4: Entrega final y notificación
1. El archivo resultante se nombra de forma limpia (p. ej. `clip_01_clutch_imposible.mp4`) y se almacena en `data/sessions/<id>/renders/`.
2. Si Google Drive está habilitado, se sube de forma resumible a la subcarpeta `Salidas/<nombre_grabación>/`.
3. Se dispara una notificación HTTP POST al **[[Glosario#Webhook|Webhook]]** de Discord o Slack configurado con los datos de publicación (título sugerido, hashtags y enlace al clip).

---

## 🔗 Relacionado
- [[Flujo 5 Edición Interactiva en Web Studio]]
- [[Motor de Renderizado y Subtítulos]]
- [[Pools de Trabajo]]
- [[Cómo exportar y renderizar clips]]