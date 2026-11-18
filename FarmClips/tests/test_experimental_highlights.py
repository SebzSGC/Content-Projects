from collections import Counter

import pytest
from pydantic import ValidationError

from clipsserver.experimental.editorial import Segment, calibrate, visible_groups
from clipsserver.experimental.storage import Store


def test_feedback_is_idempotent_and_correction_requires_latest_revision(tmp_path):
    store = Store(tmp_path / "local.db")
    store.migrate()
    original = {"decision": "dudoso", "segment": None}
    seq = store.save_review("run", "clip", "operation-1", None, original)
    assert store.save_review("run", "clip", "operation-1", None, original) == seq
    with pytest.raises(ValueError):
        store.save_review("run", "clip", "operation-1", None, {"decision": "interesante"})
    edited = {"decision": "interesante", "segment": {"start": 10, "end": 40}}
    with pytest.raises(ValueError):
        store.save_review("run", "clip", "operation-2", None, edited)
    store.save_review("run", "clip", "operation-2", seq, edited)
    assert [item["payload"] for item in Store(store.path).history("run", "clip")] == [original, edited]


@pytest.mark.parametrize("start,end", [(5, 1), (0, float("inf")), (float("nan"), 5)])
def test_segment_rejects_invalid_time(start, end):
    with pytest.raises(ValidationError):
        Segment(start=start, end=end)


def test_calibration_uses_multiple_sources_and_ignores_ambiguous_labels():
    positives = [{"sha256": str(i % 3), "decision": "interesante", "category": "llamada"} for i in range(5)]
    negatives = [{"sha256": str(i), "decision": "no_interesante", "category": "llamada"} for i in range(3)]
    uncertain = [{"sha256": "other", "decision": "dudoso", "category": "llamada"}]
    assert calibrate(positives + uncertain) == {}
    assert calibrate(positives + negatives + uncertain) == calibrate(positives + negatives)
    assert 0 < calibrate(positives + negatives)["llamada"] < .06


def test_grouping_keeps_anchor_stable_and_partial_hour_budget():
    v1 = [
        {"id": str(start), "inicio_seg": start, "fin_seg": start + 22, "centro_seg": start + 10,
         "tipo_momento": category}
        for start, category in [(100, "a"), (104, "a"), (110, "b"), (1900, "b"), (3650, "a"), (3700, "b")]
    ]
    groups = visible_groups(v1, list(reversed(v1)), duration=3800, budget=2)
    assert Counter(group["quarter"] // 4 for group in groups) == {0: 2, 1: 1}
    duplicate_group = next(group for group in groups if group["anchor"] == "100")
    assert duplicate_group["members"] == ["104", "100"]
    assert duplicate_group["representative"] == "104"
    assert visible_groups(v1, v1, 3800, 0) == []


def test_generation_prefers_editorial_context_over_intensity_for_overlapping_cuts():
    from clipscore.domain import CuratedClip
    from clipscore.selection.resolver import dedupe_clips

    loud = CuratedClip(id="loud", start_id="u1", end_id="u2", start=0, end=30,
                       overlay_title="Ruido", post_title="Ruido", llm_score=65, signal_score=1, final_score=75.5)
    story = CuratedClip(id="story", start_id="u1", end_id="u2", start=2, end=32,
                        overlay_title="Historia", post_title="Historia", llm_score=90, signal_score=.2, final_score=69)
    assert [clip.id for clip in dedupe_clips([loud, story])] == ["loud"]
    loud.editorial_score = 70.25
    story.editorial_score = 79.5
    assert [clip.id for clip in dedupe_clips([loud, story])] == ["story"]
    assert story.final_score == 69


@pytest.mark.asyncio
async def test_editorial_guidance_reaches_the_existing_curation_call():
    from clipsproviders.llm.base import LlmAdapter, RawLlmCallOutput
    from clipsserver.experimental.generation import EDITORIAL_GUIDANCE

    prompts = []

    async def fake_generate(self, system_prompt, user_prompt, schema):
        prompts.append(system_prompt)
        return RawLlmCallOutput(provider="fixture", model="fixture", raw_text='{"clips":[]}')

    class Fixture(LlmAdapter):
        generate_raw = fake_generate

    fixture = Fixture()
    await fixture.curate_timeline("u0001 [0:11] ¿Quién llamó?")
    await fixture.curate_timeline("u0001 [0:11] ¿Quién llamó?", editorial_guidance=EDITORIAL_GUIDANCE)
    assert "Perfil editorial FarmClips" not in prompts[0]
    assert prompts[1].endswith(EDITORIAL_GUIDANCE)


def test_timeline_pause_markers_reaction_tags_and_dynamic_tail_pad():
    from clipscore.domain import SignalSeries, Utterance
    from clipscore.selection import compute_dynamic_tail_pad, resolve_curated_clips
    from clipscore.timeline import build_compact_timeline

    utts = [
        Utterance(id="u0001", start=2.0, end=8.0, text="Abrimos la puerta con cuidado."),
        Utterance(id="u0002", start=12.2, end=19.0, text="¡Salió de la nada en el pasillo!"),
        Utterance(id="u0003", start=24.0, end=30.0, text="Cambio de escena tranquilo."),
    ]
    reaction = [0.1] * 35
    for s in (15, 16, 19, 20, 21):
        reaction[s] = 0.82
    mic_loud = [0.1] * 35
    signals = SignalSeries(duration=35.0, reaction=reaction, mic_loudness=mic_loud, excitement=reaction)

    compact = build_compact_timeline(utts, signals)
    assert "--- [PAUSA 4s] ---" in compact
    assert "--- [PAUSA 5s] ---" in compact
    assert "u0002 [0:12] ¡Salió de la nada en el pasillo! [ALTA REACCIÓN]" in compact

    # Ongoing laughter at t=19..21 extends tail_pad beyond 0.8s; dead silence at t=30 trims to 0.35s
    assert compute_dynamic_tail_pad(19.0, signals, next_utterance_start=24.0) == 1.65
    assert compute_dynamic_tail_pad(30.0, signals, next_utterance_start=None) == 0.35

    clips = resolve_curated_clips(
        [{"start_id": "u0002", "end_id": "u0002", "overlay_title": "Susto en pasillo", "score": 90}],
        utts,
        signals,
        vod_duration=35.0,
        editorial_profile=True,
    )
    assert len(clips) == 1
    assert clips[0].end == round(19.0 + 1.65, 3)


def test_subsecond_100hz_jump_cut_protection_and_multi_sfx(tmp_path):
    import numpy as np
    from clipscore.directors import compute_jump_cut_ranges
    from clipscore.domain import TranscriptWord
    from clipsstyles import ensure_sfx_wav, load_preset

    for sfx_name in ("boom", "whoosh", "pop"):
        wav_path = ensure_sfx_wav(sfx_name, cache_dir=tmp_path / "sfx")
        assert wav_path.is_file() and wav_path.stat().st_size > 1000

    preset = load_preset("hormozi-gaming")
    words = [
        TranscriptWord(text="Entramos", start=5.0, end=5.5),
        TranscriptWord(text="Salimos", start=7.2, end=7.8),
    ]
    # Gap [5.5 .. 7.2] has no 1Hz reaction signal, but has a sharp 100Hz vocal burst at t=6.3s
    attack_100hz = np.zeros(400, dtype=np.float32)
    attack_100hz[130] = 0.65  # 5.0 + 1.30s = 6.30s inside [cut_a, cut_b]

    unprotected = compute_jump_cut_ranges(5.0, 8.0, words, [], None, preset)
    protected = compute_jump_cut_ranges(
        5.0, 8.0, words, [], None, preset, mic_attack_100hz=attack_100hz, mic_attack_start_sec=5.0
    )
    assert len(unprotected) == 2
    assert protected == [(5.0, 8.0)]


@pytest.mark.asyncio
async def test_deepseek_direct_json_object_and_cache_hit_pricing():
    import httpx
    from clipsproviders.llm.gemini import GEMINI_PRICING_PER_1M
    from clipsproviders.llm.openai_compat import OpenAICompatibleAdapter

    assert GEMINI_PRICING_PER_1M["gemini-3.1-flash-lite"] == (0.25, 1.50)
    captured_bodies = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_bodies.append(request.read().decode("utf-8"))
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"clips":[]}'}}],
                "usage": {
                    "prompt_tokens": 100_000,
                    "prompt_cache_hit_tokens": 80_000,
                    "completion_tokens": 10_000,
                },
            },
        )

    adapter = OpenAICompatibleAdapter(
        api_key="sk-test-deepseek",
        model="deepseek-flash",
        base_url="https://api.deepseek.com/v1",
    )
    await adapter._client.aclose()
    adapter._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    try:
        out = await adapter.generate_raw("Sistema", "Timeline", {"type": "object"})
        assert len(captured_bodies) == 1
        assert '"type":"json_object"' in captured_bodies[0].replace(" ", "")
        assert '"max_tokens":8192' in captured_bodies[0].replace(" ", "")
        # 20k miss @ $0.15/1M ($0.003) + 80k hit @ $0.015/1M ($0.0012) + 10k out @ $0.60/1M ($0.006) = $0.0102
        assert out.cost_usd == 0.0102
    finally:
        await adapter.aclose()


def test_learned_editorial_guidance_and_editor_diff_feedback(tmp_path):
    from clipsserver.experimental.generation import (
        build_learned_editorial_guidance,
        selection_guidance,
        summarize_editor_diff,
    )

    db_file = tmp_path / "learned.db"
    store = Store(db_file)
    store.migrate()
    assert build_learned_editorial_guidance(db_file) == ""

    store.save_review(
        "generated:ses_1",
        "clip_a",
        "op-review-1",
        None,
        {
            "session_id": "ses_1",
            "decision": "interesante",
            "category": "llamada",
            "notes": "Excelente giro y remate de la llamada",
            "editorial_format": "individual",
            "proposal": [10.0, 56.0],
            "source_ranges": [[10.0, 56.0]],
        },
        provenance="revision_clip_generado",
    )
    clip_row = {
        "session_id": "ses_1",
        "start_sec": 10.0,
        "end_sec": 50.0,
        "overlay_title": "Momento en directo",
        "curated_json": '{"start": 10.0, "end": 50.0, "overlay_title": "Momento en directo", "editorial_format": "individual"}',
    }
    diff = summarize_editor_diff(
        clip_row,
        {
            "source": {"ranges": [[8.0, 54.0]]},
            "overlays": [{"kind": "title", "text": "LA LLAMADA MÁS TENSA"}],
        },
    )
    assert diff is not None and diff["duration_delta_sec"] == 6.0 and diff["title_changed"] is True
    store.record_editor_diff("ses_1", "clip_a", "op-edit-1", diff)

    learned = build_learned_editorial_guidance(db_file)
    assert "llamada" in learned
    assert "Golden Clips" in learned
    assert "LA LLAMADA MÁS TENSA" in learned
    full_guidance = selection_guidance(600, db_path=db_file)
    assert learned in full_guidance
