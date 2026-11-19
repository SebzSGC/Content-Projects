"""Editorial decisions driven by recorded IDs, independent of a live provider."""
import pytest

from clipscore.directors import build_editplan
from clipscore.domain import Utterance
from clipscore.selection import resolve_curated_clips
from clipseditplan import SourcePlan
from clipsproviders.llm.base import CurationEnvelope
from clipsstyles import load_preset


def line(number, start, end, text):
    return Utterance(id=f"u{number:04}", start=start, end=end, text=text)


def proposal(start, end, **fields):
    return {"start_id": start, "end_id": end, "overlay_title": "Momento", "score": 88, **fields}


def moment(number, event, role):
    uid = f"u{number:04}"
    return {"start_id": uid, "end_id": uid, "event": event, "role": role,
            "relation": "La reacción continúa la búsqueda de la salida", "evidence_ids": [uid]}


def resolve(rows, utterances, window=600):
    envelope = CurationEnvelope.model_validate({"clips": rows})
    return resolve_curated_clips([r.model_dump() for r in envelope.clips], utterances, None, 1000,
                                 min_sec=40, max_sec=180, editorial_profile=True, related_window_sec=window)


def compilation():
    return proposal("u0001", "u0004", editorial_format="recopilacion",
                    initial_context="Busca una salida", grouping_reason="La huida progresa tras cada aparición",
                    segments=[moment(1, "Buscar la salida", "contexto"), moment(2, "Primer susto", "acontecimiento"),
                              moment(4, "Huida tras el segundo susto", "remate")])


def test_individual_preserves_complete_call_and_short_candidate_is_not_padded():
    utterances = [
        line(1, 10, 22, "Marca el número y presenta la llamada."),
        line(2, 24, 36, "La interlocutora explica el problema."),
        line(3, 42, 65, "La solución cierra el intercambio."),
        line(4, 77, 89, "Encuentra un objeto."),
        line(5, 90, 140, "Espera a que cargue el menú."),
    ]
    call, short = resolve([proposal("u0001", "u0003"), proposal("u0004", "u0004")], utterances)
    assert call.editorial_format == short.editorial_format == "individual"
    assert call.end == 65.8 and call.start == 9.8
    assert short.end == 89.8 and short.start == 76.8


def test_compilation_uses_selected_ranges_and_excludes_equivalent_individual():
    utterances = [
        line(1, 10, 24, "Necesito encontrar la salida."),
        line(2, 70, 89, "Otra vez apareció en el pasillo."),
        line(3, 110, 165, "Pausa y menú."),
        line(4, 185, 211, "Ya encontré la salida. ¡Está detrás de mí!"),
        line(5, 320, 380, "Historia diferente con su propio remate."),
    ]
    rows = [proposal("u0004", "u0004"), compilation(), proposal("u0005", "u0005", score=70)]
    clips = resolve(rows, utterances)
    assert [clip.editorial_format for clip in clips] == ["recopilacion", "individual"]
    recap = clips[0]
    assert [part.role for part in recap.editorial_segments] == ["contexto", "acontecimiento", "remate"]
    plan = build_editplan("ses_vod", recap, utterances, None, None, load_preset())
    assert plan.source.ranges == [(10, 24), (70, 89), (185, 211)]
    assert plan.total_duration() == 59
    assert plan.master_to_clip_time(110) is None
    assert plan.master_to_clip_time(190) == 38


@pytest.mark.parametrize("problem", ["ids_inventados", "sin_relacion", "muy_lejanos", "sin_cierre", "solape"])
def test_incoherent_or_unverifiable_compilation_is_discarded(problem):
    lines = [line(1, 10, 24, "Contexto"), line(2, 70, 89, "Susto"),
             line(3, 90, 110, "Otro asunto"), line(4, 185, 211, "Remate")]
    item = compilation()
    if problem == "ids_inventados":
        item["segments"][1]["evidence_ids"] = ["u0003"]
    if problem == "sin_relacion":
        item["grouping_reason"] = ""
    if problem == "sin_cierre":
        item["segments"][-1]["role"] = "desarrollo"
    if problem == "solape":
        item["segments"][0]["end_id"] = "u0002"
    assert resolve([item], lines, window=100 if problem == "muy_lejanos" else 600) == []


def test_source_ranges_reject_invalid_times():
    with pytest.raises(ValueError):
        SourcePlan(session="s", ranges=[(-1, 5)])
    with pytest.raises(ValueError):
        SourcePlan(session="s", ranges=[(0, float("inf"))])
