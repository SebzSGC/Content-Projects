"""Editorial rules distilled from the published examples, comparative reviews, and creator feedback loop."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional

from .storage import Store

EDITORIAL_GUIDANCE = """Perfil editorial FarmClips 1.0. Estas pautas prevalecen sobre las directrices generales de selección y corte:
- Prioriza un giro comprensible y su consecuencia. Busca sustos con preparación y reacción, fallos o retos con desenlace, humor con remate, y llamadas o conversaciones que desarrollan una situación.
- Usa picos de sonido, movimiento, marcas `--- [PAUSA Xs] ---` y etiquetas `[REACCIÓN]` / `[ALTA REACCIÓN]` como pistas. Requiere contexto para dar peso a menús, pantallas de resultados, desplazamientos y tareas repetitivas.
- Comienza en la primera frase necesaria para entender el momento. Termina cuando se entiende la reacción, el resultado o el remate. Una llamada puede necesitar más desarrollo tras el primer pico.
- Devuelve los IDs de frase existentes y respeta el máximo del editor indicado en los parámetros. Cada propuesta es un tramo continuo. Evita atribuir acciones o reacciones que la evidencia disponible no permite identificar.
- Basa score principalmente en la claridad del contexto, lo que sucede y su desenlace. Devuelve menos propuestas si hay pocas que lo justifiquen."""


def summarize_editor_diff(clip_row: Dict[str, Any], new_plan_dict: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Compute a compact diff between the original AI proposal in curated_json and the user's edited EditPlan."""
    try:
        curated = json.loads(clip_row.get("curated_json") or "{}")
    except Exception:
        curated = {}
    if not curated:
        return None

    orig_ranges = (
        [[float(s["start"]), float(s["end"])] for s in curated.get("editorial_segments", [])]
        or [[float(curated.get("start", clip_row.get("start_sec", 0.0))), float(curated.get("end", clip_row.get("end_sec", 0.0)))]]
    )
    new_ranges = [
        [float(r[0]), float(r[1])]
        for r in (new_plan_dict.get("source", {}).get("ranges") or orig_ranges)
    ]
    orig_dur = round(sum(max(0.0, b - a) for a, b in orig_ranges), 2)
    new_dur = round(sum(max(0.0, b - a) for a, b in new_ranges), 2)
    dur_delta = round(new_dur - orig_dur, 2)

    orig_title = str(curated.get("overlay_title") or clip_row.get("overlay_title") or "").strip()
    overlays = new_plan_dict.get("overlays") or []
    new_title = str(overlays[0].get("text") if overlays else orig_title).strip()
    title_changed = bool(new_title and new_title != orig_title)
    ranges_changed = new_ranges != orig_ranges

    if not title_changed and not ranges_changed:
        return None

    return {
        "session_id": clip_row.get("session_id", ""),
        "editorial_format": curated.get("editorial_format", "individual"),
        "orig_duration_sec": orig_dur,
        "new_duration_sec": new_dur,
        "duration_delta_sec": dur_delta,
        "orig_title": orig_title,
        "new_title": new_title,
        "title_changed": title_changed,
        "ranges_changed": ranges_changed,
        "new_ranges_count": len(new_ranges),
    }


def build_learned_editorial_guidance(db_path: Optional[Path | str] = None) -> str:
    """Synthesize conservative editorial preferences and up to 3 Golden Clips from saved human reviews & editor diffs."""
    if not db_path:
        return ""
    path_obj = Path(db_path)
    if not path_obj.is_file():
        return ""
    try:
        revisions = Store(path_obj).learned_revisions()
    except Exception:
        return ""
    if not revisions:
        return ""

    latest_reviews: Dict[tuple[str, str], Dict[str, Any]] = {}
    latest_edits: Dict[str, Dict[str, Any]] = {}
    for row in revisions:
        prov = row.get("provenance")
        cand = str(row.get("candidate") or "")
        payload = row.get("payload") or {}
        if not isinstance(payload, dict):
            continue
        if prov in ("revision_clip_generado", "revision_editorial_explicita"):
            src = str(payload.get("session_id") or payload.get("sha256") or row.get("run_id") or "local")
            latest_reviews[(src, cand)] = {**payload, "candidate": cand}
        elif prov == "edicion_estudio":
            latest_edits[cand] = {**payload, "candidate": cand}

    pos_cats: Counter[str] = Counter()
    neg_cats: Counter[str] = Counter()
    golden_examples: List[str] = []

    for item in latest_reviews.values():
        decision = item.get("decision")
        cat = str(item.get("category") or "").strip()
        if decision == "interesante":
            if cat:
                pos_cats[cat] += 1
            fmt = item.get("editorial_format", "individual")
            ranges = item.get("source_ranges") or ([item["proposal"]] if item.get("proposal") else [])
            dur = round(sum(max(0.0, float(b) - float(a)) for a, b in ranges if len(ranges) > 0), 1) if ranges else 0.0
            notes = str(item.get("notes") or "").strip()
            if len(golden_examples) < 3 and (notes or cat or dur > 0):
                desc_parts = [f"formato={fmt}"]
                if dur > 0:
                    desc_parts.append(f"duración={dur:g}s")
                if cat:
                    desc_parts.append(f"categoría={cat}")
                if notes:
                    desc_parts.append(f"motivo='{notes[:90]}'")
                golden_examples.append("- Ejemplo aprobado (" + ", ".join(desc_parts) + ")")
        elif decision == "no_interesante" and cat:
            neg_cats[cat] += 1

    lines: List[str] = []
    favored = [c for c, cnt in pos_cats.most_common(3) if cnt > neg_cats[c]]
    avoided = [c for c, cnt in neg_cats.most_common(3) if cnt > pos_cats[c]]
    if favored:
        lines.append("- Categorías valoradas positivamente por el creador: " + ", ".join(favored) + ".")
    if avoided:
        lines.append("- Categorías rechazadas con frecuencia si carecen de giro claro: " + ", ".join(avoided) + ".")
    if golden_examples:
        lines.append("- Referencias de clips aprobados (Golden Clips):")
        lines.extend(golden_examples)

    if latest_edits:
        deltas = [float(e.get("duration_delta_sec") or 0.0) for e in latest_edits.values() if e.get("ranges_changed")]
        edited_titles = [
            str(e.get("new_title") or "").strip()
            for e in latest_edits.values()
            if e.get("title_changed") and str(e.get("new_title") or "").strip()
        ]
        if deltas:
            avg_delta = sum(deltas) / len(deltas)
            if avg_delta >= 3.0:
                lines.append(f"- En el editor, el creador suele ampliar los cortes (+{avg_delta:.1f}s promedio): incluye contexto previo y desenlace completo.")
            elif avg_delta <= -3.0:
                lines.append(f"- En el editor, el creador suele recortar relleno ({avg_delta:.1f}s promedio): ajusta el inicio y cierre directo a la acción.")
        if edited_titles:
            sample_titles = ", ".join(f'"{t[:40]}"' for t in edited_titles[-2:])
            lines.append(f"- Estilo de títulos preferido por el creador en estudio: {sample_titles}.")

    if not lines:
        return ""
    return "Memoria editorial aprendida del creador:\n" + "\n".join(lines)


def selection_guidance(window_seconds: float, db_path: Optional[Path | str] = None) -> str:
    base = EDITORIAL_GUIDANCE + f"""

Formato por propuesta. Evalúa secuencias de hasta {window_seconds:g} segundos del VOD.
- individual: un acontecimiento autónomo. Escoge IDs que abarquen el contexto útil, reacción y desenlace. Devuelve los candidatos breves que merezcan revisión aunque no alcancen 40 s.
- recopilacion: usa segments con dos o más tramos separados en orden del VOD, cada uno con start_id, end_id, event, role, evidence_ids y relation. Cita IDs de frases de cada tramo que respalden la historia común. Incluye initial_context y grouping_reason específicos. Asegúrate de que la combinación aporte narrativa por variación, progresión o desenlace. Obtén contexto y cierre antes de seleccionar la cantidad de tramos.
- Trata la duración mínima de 40 s como requisito de exportación, no como motivo para rellenar. En una recopilación suma las duraciones retenidas, excluyendo los huecos. El máximo indicado para los cortes individuales no se aplica a la ventana fuente.
- Si propones además un clip individual que comparte el acontecimiento con una recopilación, explica en standalone_reason por qué tiene valor autónomo excepcional y muestra un remate distinto.
"""
    learned = build_learned_editorial_guidance(db_path)
    if learned:
        return base + "\n" + learned + "\n"
    return base
