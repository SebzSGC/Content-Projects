---
titulo: Cómo usar el Editor Web Studio
tipo: guia
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-09
etiquetas: [tipo/guia, area/frontend]
---

# Cómo usar el Editor Web Studio (`/editor/[clipId]`)

> [!abstract] En pocas palabras
> Manual de usuario del estudio de edición: aprende a revisar el video vertical, mover el inicio y el final del clip, corregir subtítulos, elegir emojis del catálogo y calibrar el volumen del juego y la voz con previsualización en vivo. Los cambios se guardan solos.

---

## 🖥️ Anatomía del Editor Web

Al hacer clic en cualquier clip desde la lista de una sesión, ingresarás a `/editor/[clipId]`:

```text
+------------------------------------------------------------------------+
|  [◀ Volver a Sesión]   Clip: #1 Clutch 1v3 (89/100)    [Guardar Cambios] |
+------------------------------------+-----------------------------------+
|                                    |  🎛️ PANEL DE PROPIEDADES          |
|        +------------------+        |  -------------------------------- |
|        |                  |        |  📌 Título del Clip:              |
|        |    CÁMARA        |        |  [CLUTCH IMPOSIBLE 1v3________]   |
|        |   DEL STREAMER   |        |                                   |
|        |                  |        |  📏 Proporción Cámara:            |
|        +------------------+        |  [====O========] 40%              |
|        | [CLUTCH 1v3]     |        |                                   |
|        |                  |        |  🔊 Mezcla de Audio:              |
|        |    GAMEPLAY      |        |  Micrófono:    [====O===] +2.0 dB |
|        |    VERTICAL      |        |  Atenuación:   [===O====] -9.0 dB |
|        |                  |        |  Disparo SFX:  [☑ boom.wav]       |
|        |  ¡NO PUEDE SER!  |        |                                   |
|        +------------------+        |  🎨 Catálogo de Emojis:           |
|                                    |  [🔥] [😱] [👑] [🎯] [💀] [💥]    |
+------------------------------------+-----------------------------------+
|  LÍNEA DE TIEMPO INTERACTIVA DE PALABRAS:                              |
|  [00:00] [u0034] [¡Me] [están] [disparando] [tres,] [cúbreme!]         |
|  [00:05] [u0035] [¡Eliminé] [al] [primero!] [Queda] [uno!]             |
|  [▶ Play] [⏸ Pause]   00:15 / 00:42        [Render 540p] [Render 1080p] |
+------------------------------------------------------------------------+
```

---

## 🧭 Acciones principales en el editor

### 1. Cambiar dónde empieza y termina el clip (y las pausas largas)
En la pestaña **Mezclador de Sonido y Ritmo**, bloque **Inicio y final del clip**:
- **Empieza en / Termina en** son segundos de la grabación original. Usa **−1s / +1s** o escribe el número.
- **Quitar las pausas largas (cortes rápidos)** activa o desactiva los [[Glosario#Jump Cut|Jump Cut]]. Apágalo si quieres el tramo completo, sin saltos.
- Pulsa **Aplicar tramo**. FarmClips recalcula la cámara, los cortes y los subtítulos del nuevo tramo. Tus correcciones de texto y el título se conservan; los ajustes manuales de cámara no (te lo avisa antes).
- El clip debe durar entre 5 s y 3 min.

> [!example] Ejemplo
> El clip "CLUTCH 1v3 EN RONDA FINAL" empezaba en el segundo 4.8 y se perdía el "...del torneo" del inicio. Con **−1s** en *Empieza en* (3.8) y **Aplicar tramo**, el clip pasa de 29.3 s a 30.7 s y arranca con la frase completa.

> [!info]- Detalle técnico
> Llama a `POST /clips/{id}/retime` (ver [[Referencia API REST y SSE]]). El servidor vuelve a ejecutar la etapa de dirección (`hormozi.py`) con el nuevo `start`/`end` y `jump_cuts`, y copia el texto corregido por coincidencia de tiempo de cada palabra (redondeado a 0.1 s).

### 2. Modificar el título de cabecera
En el panel lateral derecho, edita el campo **"Título del Clip"**. Este texto se muestra en la línea de división (*seam*) entre la cámara y el juego durante los primeros 3 segundos del Short con una animación de fundido.

### 3. Corregir subtítulos
En la pestaña **Subtítulos y Emojis**, cada frase muestra sus palabras:
- **Una palabra mal escrita**: haz clic en ella y corrígela. Un `Ctrl+Z` deshace la palabra completa, no letra por letra. Si la dejas vacía, vuelve a la anterior.
- **La frase entera**: pulsa **✎ Corregir la frase completa**, escribe la frase y pulsa `Enter` (`Esc` cancela). Puede tener más o menos palabras que antes: el tiempo de la frase se reparte entre las nuevas palabras para que el resaltado siga al audio.

> [!example] Ejemplo
> La transcripción dice "MIRA CÓMO" y el streamer dijo "MIRA COMO ENTRAN". Con **Corregir la frase completa** quedan 3 palabras en el mismo tramo de 0.20 s a 0.79 s.

### 4. Seleccionar Emojis de impacto
Haz clic en cualquier palabra clave y pulsa uno de los 42 iconos del catálogo de emojis. El emoji aparecerá flotando junto al subtítulo en el segundo exacto en que se pronuncie la palabra.

### 5. Ajustar la mezcla de sonido
- Si el videojuego tapa la voz del streamer: Reduce el deslizador de **"Atenuación del juego"** (p. ej. a $-12\text{ dB}$).
- Si la voz suena baja: Aumenta la **"Ganancia del micrófono"** (p. ej. a $+4\text{ dB}$).
- Activa la casilla **`boom.wav`** para reproducir un golpe sordo dramático en el momento de mayor impacto.

---

## ⌨️ Atajos de teclado

| Tecla | Acción |
|---|---|
| `Espacio` | Reproducir / pausar |
| `Ctrl+Z` (`Cmd+Z` en Mac) | Deshacer |
| `Ctrl+Shift+Z` o `Ctrl+Y` | Rehacer |

Dentro de un campo de texto, estas teclas escriben o deshacen el texto como siempre.

---

## 💾 Guardar y Exportar

1. **Guardado automático**: 2.5 s después de tu último cambio el editor guarda solo (verás «Guardado automático.» junto a la duración). No guarda mientras arrastras, ni durante un render. Si intentas cerrar la pestaña con cambios sin guardar, el navegador te avisa.
2. **"Guardar cambios"** guarda en el momento. La versión editada queda en SQLite con el estado **`EDITED`** para que nunca se sobrescriba.
3. **"Exportar video final (1080p)"** guarda primero lo pendiente y envía el clip a la cola de render (ver [[Cómo exportar y renderizar clips]]).

---

## 🔗 Relacionado
- [[Primeros pasos]]
- [[Cómo exportar y renderizar clips]]
- [[Motor de Edición Web Studio]]
- [[Contrato EditPlan v2]]