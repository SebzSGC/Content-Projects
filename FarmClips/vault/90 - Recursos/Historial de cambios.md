---
titulo: Historial de cambios
tipo: cambios
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/cambios, area/general]
---

# Historial de cambios de FarmClips

> [!abstract] En pocas palabras
> Registro cronológico de las versiones de FarmClips, nuevas funcionalidades, optimizaciones de rendimiento y ajustes en la arquitectura del sistema.

---

## [2.1.0] — 2026-11-07 (Versión actual)

### ☁️ Conexión directa a Google Drive (OAuth 2.0) y explorador interactivo de sesiones

Esta actualización incorpora autenticación directa con cuentas personales de Google mediante OAuth 2.0 y un navegador interactivo de carpetas y videos en el estudio web para crear sesiones desde la nube en un clic.

#### Qué cambió
- **Conector `GoogleDriveOAuthConnector` (`packages/media/clipsmedia/drive.py`)**: Flujo completo de autorización OAuth 2.0 con intercambio de código, renovación automática mediante `refresh_token` persistido en `data/drive_oauth_token.json`, lectura de perfil (`/drive/v3/about`) y desconexión segura.
- **Explorador de carpetas y auto-detección de par (`browse_folder` y `get_file_entry`)**: Navegación de subcarpetas con migas de pan (*breadcrumbs*), filtrado por nombre y emparejamiento inteligente de `gameplay` + `cámara` (`detected_pair`).
- **Nuevos endpoints en FastAPI (`apps/server/clipsserver/api/routes.py`)**: `GET /drive/status`, `GET /drive/auth/url`, `GET /drive/auth/callback`, `POST /drive/auth/disconnect`, `GET /drive/files` y `POST /drive/sessions` (descarga resumible concurrente en `ApiPool` con telemetría SSE `stage_progress`).
- **Pestaña «Desde Drive» en `/sessions` y panel OAuth en `/settings`**: Explorador visual de carpetas y videos con selección en 1 clic del par detectado, botones individuales «Usar como Juego» / «Usar como Cámara» y asistente de vinculación OAuth 2.0 con ventana emergente y código manual de respaldo.

> [!warning] ⚠️ Cambia para ti
> - En `/sessions` ahora puedes alternar entre **«Ruta en Servidor»** y **«Desde Drive»** para explorar tus carpetas de Google Drive y lanzar sesiones sin copiar rutas manualmente.
> - En `/settings` dispones de la nueva sección **«4. Conexión Directa a Google Drive (OAuth 2.0 y Explorador)»** para elegir entre `local`, `oauth` o `service_account` y vincular tu cuenta con un clic.

---

## [2.0.0] — 2026-11-07

### 🌟 Monorepo unificado y arquitectura declarativa v2

Esta versión consolida el sistema en una arquitectura modular completa con servidor FastAPI, frontend Next.js 15 y 7 paquetes especializados.

#### Qué cambió
- **Contrato EditPlan v2**: Migración a esquema declarativo estricto con soporte de tipos TypeScript autogenerados (`codegen.py`).
- **Compositor C++ acelerado (`FastCompositor`)**: Implementación de transformaciones afines en C++ (`cv2.warpAffine`) para zooms y paneos sub-píxel con curvas `outBack` e `inOutSine`.
- **Subtitulado animado libass**: Compilación de subtítulos Hormozi con resaltado dinámico palabra por palabra en amarillo (`#FFD400`) y verde eléctrico (`#39FF14`).
- **Normalización sonora en 2 pasadas**: Integración de filtro lineal `loudnorm` para fijar el audio a $-14\text{ LUFS}$ y $-1.0\text{ dBTP}$.
- **Panel de control dinámico `/settings`**: Edición de claves de API en caliente con enmascaramiento seguro y probador de conexión integrado.
- **Catálogo visual de 42 emojis**: Iconos RGBA supersampled a $128 \times 128\text{ px}$.
- **Perfiles de jerga (*Keyterms*)**: Diccionarios específicos por videojuego (Valorant, CS2) para mejorar la precisión fonética de Deepgram.
- **Notificaciones por Webhook**: Entrega de alertas y enlaces de descarga a Discord y Slack.

> [!warning] ⚠️ Cambia para ti
> - La configuración ahora se gestiona preferentemente desde el navegador en `http://127.0.0.1:3040/settings`.
> - Los clips editados manualmente en el editor quedan protegidos bajo el estado `EDITED` y no se sobrescriben en reprocesamientos automáticos.
> - La variable de entorno para el límite de presupuesto pasa a denominarse `CLIPS_MAX_BUDGET_USD` (por defecto \$9.00 USD).

---

## [1.0.0] — 2026-10-15

### Prototipo inicial de pipeline híbrido
- Extracción básica de pistas mediante FFmpeg en línea de comandos.
- Sincronización manual de desfases.
- Transcripción secuencial con Whisper API.
- Generación de video vertical simple con corte horizontal fijo.

---

## 🔗 Relacionado
- [[Resumen ejecutivo]]
- [[FAQ]]
- [[Arquitectura general]]