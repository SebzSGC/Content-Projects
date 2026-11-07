---
titulo: Guía de Primeros Pasos
tipo: guia
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/guia, area/tutorial]
---

# Guía de Primeros Pasos: De cero a funcionando

> [!abstract] En pocas palabras
> Tutorial paso a paso para poner en marcha FarmClips en tu computadora con Windows, configurar tus claves de inteligencia artificial y procesar tu primera partida de videojuegos para obtener Shorts virales en 5 minutos.

---

## 📋 Requisitos previos del sistema

Antes de comenzar, asegúrate de contar con lo siguiente en tu máquina:
- **Sistema operativo**: Windows 10 u 11 (64-bit).
- **Python**: Versión 3.10, 3.11 o 3.12 instalada.
- **Node.js**: Versión 18 o 20 LTS (incluye `npm`).
- **FFmpeg**: Instalado y agregado a la variable de entorno `PATH` (o accesible en el sistema).
- **Tarjeta gráfica (Opcional pero recomendada)**: NVIDIA GeForce GTX 1060 o superior para aceleración por hardware con **[[Glosario#NVENC|NVENC]]**.

---

## 🧭 Paso a paso de instalación y arranque

### Paso 1: Clonar y preparar el entorno

Abre una terminal de PowerShell en la carpeta raíz del proyecto (`ClipsApp`):

```powershell
# 1. Crear el archivo de configuración a partir de la plantilla
Copy-Item .env.example .env

# 2. Crear y activar el entorno virtual de Python
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip

# 3. Instalar los paquetes del monorepo en modo editable
.\.venv\Scripts\pip install -e packages/styles -e packages/editplan -e packages/core -e packages/media -e packages/providers -e packages/tracking -e packages/render-engine -e apps/server

# 4. Instalar dependencias del frontend web
npm --prefix apps/web install
```

### Paso 2: Arrancar el servidor y el estudio web

Ejecuta el script de automatización incluido en la carpeta `infra`:

```powershell
powershell -ExecutionPolicy Bypass -File infra\dev.ps1
```

Este script ejecuta concurrentemente:
1. El servidor unificado FastAPI en el puerto **`8790`**.
2. La aplicación web de Next.js en el puerto **`3040`**.

Verás en tu consola la confirmación:
```text
[Dev] API Server escuchando en http://127.0.0.1:8790
[Dev] Web Studio disponible en http://127.0.0.1:3040
```

---

## ⚙️ Paso 3: Configurar claves de IA desde la web

No necesitas editar archivos de texto a mano. Abre tu navegador web en:
👉 `http://127.0.0.1:3040/settings`

1. Introduce tu **`DEEPGRAM_API_KEY`** (para transcripción rápida de voz).
2. Introduce tu **`GEMINI_API_KEY`** (obtenida gratis en Google AI Studio).
3. Haz clic en el botón **"Probar conexión"** para validar que ambas claves respondan correctamente.
4. Haz clic en **"Guardar cambios"** (la configuración se guardará en `.env` en caliente sin reiniciar el servidor).

> [!tip] ¿Quieres probar el sistema sin gastar saldo ni internet?
> En el mismo panel de `/settings` puedes activar el modo **Fixture**:
> - Proveedor STT: `fixture`
> - Proveedor LLM: `fixture`
> Esto utilizará las respuestas de prueba precargadas en `tests/fixtures/api/` a coste cero.

---

## 🎬 Paso 4: Crear tu primera sesión de video

1. Ve a la pantalla principal en `http://127.0.0.1:3040/sessions`.
2. Haz clic en **"Nueva Sesión"**.
3. Rellena los datos básicos:
   - **Título**: *Partida Épica Valorant*.
   - **Ruta de Gameplay**: `C:\Videos\gameplay.mp4` (video de la pantalla).
   - **Ruta de Cámara**: `C:\Videos\camara.mp4` (video con el micrófono de la voz).
4. Pulsa **"Iniciar Procesamiento"**.

En la pantalla verás cómo la barra de progreso avanza en tiempo real:
`Extrayendo pistas y sincronizando (5%)` $\rightarrow$ `Transcribiendo (25%)` $\rightarrow$ `Curando clips con LLM (55%)` $\rightarrow$ `Tracking facial y EditPlans (80%)` $\rightarrow$ `Completado (100%)`.

---

## 🔗 Relacionado
- [[Cómo configurar Proveedores de IA]]
- [[Cómo usar el Editor Web Studio]]
- [[Cómo exportar y renderizar clips]]
- [[Despliegue y Ejecución]]