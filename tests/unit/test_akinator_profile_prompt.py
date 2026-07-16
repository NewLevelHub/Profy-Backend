from app.core.axes import AXIS_CODES
from app.prompts.akinator_profile import (
    PROFILE_SCHEMA,
    build_messages,
    build_retry_messages,
    split_known_axes,
)


def test_schema_axis_code_enum_matches_axis_codes():
    axis_schema = PROFILE_SCHEMA["properties"]["axes"]["items"]
    assert set(axis_schema["properties"]["code"]["enum"]) == AXIS_CODES
    assert axis_schema["additionalProperties"] is False


def test_schema_value_enum_excludes_zero():
    axis_schema = PROFILE_SCHEMA["properties"]["axes"]["items"]
    assert set(axis_schema["properties"]["value"]["enum"]) == {-2, -1, 1, 2}


def test_build_messages_includes_name_and_category():
    messages = build_messages("Хирург", "Медицина и здоровье")
    assert [m["role"] for m in messages] == ["system", "user"]
    assert "Хирург" in messages[1]["content"]
    assert "Медицина и здоровье" in messages[1]["content"]


def test_build_messages_handles_missing_category():
    messages = build_messages("Хирург")
    assert "Хирург" in messages[1]["content"]


def test_split_known_axes_accepts_valid_entries():
    data = {"axes": [{"code": "People", "value": 2}, {"code": "Care", "value": -1}]}
    known, unknown = split_known_axes(data)
    assert known == {"People": 2, "Care": -1}
    assert unknown == []


def test_split_known_axes_rejects_unknown_codes():
    data = {"axes": [{"code": "People", "value": 1}, {"code": "B_analyze", "value": 2}]}
    known, unknown = split_known_axes(data)
    assert known == {"People": 1}
    assert unknown == ["B_analyze"]


def test_split_known_axes_rejects_zero_value():
    data = {"axes": [{"code": "People", "value": 0}]}
    known, unknown = split_known_axes(data)
    assert known == {}
    assert unknown == ["People"]


def test_build_retry_messages_lists_unknown_codes_and_valid_options():
    messages = build_messages("Хирург")
    raw_response = {"axes": [{"code": "B_analyze", "value": 2}]}
    retried = build_retry_messages(messages, raw_response, ["B_analyze"])

    assert len(retried) == len(messages) + 2
    correction = retried[-1]["content"]
    assert "B_analyze" in correction
    assert "People" in correction  # a real axis code, offered as a valid option
