---
id: HU-012
titulo: Rediseño integral del Web Studio inspirado en Astryx de Meta
tipo: historia
epica: EP-02
estado: vigente
audiencia: [todos]
responsable: Equipo FarmClips
prioridad: alta
estimacion: L
avance: 0
fecha_inicio: 2026-11-13
fecha_fin: 2026-11-13
origen: "[[2026-11-13 Auditoría y rediseño integral del frontend con Astryx]]"
afecta:
  - "[[Motor de Edición Web Studio]]"
  - "[[Arquitectura general]]"
actualizado: 2026-11-13
etiquetas: [requerimientos, historia, area/frontend, diseno, astryx]
estado_historia: hecho
inicio: 2026-11-13
fin: 2026-11-13
progreso: 0
fin_real: 2026-11-13
---

# 📗 HU-012 — Rediseño integral del Web Studio inspirado en Astryx de Meta

> [!abstract] En pocas palabras
> Transformación visual y arquitectónica de `apps/web` adoptando los principios, tokens semánticos, jerarquía de superficies y patrones de escritorio macOS de **Astryx de Meta**, unificando todas las vistas del estudio bajo una identidad moderna y profesional.

> [!info] Historia de usuario
> **Como** creador de contenido y operador de FarmClips,
> **quiero** trabajar en una interfaz de escritorio cohesiva, minimalista y bien jerarquizada inspirada en Astryx de Meta y macOS,
> **para** gestionar sesiones, editar clips a 60 fps, auditar el presupuesto y ajustar proveedores con máxima claridad visual, velocidad de respuesta y consistencia entre pantallas.

## ✅ Criterios de aceptación
- [x] **Dado** el sistema de estilos de `apps/web`, **cuando** se carga cualquier ruta del estudio, **entonces** se aplican tokens semánticos de superficie (`body`, `surface`, `card`, `popover`, `muted`), elevación por bisel de 1 px (`--shadow-low/med/high`), radios concéntricos (`--radius-inner` a `--radius-page`), tipografía `Figtree` + `JetBrains Mono` y soporte de tema oscuro/claro sin manchas difuminadas decorativas ni escalados bruscos en hover.
- [x] **Dado** el marco principal de navegación (`TopNav.tsx` / `AppShell`), **cuando** el usuario navega entre módulos en escritorio o móvil, **entonces** dispone de una barra lateral colapsable (`SideNav`) estilo macOS y una cabecera contextual limpia con migas de pan, estado de conexión en tiempo real, resumen de billetera y conmutador de apariencia.
- [x] **Dadas** las vistas de **Sesiones** (`/sessions`) y **Detalle de Sesión** (`/sessions/[id]`), **cuando** el usuario explora carpetas de Google Drive o revisa sesiones y clips generados, **entonces** los datos densos se presentan en filas estructuradas con buscador y filtro de estado, mientras que los resúmenes y clips 9:16 usan tarjetas proporcionadas con radios concéntricos.
- [x] **Dado** el **Editor de Clips** (`/editor/[clipId]`), **cuando** el usuario edita subtítulos, reencuadra cámaras o ajusta el tramo del clip (`handleRetime`), **entonces** el editor comparte el mismo lenguaje visual del estudio, organiza su inspector con pestañas `TabList` y atajos `Kbd`, y reemplaza el `window.confirm` nativo del navegador por un diálogo modal accesible (`AlertDialog`), manteniendo intacto el lienzo a 60 fps y el mezclador Web Audio API.
- [x] **Dadas** las vistas de **Configuración** (`/settings`) y **Consumo y Presupuesto** (`/analytics`), **cuando** el usuario administra proveedores o consulta el gasto de IA, **entonces** `/settings` ofrece navegación lateral por categorías (`settings-sidebar` maestro-detalle) con barra de guardado accesible, y `/analytics` presenta métricas tabulares, cuotas gratuitas y auditoría en tablas de alta legibilidad.

## 🛠️ Tareas técnicas
- [x] Implementar tokens semánticos Astryx (`surface`, `border`, `radius`, `shadow`, `motion`, temas `dark`/`light`) en `apps/web/src/app/globals.css` y configurar `Figtree` + `JetBrains Mono` en `apps/web/src/app/layout.tsx`.
- [x] Expandir `apps/web/src/components/ui.tsx` y `apps/web/src/components/StepProgress.tsx` con primitivas inspiradas en Astryx (`Card`, `Button`, `TabList`, `StatusDot`, `AlertDialog`, `Kbd`, `EmptyState`, `SectionHeader`) manteniendo compatibilidad con las exportaciones existentes.
- [x] Rediseñar `apps/web/src/components/TopNav.tsx` como un `AppShell` de escritorio con `SideNav` colapsable y barra superior contextual.
- [x] Rediseñar y unificar `apps/web/src/app/sessions/page.tsx`, `apps/web/src/app/sessions/[id]/page.tsx`, `apps/web/src/app/editor/[clipId]/page.tsx`, `apps/web/src/app/settings/page.tsx` y `apps/web/src/app/analytics/page.tsx`.
- [x] Validar compilación TypeScript (`tsc --noEmit`), build de producción (`next build`) y suite de pruebas (`pytest -v`).

## 📝 Registro de avance
- **2026-11-13**: Auditoría completa de `apps/web`, investigación de `@astryxdesign/core@0.7.16` y `@astryxdesign/theme-neutral@0.7.16`, implementación integral en código y validación de compilación (`tsc --noEmit` + `next build`) completadas.

## 📝 Bitácora

- 2026-11-13 · Sin iniciar → **En progreso** · Inicio de auditoría, diseño de sistema de tokens Astryx e implementación en apps/web

---
- 2026-11-13 · En progreso → **Hecho** · Rediseño integral inspirado en Astryx de Meta implementado y validado con tsc y next build

## 🔗 Relacionado
- [[EP-02 Claridad y Experiencia de Usuario en Web Studio]]
- [[2026-11-13 Auditoría y rediseño integral del frontend con Astryx]]
- [[Motor de Edición Web Studio]]
- [[Arquitectura general]]
