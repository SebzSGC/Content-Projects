---
titulo: Referencia de API REST y SSE
tipo: api
estado: vigente
audiencia: [tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-09
etiquetas: [tipo/api, area/backend]
---

# Referencia de API REST y Eventos en Tiempo Real (SSE)

> [!abstract] En pocas palabras
> Catálogo exhaustivo de todos los endpoints HTTP y flujos de eventos que expone el servidor FastAPI en `http://127.0.0.1:8790`.

---

## 📡 1. Endpoints de Diagnóstico y Eventos

| Método | Endpoint | Descripción | Formato respuesta |
|---|---|---|---|
| `GET` | `/health` | Chequeo de salud: binarios de FFmpeg, modelos y presets cargados. | `application/json` |
| `GET` | `/events` | Flujo continuo de eventos Server-Sent Events (**[[Glosario#SSE\|SSE]]**). | `text/event-stream` |

---

## 🎬 2. Gestión de Sesiones (`/sessions`)

| Método | Endpoint | Descripción | Parámetros / Cuerpo |
|---|---|---|---|
| `GET` | `/sessions` | Lista todas las sesiones con filtros opcionales. | `?limit=50&offset=0` |
| `POST` | `/sessions` | Registra una nueva sesión a partir de videos locales. | JSON: `title, gameplay_path, camera_path, auto_start` |
| `GET` | `/sessions/{id}` | Retorna el detalle completo de una sesión y sus clips. | URL: `{id}` de sesión |
| `POST` | `/sessions/{id}/start` | Inicia o reanuda la ejecución del pipeline para la sesión. | URL: `{id}` |
| `POST` | `/sessions/{id}/cancel` | Cancela de inmediato las tareas en ejecución de la sesión. | URL: `{id}` |
| `POST` | `/sessions/{id}/sync/manual`| Inyecta calibración manual de sincronización acústica. | JSON: `shift_sec, scale` |
| `DELETE`| `/sessions/{id}` | Elimina la sesión de la base de datos y sus archivos. | `?delete_files=true` |

---

## ✂️ 3. Gestión y Edición de Clips (`/clips`)

| Método | Endpoint | Descripción | Parámetros / Cuerpo |
|---|---|---|---|
| `GET` | `/clips/{clip_id}` | Obtiene los datos del clip, puntuaciones y EditPlan. | URL: `{clip_id}` |
| `PUT` | `/clips/{clip_id}/editplan` | Guarda modificaciones manuales del EditPlan (estado `EDITED`). | JSON: objeto `EditPlan` completo |
| `POST`| `/clips/{clip_id}/retime` | Cambia el inicio y el final del clip (segundos de la grabación) y activa o no los cortes rápidos; vuelve a generar cámara, cortes y subtítulos conservando el texto corregido y el título. Duración entre 5 s y 180 s. Responde `{clip, editplan}`; `400` si el tramo no es válido, `404` si el clip no existe. | JSON: `start, end, jump_cuts` (por defecto `true`) |
| `POST`| `/clips/{clip_id}/render` | Solicita renderizado manual de un clip en borrador o final. | JSON: `quality: "draft"\|"final"` |
| `GET` | `/clips/{clip_id}/thumbnail` | Obtiene o genera una miniatura vertical 9:16 compuesta en caché (gameplay + cámara). | `?width=540` |
| `GET` | `/clips/{clip_id}/file` | Descarga o reproduce el render MP4 (`final` o `draft`) del clip. | `?quality=draft\|final&download=bool` |
| `GET` | `/clips/{clip_id}/stream/{video}` | Servidor de streaming con soporte de rangos HTTP 206. | `{video}`: `"gameplay"` o `"camera"` |

---

## ⚙️ 4. Configuración y Mantenimiento (`/settings`, `/maintenance`)

| Método | Endpoint | Descripción | Parámetros / Cuerpo |
|---|---|---|---|
| `GET` | `/settings` | Devuelve la configuración activa con claves enmascaradas. | JSON seguro |
| `POST` | `/settings` | Actualiza claves, modelos, modo de Drive y presupuesto en `.env` en caliente. | JSON con campos a modificar |
| `POST` | `/settings/test-connection` | Valida credenciales contra las APIs externas en caliente. | JSON: `provider, api_key?, model?` |
| `GET`  | `/budget` | Resumen de presupuesto y consumo en USD acumulado. | JSON: `total_usd, max_budget_usd, remaining_usd, pct` |
| `GET`  | `/analytics/summary` | Resumen global de sesiones, clips curados y métricas. | JSON analítico |
| `GET`  | `/analytics/breakdown` | Desglose de costos por proveedor y modelo de IA. | JSON por proveedor |
| `POST` | `/maintenance/cleanup` | Ejecuta purga de archivos temporales según política TTL. | JSON: `ttl_days, include_inputs` |

---

## ☁️ 5. Conexión Directa y Explorador de Google Drive (`/drive`)

| Método | Endpoint | Descripción | Parámetros / Cuerpo |
|---|---|---|---|
| `GET` | `/drive/status` | Estado del conector activo (`local`, `oauth`, `service_account`), correo vinculado y rutas. | JSON de estado |
| `GET` | `/drive/auth/url` | Genera la URL de autorización OAuth 2.0 de Google (`access_type=offline`). | `?redirect_uri=...&state=...` |
| `GET` | `/drive/auth/callback` | Intercambia el código OAuth 2.0 por tokens y persiste `data/drive_oauth_token.json`. | `?code=...&state=...` |
| `POST` | `/drive/auth/disconnect` | Revoca la sesión OAuth local y elimina `data/drive_oauth_token.json`. | Sin cuerpo |
| `GET` | `/drive/files` | Explora carpetas y videos en Drive con migas de pan y par auto-detectado (`detected_pair`). | `?folder_id=...&q=...` |
| `POST` | `/drive/sessions` | Descarga `gameplay` + `cámara` en `ApiPool` con progreso SSE y lanza la sesión. | JSON: `gameplay_file_id, camera_file_id, recording_name?, game_hint?, auto_run?` |

---

## 🔗 Relacionado
- [[FastAPI y Orquestador]]
- [[Motor de Renderizado y Subtítulos]]
- [[Variables de Entorno]]
- [[Comandos CLI y Scripts]]
- [[Monitoreo y Presupuesto]]