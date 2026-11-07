---
titulo: Cómo usar el Editor Web Studio
tipo: guia
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/guia, area/frontend]
---

# Cómo usar el Editor Web Studio (`/editor/[clipId]`)

> [!abstract] En pocas palabras
> Manual de usuario del estudio de edición: aprende a revisar el video vertical, recortar pausas de respiración, cambiar subtítulos, elegir emojis del catálogo y calibrar el volumen del juego y la voz con previsualización en vivo.

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

### 1. Eliminar pausas o palabras muertas ([[Glosario#Jump Cut|Jump Cut]])
En la parte inferior verás cada palabra transcrita en una píldora clickable:
- Haz clic sobre cualquier palabra que quieras eliminar (p. ej. un "ehhh" o un silencio largo). La píldora se atenuará en gris.
- El reproductor aplicará un salto automático instantáneo sin necesidad de recalcular el video completo.

### 2. Modificar el título de cabecera
En el panel lateral derecho, edita el campo **"Título del Clip"**. Este texto se muestra en la línea de división (*seam*) entre la cámara y el juego durante los primeros 3 segundos del Short con una animación de fundido.

### 3. Seleccionar Emojis de impacto
Haz clic en cualquier palabra clave y pulsa uno de los 42 iconos del catálogo de emojis. El emoji aparecerá flotando junto al subtítulo en el segundo exacto en que se pronuncie la palabra.

### 4. Ajustar la mezcla de sonido
- Si el videojuego tapa la voz del streamer: Reduce el deslizador de **"Atenuación del juego"** (p. ej. a $-12\text{ dB}$).
- Si la voz suena baja: Aumenta la **"Ganancia del micrófono"** (p. ej. a $+4\text{ dB}$).
- Activa la casilla **`boom.wav`** para reproducir un golpe sordo dramático en el momento de mayor impacto.

---

## 💾 Guardar y Exportar

1. Pulsa el botón **"Guardar cambios"**: Esto grabará tu versión editada (`editplan.user.json`) en SQLite y marcará el clip con el estado **`EDITED`** para que nunca se sobrescriba.
2. Pulsa **"Render 1080p"** para enviar el trabajo a la cola final de la tarjeta gráfica.

---

## 🔗 Relacionado
- [[Primeros pasos]]
- [[Cómo exportar y renderizar clips]]
- [[Motor de Edición Web Studio]]
- [[Contrato EditPlan v2]]