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
