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
