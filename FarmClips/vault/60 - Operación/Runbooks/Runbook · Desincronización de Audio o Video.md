---
titulo: "Runbook · Desincronización de Audio o Video"
tipo: operacion
estado: vigente
audiencia: [tecnico, soporte]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/operacion, area/runbook]
---

# Runbook: Desincronización entre Cámara y Videojuego

> [!abstract] En pocas palabras
> Guía para corregir desalineaciones temporales donde el rostro del streamer reacciona antes o después de la jugada del juego, recalculando o forzando manualmente el desfase en segundos.

---

## 🚨 Síntomas del problema

- El grito del jugador ocurre 1 o 2 segundos antes o después de que se vea la baja o el disparo en el videojuego.
- En la vista previa del editor, los labios no coinciden con las palabras subtituladas.
- En los datos de la sesión, el valor `confidence` de la sincronización es menor a **`0.70`**.

---

## 🔍 Diagnóstico

Consulta el resultado de la sincronización automática calculada por **[[Glosario#XCorr FFT|XCorr FFT]]**:

```bash
curl http://127.0.0.1:8790/sessions/<id_sesion>
```

Observa los campos dentro de `sync_json`:
```json
{
  "shift_sec": -2.45,
  "scale": 1.0000,
  "confidence": 0.42,
  "method": "audio_xcorr"
}
```
Un valor de `confidence` bajo ocurre habitualmente cuando el streamer utilizó auriculares cerrados y el micrófono no captó ningún sonido de fondo del juego para comparar.

---

## 🛠️ Procedimiento de corrección manual

### Paso 1: Determinar el desfase visual
1. Abre los dos videos originales en un reproductor multimedia (VLC o Premiere/CapCut).
2. Busca un evento claro y simultáneo (p. ej. el momento en que el streamer dice "Uno, dos, tres, ¡ya!" o cuando hace un aplauso de sincronización frente a la cámara).
3. Anota los tiempos:
   - Tiempo del evento en el gameplay: $T_{\text{juego}} = 12.50\text{ s}$.
   - Tiempo del evento en la cámara: $T_{\text{cámara}} = 14.20\text{ s}$.
4. Calcula el desfase:
   $$\text{shift\_sec} = T_{\text{cámara}} - T_{\text{juego}} = 14.20 - 12.50 = \mathbf{+1.70\text{ s}}$$

### Paso 2: Inyectar la calibración manual en el servidor

Envía una petición al endpoint de sincronización manual:

```powershell
# En PowerShell nativo
Invoke-RestMethod -Uri "http://127.0.0.1:8790/sessions/<id_sesion>/sync/manual" `
    -Method Post -ContentType "application/json" -Body '{"shift_sec": 1.70, "scale": 1.0}'

# O con curl.exe
curl.exe -X POST http://127.0.0.1:8790/sessions/<id_sesion>/sync/manual `
    -H "Content-Type: application/json" -d "{\"shift_sec\": 1.70, \"scale\": 1.0}"
```

El servidor recalculará de inmediato el archivo `PreparedMedia`, re-alineará las palabras de la transcripción y regenerará los **[[Glosario#EditPlan|EditPlans]]** de todos los clips de esa sesión con la nueva calibración.

---

## 🔗 Relacionado
- [[Flujo 1 Ingesta y Sincronización]]
- [[Procesamiento Multimedia]]
- [[Cómo usar el Editor Web Studio]]