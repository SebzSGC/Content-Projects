---
titulo: Auditoría y rediseño integral del frontend con Astryx
tipo: nota-origen
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
fecha: 2026-11-13
fuente: solicitud-usuario
actualizado: 2026-11-13
etiquetas: [requerimientos, origen, area/frontend, diseno, astryx]
---

# 🗒️ Nota de origen — Auditoría y rediseño integral del frontend con Astryx

> [!abstract] En pocas palabras
> Solicitud para auditar, investigar, rediseñar e implementar de forma integral el frontend de FarmClips (`apps/web`) tomando como referencia técnica y de diseño a **Astryx de Meta** (`@astryxdesign/core`), llevando la aplicación a una estética profesional inspirada en aplicaciones nativas de escritorio macOS.

## 🗣️ Solicitud original del usuario

> Quiero realizar una transformación visual y funcional del frontend de nuestra aplicación, tomando como referencia el repositorio oficial de **Astryx de Meta** (`https://github.com/meta/astryx`).
> El objetivo es analizar profundamente este proyecto, comprender sus principios de diseño, arquitectura, componentes, patrones de interfaz, sistema de temas y buenas prácticas, para identificar qué podemos aprovechar y cómo podemos aplicarlo a nuestra aplicación.
> La dirección visual debe ser minimalista, moderna y premium, con inspiración en aplicaciones de escritorio modernas (macOS), jerarquía visual clara, uso inteligente del espacio y microinteracciones sutiles, evitando gradientes innecesarios, exceso de tarjetas sin propósito o bordes por todas partes.

## 🔍 Interpretación técnica
1. **Sistema de tokens semánticos e iluminación macOS (`globals.css`)**: Jerarquía de superficies (`body` → `surface` → `card` → `popover` → `muted`), elevación por bisel de 1 px (`--shadow-low/med/high` con `inset 0 0 0 1px`), radios concéntricos (`--radius-inner` a `--radius-page`), tokens de movimiento precisos (`125ms` / `240ms`) y soporte multi-tema (`Studio Dark` y `Studio Light`).
2. **Tipografía de estudio (`layout.tsx`)**: Sustituir la fuente redondeada `Nunito` por **`Figtree`** (UI/encabezados) y **`JetBrains Mono`** (códigos de tiempo, telemetría y costos), conservando `"Montserrat ExtraBold"` exclusivamente para el lienzo de video 9:16.
3. **Arquitectura `AppShell` + `SideNav` (`TopNav.tsx`)**: Evolucionar la barra superior aislada hacia un marco de aplicación de escritorio (`AppShell`) con barra lateral colapsable (`SideNav`), cabecera contextual con migas de pan, indicador de salud en vivo, billetera compacta y selector de tema.
4. **Primitivas y componentes reutilizables (`ui.tsx` y `StepProgress.tsx`)**: Incorporar componentes inspirados en Astryx (`Card` con variantes, `Button`, `TabList`, `StatusDot`, `AlertDialog`, `Kbd`, `Segmented`, `EmptyState`) manteniendo compatibilidad total con los módulos actuales.
5. **Rediseño cohesivo de módulos**:
   - **Sesiones (`/sessions`) y Detalle (`/sessions/[id]`)**: Separación clara entre tarjetas de resumen y filas densas de datos (explorador de Google Drive y tabla/lista de sesiones con buscador y filtros).
   - **Editor 60 fps (`/editor/[clipId]`)**: Unificación cromática con el resto del estudio, pestañas `TabList`, atajos `Kbd` visibles y sustitución de `window.confirm` nativo por un diálogo accesible (`AlertDialog`) sin alterar el reloj de hardware ni Web Audio API.
   - **Configuración (`/settings`)**: Patrón maestro-detalle (`settings-sidebar` de Astryx) con navegación lateral por secciones y barra de guardado fija.
   - **Consumo y Presupuesto (`/analytics`)**: Tarjetas de métricas limpias, tablas de cuotas gratuitas y registro de auditoría con jerarquía tipográfica tabular.

## 📤 Qué salió de aquí
- [[HU-012 Rediseño integral del Web Studio inspirado en Astryx de Meta]] (Épica: [[EP-02 Claridad y Experiencia de Usuario en Web Studio]])

---

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[HU-012 Rediseño integral del Web Studio inspirado en Astryx de Meta]]
- [[Motor de Edición Web Studio]]
