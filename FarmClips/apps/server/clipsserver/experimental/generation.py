"""Editorial rules distilled from the published examples and comparative reviews."""

EDITORIAL_GUIDANCE = """Perfil editorial FarmClips 1.0. Estas pautas prevalecen sobre las directrices generales de selección y corte:
- Prioriza un giro comprensible y su consecuencia. Busca sustos con preparación y reacción, fallos o retos con desenlace, humor con remate, y llamadas o conversaciones que desarrollan una situación.
- Usa picos de sonido, movimiento y cambios de pantalla como pistas. Requiere contexto para dar peso a menús, pantallas de resultados, desplazamientos y tareas repetitivas.
- Comienza en la primera frase necesaria para entender el momento. Termina cuando se entiende la reacción, el resultado o el remate. Una llamada puede necesitar más desarrollo tras el primer pico.
- Devuelve los IDs de frase existentes y respeta el máximo del editor indicado en los parámetros. Cada propuesta es un tramo continuo. Evita atribuir acciones o reacciones que la evidencia disponible no permite identificar.
- Basa score principalmente en la claridad del contexto, lo que sucede y su desenlace. Devuelve menos propuestas si hay pocas que lo justifiquen."""


def selection_guidance(window_seconds: float) -> str:
    return EDITORIAL_GUIDANCE + f"""

Formato por propuesta. Evalúa secuencias de hasta {window_seconds:g} segundos del VOD.
- individual: un acontecimiento autónomo. Escoge IDs que abarquen el contexto útil, reacción y desenlace. Devuelve los candidatos breves que merezcan revisión aunque no alcancen 40 s.
- recopilacion: usa segments con dos o más tramos separados en orden del VOD, cada uno con start_id, end_id, event, role, evidence_ids y relation. Cita IDs de frases de cada tramo que respalden la historia común. Incluye initial_context y grouping_reason específicos. Asegúrate de que la combinación aporte narrativa por variación, progresión o desenlace. Obtén contexto y cierre antes de seleccionar la cantidad de tramos.
- Trata la duración mínima de 40 s como requisito de exportación, no como motivo para rellenar. En una recopilación suma las duraciones retenidas, excluyendo los huecos. El máximo indicado para los cortes individuales no se aplica a la ventana fuente.
- Si propones además un clip individual que comparte el acontecimiento con una recopilación, explica en standalone_reason por qué tiene valor autónomo excepcional y muestra un remate distinto.
"""
