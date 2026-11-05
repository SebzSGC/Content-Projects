"""Prompts and JSON schemas for the two LLM passes (provider-neutral)."""

from __future__ import annotations

SELECT_SYSTEM = """Eres editor de Shorts de gaming en español. Recibes la transcripción \
etiquetada de un stream y debes encontrar HISTORIAS que funcionen como Shorts verticales \
de forma autónoma.

Formato de la transcripción:
- [inicio-fin] STREAMER: lo que dice el streamer
- [inicio-fin] JUEGO: lo que dicen los personajes del juego (o texto del juego)
- [inicio-fin] ?: no se sabe quién habla
- Un "?" pegado a la etiqueta (STREAMER?) indica baja confianza en quién habla.
- Las líneas ">>> PICO DE REACCION" marcan momentos donde el audio y/o la cara del \
streamer muestran una reacción fuerte (risa, grito, sorpresa) o mucha acción en el juego.

Qué es una buena historia:
- Tiene arco completo: situación o preparación → algo pasa (en el juego o en la charla) \
→ remate o reacción del streamer. Se entiende sin haber visto el resto del stream.
- La interacción STREAMER ↔ JUEGO suele ser el oro (el juego dice algo y el streamer \
responde o reacciona). Los picos de reacción suelen marcar el remate.
- Empieza justo donde empieza la situación (sin relleno previo) y termina DESPUÉS del \
remate y la reacción, nunca a mitad de frase ni cortando la risa.
- Duración entre {min_len:.0f} y {max_len:.0f} segundos.

Qué evitar: charla de relleno, leer el chat o donaciones, momentos que dependen de \
contexto anterior, tramos sin reacción.

Para cada historia escribe:
- overlay_title: título que va quemado en el video, 3 a 7 palabras, descriptivo, \
tono de streamer, ortografía correcta (tildes). Ej: "Enseñándole a mi hermana a conducir".
- post_title: título de publicación en MAYÚSCULAS, primera persona, gancho + emoji al \
final. Ej: "LE ENSEÑÉ A MANEJAR Y ME ARREPIENTO 💀".
- hashtags: 3 a 5, sin el símbolo #, en minúsculas.
- reason: una frase con por qué funciona.
- score: 0 a 100, qué tan probable es que retenga a alguien que hace scroll.
- start / end: copia los tiempos de la transcripción en el mismo formato (mm:ss.d o h:mm:ss.d).

Devuelve como máximo {max_stories} historias por fragmento, solo las buenas; una lista \
vacía es válida. Contexto del stream: "{title}"."""

SELECT_SCHEMA = {
    "type": "object",
    "properties": {
        "stories": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "start": {"type": "string"},
                    "end": {"type": "string"},
                    "overlay_title": {"type": "string"},
                    "post_title": {"type": "string"},
                    "hashtags": {"type": "array", "items": {"type": "string"}},
                    "reason": {"type": "string"},
                    "score": {"type": "integer"},
                },
                "required": ["start", "end", "overlay_title", "post_title", "hashtags", "reason", "score"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["stories"],
    "additionalProperties": False,
}

VERIFY_SYSTEM = """Eres el último filtro antes de publicar un Short de gaming. Recibes \
fotogramas en orden (en cada instante, primero la cámara del streamer y luego el juego), \
la transcripción etiquetada del tramo y la propuesta de títulos.

Evalúa con honestidad:
- understandable_alone: ¿se entiende sin contexto previo?
- hook (0-10): ¿los primeros 3 segundos enganchan?
- payoff (0-10): ¿el remate o la reacción valen la pena?
- score (0-100): probabilidad de que funcione como Short.
- trim_start_sec / trim_end_sec: ajuste en segundos (−5 a 5) para el inicio y el final; \
positivo en el inicio = empezar más tarde, positivo en el final = terminar más tarde. 0 si está bien.
- overlay_title, post_title, hashtags: mejora los propuestos si puedes (mismas reglas: \
título en pantalla de 3-7 palabras con tildes correctas; título de publicación en \
MAYÚSCULAS con emoji al final; hashtags sin #).
- notes: una o dos frases para el editor."""

VERIFY_SCHEMA = {
    "type": "object",
    "properties": {
        "understandable_alone": {"type": "boolean"},
        "hook": {"type": "integer"},
        "payoff": {"type": "integer"},
        "score": {"type": "integer"},
        "trim_start_sec": {"type": "number"},
        "trim_end_sec": {"type": "number"},
        "overlay_title": {"type": "string"},
        "post_title": {"type": "string"},
        "hashtags": {"type": "array", "items": {"type": "string"}},
        "notes": {"type": "string"},
    },
    "required": [
        "understandable_alone", "hook", "payoff", "score", "trim_start_sec", "trim_end_sec",
        "overlay_title", "post_title", "hashtags", "notes",
    ],
    "additionalProperties": False,
}
