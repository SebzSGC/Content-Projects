---
titulo: "ADR-006 Integración con FilmCraft y copiloto MCP"
tipo: decision
estado: vigente
audiencia: [tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-12
etiquetas: [tipo/decision, area/nle, area/mcp, area/interchange]
---

# ADR-006: Integración con FilmCraft y copiloto conversacional MCP

> [!abstract] En pocas palabras
> Por qué FarmClips traduce deterministamente su `EditPlan v2` a un proyecto nativo de FilmCraft (`.fcproj`) mediante código Python puro (sin IA en el montaje), abre la aplicación localmente y expone un servidor MCP stdio para asistencia contextual con Claude Desktop y Antigravity.

---

## 🎯 Contexto y Problema

FarmClips resuelve eficientemente la ingesta, sincronización de audio, detección de momentos clave, recorte facial en CPU y composición rápida vertical (9:16). Sin embargo, ciertos clips requieren retoques editoriales finos:
1. Reorganización milimétrica de transiciones o pistas complejas.
2. Intervención manual en un editor de video no lineal (NLE) de escritorio.
3. Deseo del usuario de poder interactuar en lenguaje natural con su proyecto mediante un copiloto de IA (como Claude Desktop o Antigravity) que conozca el contexto del clip (transcripción, cortes, encuadres).

Construir un NLE completo dentro del navegador es costoso y redundante. Pasar los datos por un LLM para ensamblar el proyecto gastaría tokens innecesariamente y carecería de precisión determinista milimétrica.

---

## ⚖️ Decisión adoptada

Adoptar una arquitectura híbrida de exportación y asistencia:
1. **D1 · Montaje determinista en código:** La transformación de `EditPlan v2` a proyecto FilmCraft (`.fcproj`) se realiza exclusivamente con código Python en el paquete `clipsinterchange`. Ningún token ni llamada a LLM interviene en la colocación de cortes o keyframes.
2. **D2 · La interfaz sigue siendo web:** El estudio `apps/web` (Next.js 15) añade el botón «Abrir en FilmCraft». El backend local FastAPI (`127.0.0.1:8790`) exporta los archivos a `data/exports/filmcraft/` y lanza el proceso de escritorio mediante un subproceso desacoplado y seguro (`FilmCraftLauncher`).
3. **D3 · MCP como copiloto de asistencia, no de ensamblado:**
   - FilmCraft expone su propio servidor MCP nativo (`filmcraft-cli mcp --bridge`) para manipular la interfaz y timeline de FilmCraft.
   - FarmClips expone `farmclips-mcp` (stdio) para brindar contexto (sesiones, clips, `EditPlan`, transcripción con marcas de tiempo) y permitir modificaciones controladas validadas con Pydantic.
4. **D4 · Abstracción detrás de `TimelineExporter`:**
   - Se crea la interfaz `TimelineExporter` con implementaciones `FilmCraftExporter` (principal) y `OtioExporter` (fallback OpenTimelineIO para DaVinci / Premiere).
5. **D5 · Base de tiempo racional:**
   - Todos los tiempos se convierten de segundos a ticks racionales exactos (`254,016,000,000` ticks por segundo) utilizando `fractions.Fraction` para evitar desviaciones por redondeo de números flotantes.
6. **Privacidad:**
   - Siguiendo los principios de [[ADR-001 Arquitectura Híbrida IA Nube y Proceso Local|ADR-001]], los archivos de video y audio **nunca salen de la máquina local**. Únicamente el texto de la transcripción y metadatos viajan si el usuario decide consultar activamente a Claude Desktop con el copiloto.

---

## ✅ Consecuencias

- **Positivas**:
  - Salida profesional instantánea: el clip se abre en un NLE acelerado por GPU con todas sus pistas sincronizadas.
  - El copiloto MCP tiene visión semántica del contenido (quién habló y qué dijo) y capacidad de ejecutar acciones en la app de edición.
  - Cero costo de API para la exportación y el montaje.
  - Reutilización de los algoritmos de encuadre ya calibrados en `fast_compositor.py`.
- **Negativas / Mitigaciones**:
  - Requiere que el usuario tenga FilmCraft instalado en su PC (se detecta automáticamente y se ofrece configuración en `/settings`).
  - Si una propiedad de estilo avanzada (ej. ciertos easings de animación o contornos) no tiene equivalente 1:1 en FilmCraft, el exportador emite una lista estructurada de `warnings` de fidelidad.

---

## 🔗 Relacionado
- [[EP-03 Edición profesional en FilmCraft con copiloto MCP]]
- [[Contrato EditPlan v2]]
- [[ADR-001 Arquitectura Híbrida IA Nube y Proceso Local]]
- [[Referencia API REST y SSE]]
