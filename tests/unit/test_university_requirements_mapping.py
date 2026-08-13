"""Область 8: `_map_program_requirement` (app/services/roadmap_builder.py).

Pure mapping, no DB/session needed — Program/University are plain objects
here, never flushed. Verifies the "null means no data, never 'not required'"
discipline against this richer `Program.requirements` key shape (min_gpa/
exams/min_ielts/min_sat/needs_portfolio/needs_essay/needs_recommendations/
needs_interview), not the old pre-RIASEC design doc's guessed names.

scripts/seed_universities.py, which used to seed this richer shape, was
removed 2026-08-13 (scripts/seed_kz_universities.py / university-data/*.py
is the single source of truth now, seeding a sparser {"notes": [...]}
shape instead) — this test still pins the mapping's correct behavior for
this key shape, since _map_program_requirement must keep handling it
correctly if it's ever the input.
"""
from app.models.program import Program
from app.models.university import University
from app.services.roadmap_builder import _map_program_requirement

_UNIVERSITY = University(name="Nazarbayev University", country="Казахстан", city="Астана")


def _program(**overrides) -> Program:
    defaults = dict(
        name="Компьютерные науки (бакалавр)",
        profession_slugs=["it-development"],
        language="Английский",
        requirements={},
        deadlines={},
        grants=[],
    )
    defaults.update(overrides)
    return Program(**defaults)


def test_full_requirements_map_every_field():
    program = _program(
        requirements={
            "min_gpa": 3.5,
            "exams": ["SAT", "IELTS", "ЕНТ"],
            "min_ielts": 6.5,
            "needs_portfolio": False,
            "needs_essay": True,
            "needs_recommendations": True,
            "needs_interview": False,
        },
        deadlines={
            "application_open": "2025-11-01",
            "application_close": "2026-02-28",
            "exam_deadline": "2026-02-01",
            "decision_date": "2026-04-15",
        },
        grants=[{"name": "Президентская стипендия", "amount": "100%", "conditions": "ЕНТ"}],
    )

    req = _map_program_requirement(program, _UNIVERSITY)

    assert req.program_name == "Компьютерные науки (бакалавр)"
    assert req.university_name == "Nazarbayev University"
    assert req.city == "Астана"
    assert req.exams == ["SAT", "IELTS", "ЕНТ"]
    assert req.application_deadline == "2026-02-28"
    assert req.language_level == "IELTS 6.5"
    assert req.grants[0].name == "Президентская стипендия"
    # needs_interview:false must NOT appear in required_documents, but
    # needs_essay/needs_recommendations:true must.
    assert req.required_documents == ["Мотивационное эссе", "Рекомендательные письма"]


def test_needs_portfolio_false_stays_false_not_none():
    # This is the crux of the null-discipline: "not required" (False, a known
    # fact) must never collapse into "no data" (None).
    program = _program(requirements={"needs_portfolio": False})
    req = _map_program_requirement(program, _UNIVERSITY)
    assert req.portfolio_needed is False


def test_portfolio_needed_is_none_when_key_absent():
    program = _program(requirements={})
    req = _map_program_requirement(program, _UNIVERSITY)
    assert req.portfolio_needed is None


def test_required_documents_is_none_when_no_document_keys_present():
    # Sparser seed shape (scripts/seed_kz_universities.py: requirements =
    # {"notes": [...]}) carries none of needs_essay/needs_recommendations/
    # needs_interview at all — that must read as "no data", not "[]" (which
    # would falsely claim "confirmed: nothing needed").
    program = _program(requirements={"notes": ["some admission note"]})
    req = _map_program_requirement(program, _UNIVERSITY)
    assert req.required_documents is None


def test_required_documents_can_be_empty_list_when_keys_present_but_all_false():
    # Here the data actually says "no essay, no recommendations, no interview"
    # — a real, known fact, so [] (not None) is correct.
    program = _program(
        requirements={"needs_essay": False, "needs_recommendations": False, "needs_interview": False}
    )
    req = _map_program_requirement(program, _UNIVERSITY)
    assert req.required_documents == []


def test_language_level_none_when_no_min_ielts():
    program = _program(requirements={"exams": ["ЕНТ"]})
    req = _map_program_requirement(program, _UNIVERSITY)
    assert req.language_level is None


def test_missing_deadlines_and_grants_are_empty_not_error():
    # scripts/seed_kz_universities.py seeds deadlines={} and grants=[] for the
    # 55-university scrape — must map cleanly, not raise.
    program = _program(requirements={"notes": []}, deadlines={}, grants=[])
    req = _map_program_requirement(program, _UNIVERSITY)
    assert req.application_deadline is None
    assert req.grants == []
    assert req.exams == []
