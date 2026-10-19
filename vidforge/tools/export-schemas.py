"""Exports Pydantic v2 JSON Schemas into packages/contracts/."""

from __future__ import annotations

import json
from pathlib import Path

from vidforge.domain.models import ScriptModel, TimelineModel, TranscriptModel
from vidforge.infra.paths import CONTRACTS_DIR


def main() -> int:
    CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
    models = {
        "script.pydantic.v1.json": ScriptModel,
        "transcript.pydantic.v1.json": TranscriptModel,
        "timeline.pydantic.v1.json": TimelineModel,
    }
    for fname, cls in models.items():
        schema = cls.model_json_schema()
        (CONTRACTS_DIR / fname).write_text(json.dumps(schema, indent=2), encoding="utf-8")
    print(f"Exported {len(models)} Pydantic schemas to {CONTRACTS_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
