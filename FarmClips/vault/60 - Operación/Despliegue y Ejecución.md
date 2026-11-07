---
titulo: Despliegue y Ejecución
tipo: operacion
estado: vigente
audiencia: [tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/operacion, area/despliegue]
---

# Despliegue y Ejecución del sistema

> [!abstract] En pocas palabras
> Instrucciones técnicas para desplegar FarmClips en entornos de desarrollo local en Windows o en contenedores Docker para servidores y estaciones de renderizado continuo.

---

## 🖥️ 1. Despliegue Local Nativo (Windows PowerShell)

Es el modo de ejecución predeterminado y más rápido para estaciones de trabajo con tarjeta gráfica NVIDIA:

```powershell
# Desde la raíz del repositorio ClipsApp
powershell -ExecutionPolicy Bypass -File infra\dev.ps1
```

### Puertos y servicios activos
- **Frontend Next.js**: `http://127.0.0.1:3040`
- **Backend FastAPI**: `http://127.0.0.1:8790`
- **Documentación Swagger / OpenAPI**: `http://127.0.0.1:8790/docs`
- **Chequeo de salud del sistema**: `http://127.0.0.1:8790/health`

---

## 🐳 2. Despliegue con Docker y Docker Compose

Ubicado en `infra/Dockerfile` e `infra/docker-compose.yml`. Ideal para ejecutar el servidor en un servidor local headless o máquina Linux con soporte de GPU:

```bash
# Construir y levantar el contenedor en background
docker compose -f infra/docker-compose.yml up -d --build
```

### Características de la imagen Docker:
- Imagen base: `python:3.12-slim-bookworm` con `ffmpeg`, `libsm6`, `libxext6` y compiladores necesarios.
- Montaje de volumen persistente en `./data:/app/data` para conservar la base de datos `clipsapp.db` y los renders finales.
- Passthrough de GPU NVIDIA para aceleración NVENC mediante el runtime de `nvidia-container-toolkit`.

---

## 🩺 Verificación de Salud (*Healthcheck*)

Para comprobar que todos los binarios y directorios esenciales estén operativos, ejecuta:

```bash
curl http://127.0.0.1:8790/health
```

Respuesta esperada:
```json
{
  "ok": true,
  "ffmpeg": true,
  "mediapipe_face_detector": true,
  "stt_primary": "deepgram",
  "llm_primary": "gemini",
  "style_preset": "hormozi-gaming",
  "use_nvenc": true,
  "budget": {
    "total_usd": 0.0,
    "max_budget_usd": 9.0,
    "remaining_usd": 9.0,
    "pct": 0.0
  }
}
```

---

## 🔗 Relacionado
- [[Primeros pasos]]
- [[Monitoreo y Presupuesto]]
- [[Mantenimiento y Limpieza]]
- [[Variables de Entorno]]