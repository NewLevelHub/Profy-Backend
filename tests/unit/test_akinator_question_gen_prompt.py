from app.prompts.akinator_question_gen import QUESTION_CONTENT_SCHEMA, build_messages


def test_schema_shape_has_no_administrative_fields():
    assert set(QUESTION_CONTENT_SCHEMA["required"]) == {"text", "text_junior", "options"}
    assert QUESTION_CONTENT_SCHEMA["additionalProperties"] is False

    option_schema = QUESTION_CONTENT_SCHEMA["properties"]["options"]["items"]
    assert set(option_schema["required"]) == {"text", "axis_weights"}

    weight_schema = option_schema["properties"]["axis_weights"]["items"]
    assert weight_schema["properties"]["value"]["enum"] == [-2, -1, 1, 2]
    assert "People" in weight_schema["properties"]["code"]["enum"]


def test_build_messages_includes_axis_depth_and_kind():
    messages = build_messages("People", depth=0, kind="direct")
    assert [m["role"] for m in messages] == ["system", "user"]
    content = messages[1]["content"]
    assert "People" in content
    assert "Глубина: 0" in content
    assert "direct" in content


def test_build_messages_situational_guide_differs_from_direct():
    direct_msg = build_messages("Focus", depth=2, kind="direct")[1]["content"]
    situational_msg = build_messages("Focus", depth=2, kind="situational")[1]["content"]
    assert direct_msg != situational_msg
    assert "ПРЯМОЙ" in direct_msg
    assert "СИТУАТИВНЫЙ" in situational_msg
