"""Curriculum-slice logic — pure, no DB/LLM. Runs against a stubbed CURRICULUM_BANK."""
import pytest

from app.services import development_plan_context as ctx


@pytest.fixture(autouse=True)
def _stub_curriculum(monkeypatch):
    stub = {
        ("математика", 8): [
            {"order": 1, "quarter": 1, "topic": "Квадратные корни"},
            {"order": 2, "quarter": 2, "topic": "Квадратные уравнения"},
            {"order": 3, "quarter": 3, "topic": "Квадратичная функция"},
        ],
        ("математика", 9): [
            {"order": 1, "quarter": 1, "topic": "Векторы на плоскости"},
            {"order": 2, "quarter": 2, "topic": "Прогрессии"},
        ],
    }
    monkeypatch.setattr(ctx, "CURRICULUM_BANK", stub)


def test_slice_returns_anchor_examples_from_grades_8_and_9():
    s = ctx.curriculum_slice("математика", 11)
    assert s == {
        "anchor_examples": [
            "Квадратные корни (за 8 класс)",
            "Квадратные уравнения (за 8 класс)",
            "Векторы на плоскости (за 9 класс)",
        ]
    }


def test_slice_missing_subject_returns_none():
    assert ctx.curriculum_slice("химия", 11) is None


def test_slice_grade_argument_does_not_change_anchors():
    # anchors are always grade 8-9 foundation, regardless of the student's grade
    assert ctx.curriculum_slice("математика", 9) == ctx.curriculum_slice("математика", 11)


def test_normalize_subject_matches_free_text_exam_names():
    assert ctx._normalize_subject("Математика") == "математика"
    assert ctx._normalize_subject("  ФИЗИКА  ") == "физика"
    assert ctx._normalize_subject("Творческий экзамен") is None


def test_subjects_needed_local_adds_history_only():
    out = ctx._subjects_needed(["Математика", "Информатика"], is_foreign=False)
    assert out[:2] == ["математика", "информатика"]
    assert "история Казахстана" in out
    # literacy sections are NOT subjects
    assert "математическая грамотность" not in out
    assert "грамотность чтения" not in out


def test_subjects_needed_foreign_injects_nothing():
    out = ctx._subjects_needed(["Творческий экзамен"], is_foreign=True)
    assert out == []  # no normalizable exam, no mandatory injection for foreign
