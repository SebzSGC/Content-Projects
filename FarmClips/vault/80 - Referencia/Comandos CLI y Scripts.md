---
titulo: Comandos CLI y Scripts
tipo: guia
estado: vigente
audiencia: [tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/guia, area/cli]
---

# Comandos de Línea de Comandos (CLI) y Scripts

> [!abstract] En pocas palabras
> Referencia de comandos rápidos de terminal para arrancar los servidores, regenerar contratos TypeScript, ejecutar pruebas automatizadas y gestionar el monorepo.

---

## ⚡ 1. Arranque y Desarrollo

### Arranque unificado con PowerShell (Recomendado)
```powershell
powershell -ExecutionPolicy Bypass -File infra\dev.ps1
```
Inicia concurrentemente el servidor Python FastAPI (puerto 8790) y el servidor de desarrollo Next.js (puerto 3040).

### Arranque manual independiente
```powershell
# Iniciar solo el backend Python
.\.venv\Scripts\python.exe -m clipsserver.main serve

# Iniciar solo el frontend web Next.js
npm --prefix apps/web run dev
```

---

## 🔄 2. Regeneración de Contratos y Tipos (Codegen)

Cuando se modifica un modelo de datos en `clipseditplan/models.py` o los esquemas de la API en `clipsserver`, ejecuta:

```powershell
.\.venv\Scripts\python.exe -m clipsserver.main codegen --web-dir apps/web
```

Este comando:
1. Exporta el esquema formal **JSON Schema** de `EditPlan v2`.
2. Genera los archivos de interfaces **TypeScript** en `apps/web/src/lib/types/editplan.ts`.
3. Actualiza el archivo OpenAPI `openapi.json`.

---

## 🧪 3. Pruebas Automatizadas (Pytest)

Ejecuta la suite completa de pruebas unitarias, resiliencia y pruebas *Golden E2E*:

```powershell
.\.venv\Scripts\pytest.exe -v
```

Para ejecutar una prueba específica:
```powershell
# Probar únicamente el cálculo de sincronización FFT
.\.venv\Scripts\pytest.exe tests/test_sync.py -v

# Probar la resiliencia y el límite de presupuesto de la API
.\.venv\Scripts\pytest.exe tests/test_api_resilience.py -v
```

---

## 🏗️ 4. Compilación del Frontend para Producción

```powershell
# Compilar el estudio web Next.js
npm --prefix apps/web run build

# Iniciar el servidor web compilado
npm --prefix apps/web run start
```

---

## 🤖 5. Copiloto MCP (Model Context Protocol)

### Generar configuración para Claude Desktop y Antigravity
```powershell
.\.venv\Scripts\python.exe -m clipsserver.main mcp-config
```
Detecta las rutas reales del entorno virtual y del CLI de FilmCraft en Windows y genera el bloque JSON para `%APPDATA%\Claude\claude_desktop_config.json`.

### Arranque del servidor MCP por stdio
```powershell
.\.venv\Scripts\python.exe -m clipsserver.mcp
```

---

## 🔗 Relacionado
- [[Primeros pasos]]
- [[Motor de Renderizado y Subtítulos]]
- [[Despliegue y Ejecución]]
- [[Referencia API REST y SSE]]
- [[Variables de Entorno]]