from types import SimpleNamespace

from app.models.assessment_session import SessionStatus
from app.services.result_service import _axis_comparison_for, _message_for


def test_axis_comparison_splits_by_threshold_strongest_first():
    profile = {"People": 2, "Data": 1, "Motor": 1, "Struct": 1}
    child_scores = {"People": 0.8, "Data": 0.2, "Motor": -0.1, "Struct": -0.6}

    matches, growth, is_direction_specific = _axis_comparison_for(profile, child_scores)

    assert [m.code for m in matches] == ["People", "Data"]
    assert [g.code for g in growth] == ["Struct", "Motor"]
    assert is_direction_specific is True


def test_axis_comparison_ignores_axes_the_direction_does_not_need():
    profile = {"People": -1, "Care": 0, "Data": 1}
    child_scores = {"People": 0.9, "Care": 0.9, "Data": 0.9}

    matches, growth, is_direction_specific = _axis_comparison_for(profile, child_scores)

    assert [m.code for m in matches] == ["Data"]
    assert growth == []
    assert is_direction_specific is True


def test_axis_comparison_ignores_axes_with_no_child_signal():
    profile = {"People": 1, "Data": 1}
    child_scores = {"People": 0.5}  # Data never touched by an answered question

    matches, growth, is_direction_specific = _axis_comparison_for(profile, child_scores)

    assert [m.code for m in matches] == ["People"]
    assert growth == []
    assert is_direction_specific is True


def test_axis_comparison_caps_at_n_per_side():
    profile = {f"axis{i}": 1 for i in range(6)}
    child_scores = {f"axis{i}": float(i + 1) for i in range(6)}

    matches, _, _ = _axis_comparison_for(profile, child_scores)
    assert len(matches) == 4


def test_axis_comparison_looks_up_known_axis_labels():
    matches, _, _ = _axis_comparison_for({"Care": 1}, {"Care": 0.5})
    assert matches[0].label_ru.strip()
    assert matches[0].label_ru != "Care"


def test_axis_comparison_growth_items_carry_a_static_explanation():
    _, growth, _ = _axis_comparison_for({"Care": 1}, {"Care": -0.5})
    assert growth[0].explanation is not None
    assert growth[0].explanation.meaning.strip()
    assert growth[0].explanation.suggestion.strip()


def test_axis_comparison_match_items_carry_a_strength_phrase_not_explanation():
    matches, _, _ = _axis_comparison_for({"Care": 1}, {"Care": 0.5})
    assert matches[0].explanation is None
    assert matches[0].strength_phrase
    assert matches[0].strength_phrase != "Care"


def test_axis_comparison_direction_specific_items_carry_the_profile_value():
    matches, _, _ = _axis_comparison_for({"Care": 2}, {"Care": 0.5})
    assert matches[0].profile_value == 2


def test_axis_comparison_empty_inputs_is_empty_and_not_direction_specific():
    matches, growth, is_direction_specific = _axis_comparison_for({}, {})
    assert matches == []
    assert growth == []
    assert is_direction_specific is False


def test_axis_comparison_falls_back_to_whole_session_when_no_direction_overlap():
    """The session never touched any axis this direction needs (e.g. its
    questions happened to land elsewhere) — rather than showing nothing,
    fall back to the child's real signal across the whole session, and say
    so via is_direction_specific=False."""
    profile = {"Care": 1}  # direction needs Care, but the child never answered on it
    child_scores = {"Data": 0.7, "Struct": -0.4}  # real signal, just on other axes

    matches, growth, is_direction_specific = _axis_comparison_for(profile, child_scores)

    assert is_direction_specific is False
    assert [m.code for m in matches] == ["Data"]
    assert [g.code for g in growth] == ["Struct"]


def test_axis_comparison_fallback_items_carry_no_profile_value():
    matches, _, _ = _axis_comparison_for({"Care": 1}, {"Data": 0.7})
    assert matches[0].profile_value is None


def test_message_for_is_always_confident_regardless_of_session_status():
    """The Results page only ever shows a direction the user explicitly
    confirmed via "liked" feedback — so the message must read as confident
    even if the engine itself only ever reached a cluster or the ceiling.
    Regression test: previously this leaked the engine's pre-choice
    uncertainty ("не набралось уверенности...") onto an already-confirmed
    result, which read as a contradiction to the user."""
    for session_status in (
        SessionStatus.converged_single, SessionStatus.converged_cluster, SessionStatus.exhausted_ceiling,
    ):
        session = SimpleNamespace(status=session_status, rejected_leaves=[])
        assert "не единственное" in _message_for(session)
        assert "не набралось уверенности" not in _message_for(session)


def test_message_for_after_rejection_regardless_of_session_status():
    for session_status in (
        SessionStatus.converged_single, SessionStatus.converged_cluster, SessionStatus.exhausted_ceiling,
    ):
        session = SimpleNamespace(status=session_status, rejected_leaves=["general-medicine"])
        assert "предыдущий вариант" in _message_for(session)
