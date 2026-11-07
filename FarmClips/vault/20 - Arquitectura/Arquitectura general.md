---
titulo: Arquitectura general del sistema
tipo: arquitectura
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/arquitectura, area/core]
---

# Arquitectura general de FarmClips

> [!abstract] En pocas palabras
> FarmClips divide el trabajo de forma radical: la inteligencia y comprensión de lenguaje viajan por internet en paquetes diminutos hacia modelos de IA, mientras que el renderizado, corte de video y análisis facial ocurren íntegramente dentro de tu computadora para máxima velocidad y cero costo de almacenamiento en la nube.

---

## 🗺️ Diagrama de contexto del sistema (C4 Nivel 1)

```mermaid
flowchart TD
    %% Diagrama de contexto
    subgraph FuentesExternas["☁️ Servicios Externos e Ingesta"]
        GD["Google Drive / Carpeta Local<br/>(Almacén de grabaciones)"]
        STT_API["APIs STT (Deepgram Nova-3 / Groq Whisper)<br/>(Transcripción de voz)"]
        LLM_API["APIs LLM (Gemini 3.5 Flash / GPT-6 Luna)<br/>(Curación de historias)"]
        DISCORD["Webhooks (Discord / Slack)<br/>(Notificaciones de entrega)"]
    end

    subgraph FarmClipsLocal["💻 Máquina Local (Host)"]
        WEB["App Web (Next.js 15)<br/>Puerto 3040"]
        SERVER["Servidor Unificado (FastAPI)<br/>Puerto 8790"]
        DB[(SQLite WAL<br/>clipsapp.db)]
        DATA_FS["Sistema de Archivos Local<br/>(data/sessions/)"]
        GPU["Tarjeta Gráfica NVIDIA<br/>(NVENC H.264)"]
    end

    GD -->|Descarga audio/video| SERVER
    SERVER <-->|Estado, clips y configuración| DB
    SERVER <-->|Lectura/Escritura de artefactos| DATA_FS
    SERVER -->|Envía audio Opus 16 kHz| STT_API
    SERVER -->|Envía línea de tiempo de IDs| LLM_API
    SERVER -->|Notifica fin de render| DISCORD
    SERVER -->|Envía jobs de renderizado| GPU

    WEB <-->|SSE y API REST| SERVER
    WEB -->|Previsualización en tiempo real| DATA_FS

    style FarmClipsLocal fill:#1e293b,stroke:#334155,stroke-width:2px,color:#fff
    style FuentesExternas fill:#0f172a,stroke:#1e293b,stroke-width:1px,color:#94a3b8
```

---

## 🏗️ Diagrama de contenedores y separación de capas (C4 Nivel 2)

El sistema se estructura en dos aplicaciones principales y un monorepo modular de paquetes en Python y TypeScript:

```mermaid
flowchart LR
    subgraph apps["📦 Aplicaciones (apps/)"]
        W["apps/web<br/>(Next.js 15, React 19, Tailwind)"]
        S["apps/server<br/>(FastAPI, Asyncio, SSE)"]
    end

    subgraph packages["📚 Paquetes Modulares (packages/)"]
        P_EDIT["clipseditplan<br/>(Contrato JSON Schema v2)"]
        P_CORE["clipscore<br/>(Señales, Director, Timeline)"]
        P_MEDIA["clipsmedia<br/>(FFmpeg, Opus, Sync FFT)"]
        P_PROV["clipsproviders<br/>(HTTP Resiliencia, STT, LLM)"]
        P_TRACK["clipstracking<br/>(MediaPipe BlazeFace CPU)"]
        P_REND["clipsrender<br/>(FastCompositor, ASS, Loudnorm)"]
        P_STYLES["clipsstyles<br/>(Presets, Fuentes, Emojis, SFX)"]
    end

    subgraph storage["💾 Almacenamiento Local"]
        SQL[(SQLite WAL)]
        PARQUET[Archivos Parquet]
        MEDIA_STORE[Renders MP4]
    end

    W <-->|REST + SSE /events| S
    S --> P_EDIT
    S --> P_CORE
    S --> P_MEDIA
    S --> P_PROV
    S --> P_TRACK
    S --> P_REND
    S --> P_STYLES

    S <--> SQL
    P_CORE --> PARQUET
    P_TRACK --> PARQUET
    P_REND --> MEDIA_STORE
```

---

## ⚙️ Los 3 Pools de Trabajo Aislados

Para evitar que una tarea pesada congele al servidor o bloquee la interfaz gráfica, el servidor organiza el trabajo en tres grupos de ejecución con políticas de concurrencia independientes:

1. **`ApiPool` (`asyncio` + `httpx`)**:
   - Gestiona todas las llamadas de red externas.
   - Aplica limitación triple: concurrencia máxima, peticiones por minuto (RPM) y control de presupuesto en USD.
   - Detecta errores `429` respetando el encabezado `Retry-After`.
   - En caso de payload demasiado grande (`413`), subdivide el archivo de audio automáticamente.
   - Conmuta a proveedores de respaldo si el proveedor principal falla.
2. **`CpuPool` (`ProcessPoolExecutor`, núcleos disponibles $- 1$)**:
   - Dedicado al cómputo numérico intensivo sin sufrir el bloqueo del GIL de Python.
   - Ejecuta extracción de envolventes de audio a 100 Hz, detección de movimiento en video a 2 fps mediante OpenCV y tracking facial con **[[Glosario#MediaPipe|MediaPipe]]**.
   - Almacena series temporales comprimidas en formato Parquet.
3. **`RenderPool` (Cola priorizada para GPU y CPU)**:
   - Controla el acceso a los slots de codificación de la GPU (**[[Glosario#NVENC|NVENC]]**, típicamente 2 o 3 sesiones simultáneas).
   - Degrada de forma segura a codificación por software (**[[Glosario#libx264|libx264]]**) con límite de núcleos si no hay hardware NVIDIA disponible.

> [!example] Asignación en una computadora típica de 8 núcleos con GPU RTX 4060
> - `ApiPool`: Gestiona hasta 8 peticiones HTTP concurrentes hacia Deepgram y Gemini.
> - `CpuPool`: Utiliza 7 procesos paralelos para computar las señales Parquet y rastrear el rostro en los clips elegidos.
> - `RenderPool`: Limita a 2 renders simultáneos con NVENC a 1080p, encolando el resto según la puntuación de calidad del clip.

---

## 🛡️ Seguridad y protección de datos

> [!info]- Detalle técnico (clic para expandir)
> - **Enmascaramiento de credenciales**: En la base de datos y la interfaz de configuración (`/settings`), las claves de API nunca se exponen completas (se almacenan y transmiten como `AIza...8a9b` o `sk-...3f1a`).
> - **Aislamiento de red**: El servidor solo se expone por defecto en la interfaz local de bucle invertido (`127.0.0.1:8790`).
> - **Idempotencia mediante Hash SHA-256**: Todo archivo de entrada y artefacto intermedio genera una firma determinista basada en su ruta absoluta, tamaño en bytes y fecha de modificación en nanosegundos (`mtime_ns`). Si el hash ya existe en la tabla `artifacts`, no se recalculan datos.

---

## 🔗 Relacionado
- [[FastAPI y Orquestador]]
- [[Pools de Trabajo]]
- [[Motor de Edición Web Studio]]
- [[Integraciones]]
- [[ADR-001 Arquitectura Híbrida IA Nube y Proceso Local]]