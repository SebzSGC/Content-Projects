---
titulo: "Runbook · Falla de API o Presupuesto Agotado"
tipo: operacion
estado: vigente
audiencia: [tecnico, soporte]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/operacion, area/runbook]
---

# Runbook: Falla de API externa o Presupuesto Agotado

> [!abstract] En pocas palabras
> Procedimiento de emergencia ante errores de cuota superada (429), saldo agotado en Deepgram o Gemini, o cuando el sistema se frena automáticamente por alcanzar el límite de gasto en dólares.

---

## 🚨 Síntomas del problema

- La barra de progreso de la sesión se detiene en `Transcribiendo (25 %)` o `Curando con LLM (55 %)`.
- El estado de la sesión cambia a `FAILED` o permanece pausado con advertencia de presupuesto.
- En la consola o el log aparece alguno de estos mensajes:
  - `HTTPStatusError: 429 Too Many Requests`
  - `RuntimeError: Presupuesto agotado para esta sesión (> $9.00 USD)`
  - `HTTPStatusError: 401 Unauthorized` o `Invalid API Key`.

---

## 🔍 Diagnóstico rápido

Ejecuta en tu terminal de PowerShell para conocer el desglose de gasto y el error exacto:

```powershell
# En PowerShell nativo
Invoke-RestMethod -Uri "http://127.0.0.1:8790/budget"

# O con curl.exe
curl.exe http://127.0.0.1:8790/budget
```

Revisa si el proveedor primario está respondiendo con el probador:

```powershell
# En PowerShell nativo
Invoke-RestMethod -Uri "http://127.0.0.1:8790/settings/test-connection" -Method Post -ContentType "application/json" -Body '{"provider": "deepgram"}'

# O con curl.exe
curl.exe -X POST http://127.0.0.1:8790/settings/test-connection -H "Content-Type: application/json" -d "{\"provider\": \"deepgram\"}"
```

---

## 🛠️ Procedimiento de resolución paso a paso

### Caso 1: Límite de presupuesto alcanzado en FarmClips
1. Abre en tu navegador `http://127.0.0.1:3040/settings`.
2. Localiza el campo **"Presupuesto máximo por sesión"**.
3. Incrementa el límite (por ejemplo de `9.00` a `15.00` USD).
4. Pulsa **"Guardar cambios"**.
5. Regresa a `/sessions/[id]` y pulsa **"Reanudar sesión"**. El orquestador continuará sin repetir los audios ya transcritos gracias a la caché en SQLite.

### Caso 2: Saldo agotado en Deepgram
1. Cambia el proveedor de transcripción secundario a Groq:
   - En `/settings`, fija **STT Primario**: `groq`.
   - Modelo: `whisper-large-v3-turbo`.
   - Introduce tu `GROQ_API_KEY`.
2. Guarda los cambios y pulsa **"Reanudar"**.

### Caso 3: Fallo en Gemini AI Studio (Error 429 o bloqueo de región)
1. En `/settings`, fija **LLM Primario**: `openai_compat`.
2. Si tienes OpenAI, introduce tu `OPENAI_API_KEY`.
3. Si utilizas un modelo local (Ollama):
   - Base URL: `http://localhost:11434/v1`
   - Modelo: `llama3.2` o `mistral`.
4. Pulsa **"Probar conexión"** y guarda.

---

## 🔗 Relacionado
- [[Monitoreo y Presupuesto]]
- [[Cómo configurar Proveedores de IA]]
- [[Proveedores de IA y Resiliencia]]