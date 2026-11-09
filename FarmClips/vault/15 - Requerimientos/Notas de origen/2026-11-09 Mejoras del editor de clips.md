---
titulo: Mejoras del editor de clips
tipo: nota-origen
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
fecha: 2026-11-09
fuente: solicitud-usuario
actualizado: 2026-11-09
etiquetas: [requerimientos, origen, area/frontend, area/render, editor]
---

# 🗒️ Nota de origen — Mejoras del editor de clips

> [!abstract] En pocas palabras
> Se pidió revisar el editor de clips y proponer un plan de mejora. El plan aprobado corrige fallos al editar, agrega corrección de frases, cambio de inicio/final del clip y guardado automático, y acelera el render en Mac sin tocar Windows.

## 🗣️ Solicitud original del usuario

> Revisa la parte de edición de clips y genera el plan de mejora.

Respuesta al plan propuesto:

> Si hazlo, pero la que es especificamente para Mac solo afectaria cuando se use en mac y en windows seguiria usando la otra forma, correcto? Si no es asi, no lo apliques.

## 🔍 Interpretación técnica
1. **Fallos del editor**: `Espacio` no pausaba, el visor no se repintaba en pausa, el historial registraba efectos dentro de `setState` y mutaba el preset al arrastrar subtítulos, y cada letra era un paso de deshacer.
2. **Texto de subtítulos**: corregir una frase completa aunque cambie el número de palabras.
3. **Tramo del clip**: mover inicio y final y activar o no los cortes rápidos sin reprocesar la sesión.
4. **Guardado automático** y aviso al salir.
5. **Render en Mac**: VideoToolbox solo cuando `sys.platform == "darwin"`, con calidad igual a libx264 medida con VMAF; Windows mantiene NVENC → libx264.

## Historias derivadas
- [[HU-004 Edición confiable de clips tramos frases y guardado automático]] (Épica: [[EP-02 Claridad y Experiencia de Usuario en Web Studio]])

---

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[HU-004 Edición confiable de clips tramos frases y guardado automático]]
- [[Motor de Edición Web Studio]]
- [[Motor de Renderizado y Subtítulos]]
