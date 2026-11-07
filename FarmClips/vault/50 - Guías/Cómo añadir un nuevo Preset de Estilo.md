---
titulo: Cómo añadir un nuevo Preset de Estilo
tipo: guia
estado: vigente
audiencia: [negocio, tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/guia, area/estilos]
---

# Cómo añadir un nuevo Preset de Estilo

> [!abstract] En pocas palabras
> Tutorial para diseñadores y editores que deseen crear una identidad gráfica personalizada: cambiar los colores de los subtítulos, modificar la posición de las cámaras o usar una tipografía diferente.

---

## 🎨 Estructura de un Preset de Estilo

Los presets se definen como archivos JSON ubicados en:
`packages/styles/clipsstyles/presets/`

Para crear un nuevo preset (p. ej. `mi-estilo-neon.json`), copia como base `hormozi-gaming.json` y personaliza los campos:

```json
{
  "id": "mi-estilo-neon",
  "name": "Estilo Neón Cyberpunk",
  "format": {
    "width": 1080,
    "height": 1920,
    "fps": 60
  },
  "duration": {
    "min_sec": 25.0,
    "max_sec": 55.0
  },
  "layout": {
    "camera_ratio": 0.45,
    "border_px": 6,
    "border_color_hex": "#00F0FF"
  },
  "title": {
    "font_family": "Montserrat ExtraBold",
    "font_size_px": 68,
    "color_hex": "#00F0FF",
    "outline_color_hex": "#000000",
    "outline_px": 6,
    "max_chars_per_line": 16,
    "max_lines": 2
  },
  "captions": {
    "font_family": "Montserrat ExtraBold",
    "font_size_px": 50,
    "color_hex": "#FFFFFF",
    "outline_color_hex": "#000000",
    "outline_px": 4,
    "shadow_px": 3,
    "gameplay_top_third_ratio": 0.25,
    "active_word": {
      "color_hex": "#00F0FF",
      "scale_pct": 108
    },
    "emphasis_word": {
      "color_hex": "#FF003C",
      "scale_pct": 120
    }
  }
}
```

---

## 🧭 Paso a paso de registro y uso

### Paso 1: Guardar el archivo JSON
Guarda el archivo en `packages/styles/clipsstyles/presets/mi-estilo-neon.json`.

### Paso 2: Usar tipografías personalizadas (Opcional)
Si usas una fuente que no está instalada en el sistema de Windows:
1. Copia el archivo `.ttf` a `packages/styles/clipsstyles/fonts/`.
2. Asegúrate de escribir el nombre de la familia tipográfica exacto en el campo `"font_family"`.

### Paso 3: Asignar el preset a tus sesiones
- **De forma global**: En `.env`, define:
  ```env
  CLIPS_STYLE_PRESET=mi-estilo-neon
  ```
- **Por sesión individual**: En la pantalla de creación de sesión en `/sessions`, selecciona tu nuevo preset en el menú desplegable de estilos.

---

## 🔗 Relacionado
- [[Sistema de Estilos y Presets]]
- [[Contrato EditPlan v2]]
- [[Motor de Renderizado y Subtítulos]]