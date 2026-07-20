from types import SimpleNamespace

from app.models.assessment_session import SessionStatus
from app.services.result_service import _child_strengths_and_growth, _message_for, matched_axes_for


def test_matched_axes_for_ranks_by_absolute_value_strongest_first():
    profile = {"People": 1, "Care": 2, "Focus": -2, "Struct": 1}
    highlights = matched_axes_for(profile)

    assert [h.code for h in highlights] == ["Care", "Focus", "People", "Struct"]
    assert highlights[0].direction_value == 2
    assert highlights[1].direction_value == -2


def test_matched_axes_for_skips_zero_axes():
    highlights = matched_axes_for({"People": 0, "Care": 1})
    assert [h.code for h in highlights] == ["Care"]


def test_matched_axes_for_caps_at_top_n():
    profile = {"People": 2, "Living": 2, "Phys": 2, "Data": 2, "Ideas": 2, "Inv": 2, "Obj": 2}
    highlights = matched_axes_for(profile)
    assert len(highlights) == 6


def test_matched_axes_for_looks_up_known_axis_labels():
    highlights = matched_axes_for({"Care": 2})
    assert highlights[0].label_ru.strip()
    assert highlights[0].label_ru != "Care"


def test_matched_axes_for_breaks_ties_deterministically():
    highlights = matched_axes_for({"People": 2, "Care": 2})
    assert [h.code for h in highlights] == ["Care", "People"]  # alphabetical tie-break


def test_child_strengths_and_growth_splits_by_sign_strongest_first():
    totals = {"People": 12.0, "Data": 4.0, "Motor": -1.0, "Struct": -6.0, "Ideas": 0.0}
    strengths, growth = _child_strengths_and_growth(totals)

    assert [s.code for s in strengths] == ["People", "Data"]
    assert [g.code for g in growth] == ["Struct", "Motor"]


def test_child_strengths_and_growth_caps_at_n():
    totals = {f"axis{i}": float(i + 1) for i in range(5)}
    strengths, _ = _child_strengths_and_growth(totals)
    assert len(strengths) == 3


def test_child_strengths_and_growth_looks_up_known_axis_labels():
    strengths, _ = _child_strengths_and_growth({"Care": 3.0})
    assert strengths[0].label_ru.strip()
    assert strengths[0].label_ru != "Care"


def test_child_strengths_and_growth_empty_totals_is_empty():
    strengths, growth = _child_strengths_and_growth({})
    assert strengths == []
    assert growth == []


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
