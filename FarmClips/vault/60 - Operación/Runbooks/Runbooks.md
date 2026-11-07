---
titulo: Catálogo de Runbooks
tipo: indice
estado: vigente
audiencia: [tecnico, soporte]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/indice, area/runbooks]
---

# 60.1 · Catálogo de Runbooks de Operación

> [!abstract] En pocas palabras
> Protocolos de respuesta rápida y procedimientos estandarizados ante incidentes operativos, fallas de proveedores externos, saturación de hardware o desajustes audiovisuales.

---

## 📑 Procedimientos de emergencia

| Runbook | Cuándo aplicarlo | Tiempo de resolución | Estado |
|---|---|:---:|---|
| [[Runbook · Falla de API o Presupuesto Agotado]] | Ante errores 429, bloqueo por presupuesto (\$9 USD) o fallos de Deepgram/Gemini. | < 2 min | `#estado/vigente` |
| [[Runbook · Desincronización de Audio o Video]] | Si el rostro del jugador no coincide con el sonido del juego o la transcripción. | < 5 min | `#estado/vigente` |
| [[Runbook · Falla de Render o NVENC]] | Ante errores de memoria VRAM de NVIDIA (`OpenEncodeSessionEx`) o caída de FFmpeg. | < 3 min | `#estado/vigente` |

---

## 🔗 Relacionado
- [[Operación]]
- [[Monitoreo y Presupuesto]]
- [[Despliegue y Ejecución]]