---
titulo: Mantenimiento y Limpieza
tipo: operacion
estado: vigente
audiencia: [tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/operacion, area/mantenimiento]
---

# Mantenimiento, Limpieza de Disco y Base de Datos

> [!abstract] En pocas palabras
> Políticas de mantenimiento preventivo para evitar que el disco duro se llene de archivos temporales de audio o fragmentos de tracking, junto con rutinas para optimizar la base de datos SQLite.

---

## 🧹 Política de Vida Útil de Archivos Temporales ([[Glosario#TTL|TTL]])

El procesamiento multimedia produce archivos intermedios pesados (fragmentos de audio Opus, pistas WAV temporales, capturas de frames para tracking).

FarmClips incluye el módulo `cleanup_temp_media()` que corre automáticamente al arrancar el servidor:
- **Variable de control**: `CLIPS_TEMP_TTL_DAYS = 7` (días de retención).
- **Archivos purgados**:
  - `data/sessions/<id>/media/opus_chunks/*.opus`
  - `data/sessions/<id>/media/*.wav`
  - `data/render_cache/temp_*.mp4`
- **Archivos que NUNCA se eliminan**:
  - Videos finales renderizados en `renders/*.mp4`.
  - Contratos declarativos `editplan.json` y `editplan.user.json`.
  - Transcripciones de frases `utterances.json`.
  - Registros de la base de datos `clipsapp.db`.

---

## 🛠️ Ejecución Manual de Limpieza

Puedes forzar una purga inmediata sin reiniciar el servidor llamando al endpoint:

```bash
curl -X POST http://127.0.0.1:8790/maintenance/cleanup \
     -H "Content-Type: application/json" \
     -d '{"ttl_days": 1.0, "include_inputs": false}'
```

Salida esperada:
```json
{
  "purged_files": 42,
  "freed_bytes": 1428571428,
  "freed_human": "1.33 GB"
}
```

---

## 🗄️ Optimización de SQLite (Compactación)

Tras procesar cientos de sesiones, la base de datos `clipsapp.db` puede beneficiarse de una compactación para reducir su tamaño y reordenar índices:

```powershell
# Ejecutar mantenimiento de la base de datos
sqlite3 data\clipsapp.db "PRAGMA optimize; VACUUM;"
```

---

## 🔗 Relacionado
- [[Despliegue y Ejecución]]
- [[Monitoreo y Presupuesto]]
- [[Modelo de datos]]