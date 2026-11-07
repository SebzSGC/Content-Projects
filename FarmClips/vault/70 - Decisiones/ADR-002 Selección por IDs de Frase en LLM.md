---
titulo: "ADR-002 Selección por IDs de Frase en LLM"
tipo: decision
estado: vigente
audiencia: [tecnico]
responsable: Equipo FarmClips
actualizado: 2026-11-07
etiquetas: [tipo/decision, area/ia]
---

# ADR-002: Selección por IDs de Frase en el LLM y Ajuste Acústico Local

> [!abstract] En pocas palabras
> Explica por qué el modelo de lenguaje solo elige códigos de frase como `u0015` en vez de inventar números con decimales, dejando el corte milimétrico y el análisis de la respiración al código local.

---

## 🎯 Contexto y Problema

Los modelos de lenguaje grandes (LLMs como GPT o Gemini) son excelentes comprendiendo el humor, la tensión dramática y la narrativa de un diálogo, pero **son deficientes realizando operaciones aritméticas de coma flotante continuas**. 

Cuando se le pide a un LLM que responda con tiempos exactos (p. ej. `start: 124.845, end: 156.210`):
1. **Alucinaciones numéricas**: Tiende a inventar marcas de tiempo que caen a la mitad de una palabra o dentro de un silencio muerto.
2. **Consumo masivo de tokens**: Enviar al LLM estructuras JSON con cada palabra repetida con sus campos `start` y `end` multiplica el tamaño del prompt por diez, encareciendo el costo y superando las ventanas de contexto.

---

## ⚖️ Decisión adoptada

Dividir la responsabilidad entre comprensión semántica y precisión física:
1. **El LLM solo ve y responde con IDs compactos**: El texto se formatea en frases lingüísticas (**[[Glosario#Utterance|Utterances]]**) con identificadores secuenciales cortos (`[u0001]`, `[u0002]`, ..., `[u9999]`). El LLM solo debe responder:
   ```json
   {"start_id": "u0045", "end_id": "u0048", "score": 92}
   ```
2. **El código local resuelve los tiempos**: El módulo `selection/resolver.py` busca las palabras físicas en la base de datos y analiza la envolvente acústica a 100 Hz para encontrar el punto de silencio exacto antes del **[[Glosario#Ataque Acústico|ataque acústico]]** de la primera consonante.

---

## ✅ Consecuencias

- **Positivas**:
  - Reducción del 82 % en el consumo de tokens de entrada al LLM.
  - Cero cortes abruptos de palabras a la mitad.
  - Transición sonora completamente natural y sin clics digitales en el audio.
- **Negativas / Mitigaciones**:
  - Exige que el pipeline de transcripción mantenga una correspondencia biunívoca estricta entre palabras y frases (implementado en `group_words_into_utterances`).

---

## 🔗 Relacionado
- [[Núcleo de Señales y Selección]]
- [[Flujo 3 Curación con LLM]]
- [[Proveedores de IA y Resiliencia]]