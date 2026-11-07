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

## [2.0.0] — 2026-11-07 (Versión actual)

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