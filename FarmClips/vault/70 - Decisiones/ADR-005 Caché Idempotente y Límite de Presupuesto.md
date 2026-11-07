---
titulo: "ADR-005 Caché Idempotente y Límite de Presupuesto"
tipo: decision
estado: vigente
audiencia: [tecnico, negocio]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/decision, area/seguridad]
---

# ADR-005: Caché Idempotente en SQLite y Límite de Presupuesto en USD

> [!abstract] En pocas palabras
> Explica la regla inquebrantable de FarmClips: "Nunca se paga dos veces por la misma petición de IA", garantizando que los reintentos o reprocesamientos no generen cobros duplicados en las tarjetas de crédito de los usuarios.

---

## 🎯 Contexto y Problema

Cuando se integran modelos de lenguaje y APIs de transcripción de pago por uso en aplicaciones de escritorio:
1. Una interrupción de internet, un reinicio del sistema o un fallo menor en una fase posterior (p. ej. en el renderizado final) suele provocar que los usuarios reintenten la sesión completa.
2. Si el sistema no conserva las respuestas crudas de las APIs, vuelve a transcribir el audio y a reenviar los prompts al LLM, cobrando el doble o el triple innecesariamente.
3. Un bucle de reintento mal programado ante un error 500 puede vaciar el saldo de una cuenta en pocos minutos.

---

## ⚖️ Decisión adoptada

1. **Idempotencia estricta por Hash SHA-256**:
   - Todo archivo de audio genera una firma criptográfica única basada en su contenido y metadatos.
   - Las respuestas completas en crudo devueltas por Deepgram, Groq, Gemini y OpenAI se almacenan en la tabla `artifacts` de la base de datos local SQLite antes de cualquier normalización.
   - Si una tarea se reejecuta con la misma firma, el sistema recupera la respuesta de disco sin tocar la red.
2. **Cortafuegos de Presupuesto (*Budget Guard*)**:
   - Cada llamada registra su costo proyectado en la tabla `api_calls`.
   - Se fija un límite inviolable en la variable de entorno `CLIPS_MAX_BUDGET_USD` (por defecto \$9.00 USD). Si el gasto proyectado supera este monto, el sistema bloquea nuevas salidas y emite un evento SSE de alerta.

---

## ✅ Consecuencias

- **Positivas**:
  - Reintentar o reprocesar una sesión previa cuesta **\$0.00 USD**.
  - Confianza total para el usuario: imposibilidad técnica de facturas sorpresa descontroladas.
  - Facilidad de depuración: permite inspeccionar en `data/artifacts/` el JSON exacto devuelto por los modelos.
- **Negativas / Mitigaciones**:
  - Requiere almacenamiento en disco para la base de datos y la caché (mitigado con la política de limpieza automática TTL de 7 días).

---

## 🔗 Relacionado
- [[Proveedores de IA y Resiliencia]]
- [[Monitoreo y Presupuesto]]
- [[Modelo de datos]]
- [[Runbook · Falla de API o Presupuesto Agotado]]