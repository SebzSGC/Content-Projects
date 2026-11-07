---
titulo: "ADR-004 Formato EditPlan Declarativo v2"
tipo: decision
estado: vigente
audiencia: [tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/decision, area/contrato]
---

# ADR-004: Formato EditPlan Declarativo v2 y Previsualización Web

> [!abstract] En pocas palabras
> Por qué FarmClips describe la edición como un documento digital estructurado (JSON Schema v2) en vez de generar videos temporales destructivos, permitiendo previsualizaciones instantáneas en el navegador.

---

## 🎯 Contexto y Problema

En los editores automáticos tradicionales de video:
- Cada ajuste menor (corregir una tilde, cambiar un color o mover un recorte 5 %) obliga al sistema a lanzar un comando de FFmpeg que recorta, renderiza y comprime un nuevo video MP4 en disco.
- Esto genera tiempos de espera frustrantes de varios minutos para el creador y satura el disco duro con decenas de archivos intermedios.

---

## ⚖️ Decisión adoptada

Crear un contrato declarativo estricto e inmutable denominado **[[Glosario#EditPlan|EditPlan v2]]**:
1. El EditPlan describe la **intención de edición** en formato JSON: qué trozos de video usar (`ranges`), cómo recortar la cámara (`CropKeyframe`), la lista de palabras y emojis (`CaptionsPlan`) y las ganancias de audio (`AudioPlan`).
2. El estudio web (`apps/web`) interpreta este plano digital directamente en el cliente mediante transformaciones CSS y la **[[Glosario#Web Audio API|Web Audio API]]**.
3. El motor de renderizado final (`clipsrender`) lee exactamente el mismo JSON para compilar el script `.ass` y ejecutar el renderizado acelerado en GPU.

---

## ✅ Consecuencias

- **Positivas**:
  - Previsualización instantánea a 60 fps en tiempo real sin esperas.
  - El usuario puede editar y experimentar con total libertad antes de exportar.
  - Arquitectura desacoplada: el frontend y el backend comparten contratos generados automáticamente vía Pydantic y TypeScript (`codegen.py`).
- **Negativas / Mitigaciones**:
  - Exige mantener paridad exacta de comportamiento visual entre el reproductor Canvas/CSS web y el motor de renderizado de FFmpeg/libass (cubierto mediante pruebas visuales de regresión *Golden tests*).

---

## 🔗 Relacionado
- [[Contrato EditPlan v2]]
- [[Motor de Edición Web Studio]]
- [[Motor de Renderizado y Subtítulos]]