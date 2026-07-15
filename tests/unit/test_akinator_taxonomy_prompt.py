from app.prompts.akinator_taxonomy import AKINATOR_TAXONOMY_SCHEMA, build_messages


def test_schema_shape_matches_ticket_fields():
    node_schema = AKINATOR_TAXONOMY_SCHEMA["properties"]["nodes"]["items"]
    assert set(node_schema["required"]) == {"slug", "name", "parent_slug", "is_leaf"}
    assert node_schema["additionalProperties"] is False


def test_build_messages_includes_existing_slugs_and_focus_area():
    messages = build_messages(["teacher", "engineer"], "медицина", count=5)

    assert [m["role"] for m in messages] == ["system", "user"]
    user_content = messages[1]["content"]
    assert "teacher" in user_content
    assert "engineer" in user_content
    assert "медицина" in user_content
    assert "5" in user_content


def test_build_messages_handles_empty_catalog():
    messages = build_messages([], "", count=3)
    assert "каталог пока пуст" in messages[1]["content"]
