"""Example-response snapshots for the student v2 contract — junior (MI),
middle and senior (both RIASEC, but pinned separately since the ticket asks
for a snapshot per age group, not per schema class). Reuses the same schema
fixtures test_result_v2_schema.py already builds (not a second, drifting
copy of "what a valid response looks like") — `assessment_id`/`created_at`
are overridden to fixed values here so the snapshot is deterministic.

This complements test_openapi_schema_snapshot.py (which pins the abstract
JSON Schema): this file pins a concrete example payload, catching drift a
schema-shape diff wouldn't — e.g. a field that's still the right type but
now renders with unexpected formatting.
"""
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path

from tests.unit.test_result_v2_schema import _junior_fixture, _middle_fixture, _senior_fixture

_SNAPSHOT_DIR = Path(__file__).parent.parent / "snapshots"
_FIXED_ID = uuid.UUID("00000000-0000-0000-0000-000000000001")
_FIXED_CREATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)


def _load_snapshot(name: str) -> dict:
    with open(_SNAPSHOT_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def test_junior_example_response_matches_snapshot():
    response = _junior_fixture(assessment_id=_FIXED_ID, created_at=_FIXED_CREATED_AT)
    assert response.model_dump(mode="json") == _load_snapshot("result_v2_example_junior")


def test_middle_example_response_matches_snapshot():
    response = _middle_fixture(assessment_id=_FIXED_ID, created_at=_FIXED_CREATED_AT)
    assert response.model_dump(mode="json") == _load_snapshot("result_v2_example_middle")


def test_senior_flat_profile_example_response_matches_snapshot():
    response = _senior_fixture(assessment_id=_FIXED_ID, created_at=_FIXED_CREATED_AT)
    assert response.model_dump(mode="json") == _load_snapshot("result_v2_example_senior")
