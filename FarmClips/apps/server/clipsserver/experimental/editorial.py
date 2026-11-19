"""Presentation grouping and explicit, conservative calibration."""
from collections import Counter, defaultdict
from math import ceil

from pydantic import BaseModel, Field, model_validator


class Segment(BaseModel):
    start: float = Field(ge=0, allow_inf_nan=False)
    end: float = Field(gt=0, allow_inf_nan=False)

    @model_validator(mode="after")
    def ordered(self):
        if self.end <= self.start:
            raise ValueError("El final debe ser posterior al inicio")
        return self


class Montage(BaseModel):
    """Ordered segments in a single VOD; editing/export remain separate."""
    vod_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    segments: list[Segment] = Field(min_length=2)


def iou(left, right):
    a, b = left["inicio_seg"], left["fin_seg"]
    c, d = right["inicio_seg"], right["fin_seg"]
    return max(0, min(b, d) - max(a, c)) / (max(b, d) - min(a, c))


def visible_groups(v1, ranked, duration, budget):
    positions = {row["id"]: rank for rank, row in enumerate(ranked)}
    groups = []
    for row in v1:
        matches = [(iou(row, anchor), index) for index, (anchor, _) in enumerate(groups)]
        overlap, index = max(matches, key=lambda pair: (pair[0], -pair[1]), default=(0, 0))
        if overlap >= .5:
            groups[index][1].append(row["id"])
        else:
            groups.append((row, [row["id"]]))
    buckets = defaultdict(list)
    for anchor, members in groups:
        members.sort(key=positions.__getitem__)
        buckets[anchor["centro_seg"] // 3600].append({
            "anchor": anchor["id"], "members": members, "category": anchor["tipo_momento"],
            "quarter": anchor["centro_seg"] // 900, "representative": members[0],
        })
    visible = []
    if budget:
        for hour, choices in sorted(buckets.items()):
            limit = ceil(budget * min(3600, duration - hour * 3600) / 3600)
            used_categories, quarters = Counter(), set()
            for _ in range(min(limit, len(choices))):
                selected = min(choices, key=lambda group: (
                    used_categories[group["category"]], group["quarter"] in quarters,
                    positions[group["representative"]],
                ))
                choices.remove(selected)
                used_categories[selected["category"]] += 1
                quarters.add(selected["quarter"])
                visible.append(selected)
    return sorted(visible, key=lambda group: positions[group["representative"]])


def calibrate(labels):
    """Small additive adjustment, using explicit semantic labels only."""
    by_category = defaultdict(list)
    for label in labels:
        if label.get("category") and label["decision"] in ("interesante", "no_interesante"):
            by_category[label["category"]].append(label)
    weights = {}
    for category, examples in by_category.items():
        outcomes = Counter(e["decision"] for e in examples)
        if min(outcomes["interesante"], outcomes["no_interesante"]) < 3:
            continue
        if len({e["sha256"] for e in examples}) < 3:
            continue
        weights[category] = round(.06 * (outcomes["interesante"] - outcomes["no_interesante"]) /
                                  (len(examples) + 10), 6)
    return weights
