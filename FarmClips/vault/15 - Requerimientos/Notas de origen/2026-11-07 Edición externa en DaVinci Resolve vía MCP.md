---
titulo: "2026-11-07 · Edición externa en DaVinci Resolve vía MCP"
tipo: origen
estado: vigente
audiencia: [negocio, tecnico]
fuente: "chat"
participantes: [Sebas]
actualizado: "2026-11-07"
etiquetas: [tipo/origen]
---

# 🗒️ 2026-11-07 · Edición externa en DaVinci Resolve vía MCP

> [!abstract] En pocas palabras
> Solicitud para trasladar y delegar la edición de video de los clips curados hacia DaVinci Resolve mediante el protocolo MCP (Model Context Protocol), operando de manera local junto con la opción de renderizado local existente.

## 📥 Notas originales
Este nuevo requerimiento hazlo en una rama nueva.
Quiero trasladar la edicion del video a algo aparte, me refiero a daviccinci resolve mediante MCP, se requiere usar la otra opcion de manera local lo cual es aceptable. Entonces quiero desarrollar esta idea y funcionalidad

## 📤 Qué salió de aquí
- [[HU-001 Edición y exportación de clips en DaVinci Resolve mediante MCP local|HU-001]] — Edición y exportación de clips en DaVinci Resolve mediante MCP local

## ❓ Dudas detectadas
- Ninguna: se soporta tanto la conexión MCP / Scripting directo (`DaVinciResolveScript`) hacia DaVinci Resolve local como la generación de paquete FCPXML 1.9 + SRT/ASS + Script Python local compatible con DaVinci Resolve Free y Studio, manteniendo la convivencia con el renderizador local FFmpeg.

## 🔗 Relacionado
- [[Requerimientos]]
