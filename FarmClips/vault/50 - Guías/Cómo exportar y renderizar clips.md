---
titulo: Cómo exportar y renderizar clips
tipo: guia
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/guia, area/render]
---

# Cómo exportar y renderizar clips de video

> [!abstract] En pocas palabras
> Guía práctica sobre los dos modos de renderizado (borrador rápido de 540p vs exportación final en 1080p), cómo aprovechar la tarjeta gráfica NVIDIA y dónde se guardan los archivos finales listos para publicar.

---

## ⚡ Comparativa de calidades de render

| Modo de render | Resolución | Tasa de cuadros | Tiempo de exportación | Uso recomendado |
|---|:---:|:---:|:---:|---|
| **Borrador (*Draft*)** | $540 \times 960$ | 30 fps | **5 a 10 segundos** | Revisión rápida en celular o previsualización. |
| **Final (*Final*)** | $1080 \times 1920$ | 60 fps | **35 a 50 segundos** | Publicación definitiva en YouTube Shorts, TikTok y Reels. |

---

## 🎬 Modos de activación del renderizado

### 1. Renderizado Automático (Piloto automático)
Cuando el orquestador concluye el análisis de una sesión:
- Filtra todos los clips cuya puntuación final (`final_score`) sea igual o superior a **`60 / 100`**.
- Selecciona los mejores (por defecto el Top 5 configurado en `auto_render_top_k`).
- Los encola automáticamente para render en 1080p y los sube a Google Drive sin que tengas que tocar nada.

### 2. Renderizado Manual desde el Estudio Web
Si quieres renderizar un clip que no quedó en el Top 5 o que acabas de modificar:
1. Abre el clip en `/editor/[clipId]`.
2. Pulsa el botón **"Render 1080p"** (o "Render 540p" para prueba).
3. Aparecerá una barra de progreso que refleja el avance de FFmpeg cuadro a cuadro:
   `En cola...` $\rightarrow$ `Codificando video (45%)` $\rightarrow$ `Normalizando audio -14 LUFS` $\rightarrow$ `¡Completado!`.

---

## 📁 ¿Dónde se guardan los archivos de salida?

1. **En tu disco local**:
   Los archivos MP4 finales se ubican en la carpeta de la sesión:
   ```text
   ClipsApp/data/sessions/<id_sesion>/renders/
     ├── clip_01_clutch_final.mp4
     ├── clip_02_reaccion_susto.mp4
     └── ...
   ```
2. **En Google Drive (si está conectado)**:
   Se crea automáticamente una subcarpeta en la raíz configurada:
   ```text
   Google Drive / Salidas / <nombre_de_la_partida> /
     ├── clip_01_clutch_final.mp4
     └── metadata.json (hashtags, título sugerido y duración)
   ```

---

## 🔗 Relacionado
- [[Cómo usar el Editor Web Studio]]
- [[Motor de Renderizado y Subtítulos]]
- [[Flujo 6 Renderizado y Normalización]]
- [[Runbook · Falla de Render o NVENC]]