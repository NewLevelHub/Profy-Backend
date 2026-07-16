from types import SimpleNamespace

from app.models.assessment_session import SessionStatus
from app.services.result_service import _message_for, matched_axes_for


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


def test_message_for_confident_status_no_rejection():
    session = SimpleNamespace(status=SessionStatus.converged_single, rejected_leaves=[])
    assert "не единственное" in _message_for(session)


def test_message_for_confident_status_after_rejection():
    session = SimpleNamespace(status=SessionStatus.converged_single, rejected_leaves=["surgeon"])
    assert "предыдущий вариант" in _message_for(session)


def test_message_for_cluster_status_no_rejection():
    session = SimpleNamespace(status=SessionStatus.converged_cluster, rejected_leaves=[])
    assert "не набралось уверенности" in _message_for(session)


def test_message_for_ceiling_status_treated_as_uncertain():
    session = SimpleNamespace(status=SessionStatus.exhausted_ceiling, rejected_leaves=[])
    assert "не набралось уверенности" in _message_for(session)
