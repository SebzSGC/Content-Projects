---
titulo: "Runbook · Falla de Render o NVENC"
tipo: operacion
estado: vigente
audiencia: [tecnico, soporte]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/operacion, area/runbook]
---

# Runbook: Falla de Renderizado o Saturación de NVENC

> [!abstract] En pocas palabras
> Solución inmediata ante errores de codificación por hardware en tarjetas gráficas NVIDIA (falta de memoria VRAM o sesiones de codificación superadas), con cambio automático a codificación por procesador (CPU).

---

## 🚨 Síntomas del problema

- El renderizado se cancela en los primeros segundos de codificación.
- La barra de progreso de render muestra un error en rojo.
- En los registros de la consola de FarmClips o FFmpeg aparece:
  - `[h264_nvenc @ ...] OpenEncodeSessionEx failed: out of memory (10)`
  - `No capable devices found`
  - `Error while opening encoder for output stream #0:0`.

---

## 🔍 Diagnóstico

Abre una terminal y revisa el estado de memoria de tu tarjeta gráfica:

```powershell
nvidia-smi
```

Comprueba:
1. Si la memoria VRAM libre es menor a **`1.5 GB`** (a menudo ocupada por videojuegos en segundo plano como Call of Duty o Cyberpunk).
2. Cuántos procesos están utilizando el codificador de video simultáneamente. Las tarjetas gráficas de la serie GeForce suelen tener un límite por firmware de **3 sesiones NVENC simultáneas**.

---

## 🛠️ Procedimiento de resolución paso a paso

### Paso 1: Reducir los slots de renderizado concurrente
Si tienes otras aplicaciones abiertas (OBS Studio, Discord con transmisión activa):
1. Abre tu archivo `.env`.
2. Fija el límite de sesiones concurrentes a 1:
   ```env
   CLIPS_NVENC_SLOTS=1
   ```
3. Reinicia el servidor o guarda los cambios en `/settings`.

### Paso 2: Conmutar a codificación por software ([[Glosario#libx264|libx264]])
Si la tarjeta gráfica está completamente saturada por un juego o estás operando en una máquina sin GPU NVIDIA:
1. En `.env`, desactiva el uso de hardware:
   ```env
   CLIPS_USE_NVENC=false
   ```
2. El motor `RenderPool` conmutará inmediatamente a **[[Glosario#libx264|libx264]]** en CPU, asignando un cuarto de los núcleos disponibles para un renderizado estable y sin caídas.

### Paso 3: Reintentar el clip fallido
1. Ve a `/editor/[clipId]`.
2. Pulsa nuevamente **"Render 1080p"**.

---

## 🔗 Relacionado
- [[Pools de Trabajo]]
- [[Motor de Renderizado y Subtítulos]]
- [[Cómo exportar y renderizar clips]]