"""OpenAPI schema snapshots — student (`MiResultResponse`/
`RiasecResultResponse`) and admin (`AdminAnalysisResultResponse`) contracts,
pinned to `tests/snapshots/*.json`.

Deliberately normalized rather than diffing the raw `app.openapi()` output
byte-for-byte: pydantic auto-generates a `title` for every property from its
Python name, and those titles (plus free-text `description`s) shift with
unrelated docstring edits — noise a contract snapshot shouldn't fail on.
What actually matters for "did the contract change" is: which fields exist,
their type/$ref, and their hard constraints (required, min/maxItems,
min/maxLength, const, enum, default). That's what's captured and compared.

To intentionally update a snapshot after a real, agreed contract change:
regenerate via the `_normalize_schema` helper below and overwrite the
matching file in tests/snapshots/ — never hand-edit the JSON.
"""
import json
from pathlib import Path

from app.main import app

_SNAPSHOT_DIR = Path(__file__).parent.parent / "snapshots"


def _normalize_schema(component: dict) -> dict:
    properties = {}
    for name, spec in sorted(component.get("properties", {}).items()):
        entry: dict = {}
        if "$ref" in spec:
            entry["ref"] = spec["$ref"].rsplit("/", 1)[-1]
        elif "type" in spec:
            entry["type"] = spec["type"]
        elif "anyOf" in spec:
            entry["anyOf"] = sorted(
                (s.get("type") or s.get("$ref", "").rsplit("/", 1)[-1]) for s in spec["anyOf"]
            )
        if "items" in spec:
            item = spec["items"]
            entry["items"] = item.get("$ref", "").rsplit("/", 1)[-1] or item.get("type")
        for key in ("minItems", "maxItems", "minLength", "maxLength", "const", "enum", "default"):
            if key in spec:
                entry[key] = spec[key]
        properties[name] = entry

    return {
        "required": sorted(component.get("required", [])),
        "additionalProperties": component.get("additionalProperties"),
        "properties": properties,
    }


def _load_snapshot(name: str) -> dict:
    with open(_SNAPSHOT_DIR / f"{name}.json", encoding="utf-8") as f:
        return json.load(f)


def _component(name: str) -> dict:
    return app.openapi()["components"]["schemas"][name]


def test_mi_result_response_schema_matches_snapshot():
    assert _normalize_schema(_component("MiResultResponse")) == _load_snapshot("openapi_mi_result_response")


def test_riasec_result_response_schema_matches_snapshot():
    assert _normalize_schema(_component("RiasecResultResponse")) == _load_snapshot(
        "openapi_riasec_result_response"
    )


def test_student_career_schema_matches_snapshot():
    assert _normalize_schema(_component("StudentCareer")) == _load_snapshot("openapi_student_career")


def test_admin_analysis_result_response_schema_matches_snapshot():
    assert _normalize_schema(_component("AdminAnalysisResultResponse")) == _load_snapshot(
        "openapi_admin_analysis_result_response"
    )
