---
titulo: Registro de Decisiones de Arquitectura (ADR)
tipo: indice
estado: vigente
audiencia: [tecnico, negocio]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/indice, area/decisiones]
---

# 70 · Registro de Decisiones de Arquitectura (ADRs)

> [!abstract] En pocas palabras
> Documenta las decisiones técnicas y de producto fundamentales adoptadas en FarmClips: por qué se eligieron ciertas soluciones, qué alternativas se descartaron y qué consecuencias conllevan.

---

## 📑 Decisiones documentadas

| ADR | Decisión | Por qué se tomó | Estado |
|---|---|---|---|
| [[ADR-001 Arquitectura Híbrida IA Nube y Proceso Local]] | IA en la nube por API y proceso local en máquina. | Evita subir videos de 20 GB y mantiene la GPU libre. | `#estado/vigente` |
| [[ADR-002 Selección por IDs de Frase en LLM]] | Selección mediante IDs `u0001`..`u9999` y corte local a 100 Hz. | Elimina alucinaciones de tiempo y ahorra un 82 % de tokens. | `#estado/vigente` |
| [[ADR-003 Tracking Facial por Clip en CPU]] | MediaPipe BlazeFace acotado por clip en CPU. | Reduce el tiempo de tracking de 35 minutos a 45 segundos. | `#estado/vigente` |
| [[ADR-004 Formato EditPlan Declarativo v2]] | Esquema declarativo JSON v2 para Web y Render. | Permite previsualización instantánea a 60 fps sin re-renderizar. | `#estado/vigente` |
| [[ADR-005 Caché Idempotente y Límite de Presupuesto]] | Caché estricta en SQLite y tope en USD (\$9.00). | Garantiza que nunca se pague dos veces por la misma petición. | `#estado/vigente` |

---

## 🔗 Relacionado
- [[00 - Inicio]]
- [[Arquitectura general]]
- [[Componentes]]