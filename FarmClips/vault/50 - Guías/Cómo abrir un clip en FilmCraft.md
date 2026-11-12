---
titulo: "Cómo abrir un clip en FilmCraft"
tipo: guia
estado: vigente
audiencia: [creadores, editores]
responsable: Equipo FarmClips
actualizado: 2026-11-12
etiquetas: [guia, nle, filmcraft, exportacion]
---

# 🎬 Cómo abrir un clip en FilmCraft

> [!abstract] En pocas palabras
> Pasa de la previsualización web de FarmClips a un entorno de edición no lineal (NLE) profesional en **FilmCraft** con un solo clic, sin mover archivos manualmente y con todas las pistas sincronizadas al milisegundo.

---

## 🚀 Paso a Paso

1. **Abre cualquier clip en el Web Studio:**
   - Entra a `http://127.0.0.1:3040/editor/[clipId]`.
2. **Revisa tus cortes y ajustes rápidos:**
   - Puedes ajustar subtítulos, volumen, encuadre o cortes.
3. **Haz clic en el botón «Abrir en FilmCraft»:**
   - Ubicado en la barra superior junto a «Guardar cambios».
   - Si tenías cambios sin guardar, FarmClips los guarda automáticamente antes de exportar.
4. **FilmCraft se abre automáticamente:**
   - Si FilmCraft ya estaba abierto con su bridge activo, el proyecto se cargará en la ventana existente sin abrir procesos duplicados y se traerá al frente.
   - Si no estaba abierto, se iniciará con la secuencia vertical (1080×1920) lista y aceleración por GPU (`--graphics default`).
   - En la interfaz web aparecerá un banner de éxito con opciones adicionales:
     - `[📁 Abrir carpeta]`: Abre el Explorador de Windows con el archivo `.fcproj` seleccionado directamente.
     - `[📥 Descargar .fcproj]`: Descarga una copia directa del proyecto para respaldos o edición manual.

---

## 🎛️ Pistas que encontrarás en FilmCraft

| Pista | Nombre | Contenido |
|---|---|---|
| **V1** | `V1 Gameplay` | Video del juego, posicionado en la región inferior (o pantalla completa). |
| **V2** | `V2 Cámara` | Video del streamer, recortado con seguimiento facial y keyframes de zoom. |
| **V3** | `V3 Overlays` | Capa para elementos gráficos y textos. |
| **A1** | `A1 Mic` | Audio de la voz del streamer con la ganancia configurada. |
| **A2** | `A2 Juego` | Audio del juego con keyframes automáticos de ducking (atenuación al hablar). |
| **A3** | `A3 SFX` | Efectos de sonido colocados en sus instantes exactos. |

Además, los subtítulos de cada frase aparecen como **marcadores** en el timeline para que puedas saltar de una frase a otra rápidamente.

---

## ⚙️ Configuración y Solución de Problemas

- Si el botón aparece deshabilitado o avisa que no encuentra FilmCraft:
  - Entra a `/settings`.
  - Verifica la sección **FilmCraft NLE & Copiloto MCP**.
  - Si instalaste FilmCraft en una carpeta personalizada, puedes configurar la variable `CLIPS_FILMCRAFT_PATH`.
- **Control server y token:** FilmCraft requiere `FILMCRAFT_CONTROL_TOKEN` (64 caracteres hexadecimales) para su servidor de control loopback (puerto 9876). FarmClips lo genera y persiste automáticamente en `%LOCALAPPDATA%\FilmCraft\.farmclips_control_token` y en el entorno del usuario (`HKCU\Environment`).
- **Ventana y asociación en Windows:** FarmClips asocia automáticamente la extensión `.fcproj` en el Registro de Windows (`HKCU\Software\Classes\.fcproj`) configurando la apertura interactiva mediante el Shell (`Shell.Application` / `os.startfile`) con `--graphics default` y el puerto de control, asegurando que la ventana aparezca siempre en el monitor del usuario y pase al frente. Si por alguna razón de permisos el proceso no emerge, el botón `[📁 Abrir carpeta]` permite abrirlo de inmediato con doble clic desde el Explorador.

---

## 🔗 Relacionado
- [[Cómo usar el copiloto con Claude Desktop y Antigravity]]
- [[Motor de Edición Web Studio]]
- [[ADR-006 Integración con FilmCraft y copiloto MCP]]
