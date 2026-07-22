from types import SimpleNamespace

from app.services.subject_readiness_service import REQUIRED_SUBJECT_COUNT, _top_subjects


def _direction(subjects_required: dict) -> SimpleNamespace:
    return SimpleNamespace(subjects_required=subjects_required)


def test_top_subjects_sorted_by_weight_descending():
    direction = _direction({"Физика": 1, "Математика": 2, "Информатика": 2})
    assert _top_subjects(direction) == ["Информатика", "Математика", "Физика"]


def test_top_subjects_ties_broken_alphabetically():
    direction = _direction({"Химия": 2, "Биология": 2})
    assert _top_subjects(direction) == ["Биология", "Химия"]


def test_top_subjects_caps_at_required_count():
    direction = _direction({
        "Математика": 2, "Информатика": 2, "Физика": 1, "Химия": 1, "Биология": 1,
    })
    top = _top_subjects(direction)
    assert len(top) == REQUIRED_SUBJECT_COUNT
    # Weight-1 ties broken alphabetically: Биология < Физика < Химия.
    assert top == ["Информатика", "Математика", "Биология"]


def test_top_subjects_returns_fewer_when_fewer_available():
    direction = _direction({"Математика": 2, "Информатика": 2})
    assert _top_subjects(direction) == ["Информатика", "Математика"]


def test_top_subjects_empty_when_none_required():
    assert _top_subjects(_direction({})) == []
