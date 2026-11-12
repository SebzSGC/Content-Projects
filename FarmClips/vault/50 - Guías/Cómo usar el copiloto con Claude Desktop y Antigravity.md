---
titulo: "Cómo usar el copiloto con Claude Desktop y Antigravity"
tipo: guia
estado: vigente
audiencia: [creadores, desarrolladores]
responsable: Equipo FarmClips
actualizado: 2026-11-12
etiquetas: [guia, copiloto, mcp, claude, antigravity]
---

# 🤖 Cómo usar el copiloto con Claude Desktop y Antigravity

> [!abstract] En pocas palabras
> Conecta FarmClips y FilmCraft a tu cliente de IA preferido mediante el protocolo MCP (Model Context Protocol) para pedirle cambios al clip en lenguaje natural, buscar frases en la transcripción y aplicar zooms inteligentes.

---

## 🔒 Privacidad y Costos

> [!IMPORTANT]
> **Privacidad local:**
> Tus videos y audios **nunca salen de tu PC**. Solo viaja el texto de la transcripción y los parámetros numéricos de corte o encuadre hacia Claude.
> Si usas Claude Desktop con tu suscripción Pro/Team, no gastas tokens de API.

---

## ⚙️ 1. Generar la configuración automática

Abre una terminal en la raíz del proyecto y ejecuta:

```powershell
.\.venv\Scripts\python.exe -m clipsserver.main mcp-config
```

Este comando detectará automáticamente la ruta de tu entorno virtual de Python y el ejecutable `filmcraft-cli.exe` de tu máquina, generando un bloque como este:

```json
{
  "mcpServers": {
    "farmclips": {
      "command": "C:\\Users\\...\\FarmClips\\.venv\\Scripts\\python.exe",
      "args": ["-m", "clipsserver.mcp"],
      "env": {
        "FARMCLIPS_API": "http://127.0.0.1:8790"
      }
    },
    "filmcraft": {
      "command": "C:\\Users\\...\\FilmCraft\\filmcraft-cli.exe",
      "args": ["mcp", "--bridge", "127.0.0.1:9876"]
    }
  }
}
```

---

## 💻 2. Conexión en Claude Desktop

1. Abre el archivo de configuración de Claude Desktop:
   - En Windows: `%APPDATA%\Claude\claude_desktop_config.json`
2. Pega el bloque JSON generado dentro de `"mcpServers"`.
3. Reinicia Claude Desktop.
4. Verás el icono del martillo indicando que `farmclips` y `filmcraft` están activos.

---

## 🎮 3. Ejemplos de uso con tu Copiloto

Una vez conectados ambos servidores, puedes pedirle a Claude cosas como:

- **Descubrir contenido:**  
  *«¿Qué clips destacados tengo de la sesión de ayer?»*  
  *(Claude usa `list_clips` y te resume los mejores momentos y sus puntuaciones).*

- **Abrir en el editor:**  
  *«Abre el clip con mejor puntaje en FilmCraft.»*  
  *(Claude ejecuta `open_in_filmcraft`, abriendo el timeline al instante).*

- **Edición semántica:**  
  *«Busca en la transcripción cuando dije "no puede ser" y haz un zoom a la cámara del streamer en ese segundo.»*  
  *(Claude usa `get_transcript` de FarmClips, ubica el segundo exacto y aplica el keyframe en FilmCraft).*

- **Renderizado:**  
  *«Renderiza una prueba rápida (draft) del clip actual para ver cómo quedó.»*  
  *(Claude llama a `render_clip` y te confirma cuando esté listo).*

---

## 🔗 Relacionado
- [[Cómo abrir un clip en FilmCraft]]
- [[ADR-006 Integración con FilmCraft y copiloto MCP]]
- [[Referencia API REST y SSE]]
- [[Comandos CLI y Scripts]]
