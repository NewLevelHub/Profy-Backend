"""Область 8: goal-specific prompt branching in app/prompts/direction_roadmap.py.

Pure unit tests — no DB, no LLM. `build_messages` must vary its *instructional
text* per `context.goal` (ТЗ §23.3: сценарии A/B/C) while
`DIRECTION_ROADMAP_SCHEMA` — the JSON contract the model must satisfy — stays
byte-identical regardless of goal.
"""
from app.models.direction import Direction
from app.prompts import direction_roadmap as direction_prompt
from app.schemas.roadmap import UniversityRequirement
from app.schemas.student_context import StudentContext

_DIRECTION = Direction(
    name="IT и разработка",
    slug="it-development",
    holland_code="RIA",
    description="desc",
    professions=["Backend-разработчик"],
    skills_needed=["Python"],
    subjects_to_develop=["Информатика"],
    first_steps=[],
)


def _context(goal: str) -> StudentContext:
    return StudentContext(
        name="Аян", age=16, age_group="senior", grade=10,
        city="Алматы", country="Казахстан", language="ru",
        goal=goal,
    )


def _system_content(goal: str, university_requirements=None) -> str:
    messages = direction_prompt.build_messages(_context(goal), _DIRECTION, university_requirements)
    return messages[0]["content"]


def test_goal_focus_text_differs_across_goals():
    explore = _system_content("explore")
    profession = _system_content("profession")
    university = _system_content("university")

    assert explore != profession
    assert explore != university
    assert profession != university


def test_unsure_shares_explores_goal_focus_exactly():
    # AssessmentGoal comment: unsure ("Пока не знаю") behaves like explore
    # everywhere else in this pipeline — the goal-focus text must match too.
    assert _system_content("unsure") == _system_content("explore")


def test_unknown_goal_falls_back_to_bare_system_prompt():
    # Defensive: an unexpected/future goal value must not KeyError, it should
    # just get the shared rules with no extra goal-specific paragraph.
    assert _system_content("some_future_goal") == direction_prompt._SYSTEM_PROMPT


def test_explore_focus_emphasises_trial_activities():
    assert "проб" in _system_content("explore").lower()


def test_university_focus_emphasises_admission_prep():
    assert "поступ" in _system_content("university").lower()


def test_schema_is_identical_regardless_of_goal():
    # DIRECTION_ROADMAP_SCHEMA is a module-level constant build_messages never
    # touches — this documents that invariant explicitly rather than relying
    # on "it's not referenced in the function body".
    assert "university_requirements" not in direction_prompt.DIRECTION_ROADMAP_SCHEMA["properties"]
    assert set(direction_prompt.DIRECTION_ROADMAP_SCHEMA["required"]) == {
        "target", "growth_focus", "stages", "skills_to_build",
        "subjects_to_focus", "university_track",
    }


def test_stage_schema_requires_subject_focus():
    stage_schema = direction_prompt._STAGE_SCHEMA
    assert "subject_focus" in stage_schema["required"]
    subject_item_schema = stage_schema["properties"]["subject_focus"]["items"]
    assert set(subject_item_schema["required"]) == {"subject", "topics", "why"}


def test_system_prompt_ties_subject_focus_to_grade_and_bases_month3_in_gaps():
    system = direction_prompt._SYSTEM_PROMPT
    assert "subject_focus" in system
    assert "months_3 — ВСЕГДА база" in system


def test_university_requirements_block_omitted_when_empty():
    _, user_message = direction_prompt.build_messages(_context("university"), _DIRECTION, [])
    assert "ДАННЫЕ ПО ВУЗАМ" not in user_message["content"]


def test_university_requirements_block_present_when_populated():
    reqs = [
        UniversityRequirement(
            program_name="Компьютерные науки",
            university_name="Nazarbayev University",
            city="Астана",
            exams=["SAT", "IELTS", "ЕНТ"],
            application_deadline="2026-02-28",
            language_level="IELTS 6.5",
            portfolio_needed=False,
            required_documents=["Мотивационное эссе"],
        )
    ]
    _, user_message = direction_prompt.build_messages(_context("university"), _DIRECTION, reqs)
    content = user_message["content"]
    assert "ДАННЫЕ ПО ВУЗАМ" in content
    assert "Nazarbayev University" in content


def test_growth_focus_evidence_instruction_no_longer_asks_for_a_percentage():
    # Область 9 §9.4: the old instruction told the model to cite a RIASEC type
    # "с его баллом из profile" — a raw percentage into GrowthFocus.evidence,
    # which the schema docstring says is shown to the student (violates the
    # no-raw-numbers-to-the-child rule the same way big_five/motivation being
    # admin-only does). It must now ask for the type/letter only.
    system = direction_prompt._SYSTEM_PROMPT
    assert "с его баллом из profile" not in system
    assert "БЕЗ балла/процента" in system


def test_growth_focus_has_four_sources_including_personality():
    # Область 9 §9.2 point 2: personality_notes (low tier) is a new admissible
    # growth_focus source, additive to the existing RIASEC/inquiry/subjects
    # ones — gated on relevance to a concrete requirement of the direction.
    system = direction_prompt._SYSTEM_PROMPT
    assert "Допустимые источники — ТОЛЬКО эти четыре" in system
    assert "personality_notes" in system


def test_target_why_guides_relevance_gated_personality_and_motivation_synthesis():
    # Область 9 §9.2 point 1: target.why synthesizes RIASEC fit + 1-2 genuinely
    # relevant personality_notes traits + motivation, not all five mechanically.
    system = direction_prompt._SYSTEM_PROMPT
    assert "personality_notes" in system
    assert "motivation_top" in system or "motivation_highlights" in system
    assert "не бери все пять механически" in system


def test_personality_guidance_explicitly_forbids_typology_labels():
    # ТЗ §3.1: no "ты интроверт"-style labeling. The new personality/motivation
    # synthesis instructions must guard against the model paraphrasing
    # personality_notes back into label language in why/evidence/step text.
    system = direction_prompt._SYSTEM_PROMPT
    assert "ты интроверт" in system  # cited as the explicit forbidden example
    assert "БЕЗ ЯРЛЫКОВ" in system


def test_step_description_no_longer_fixes_a_sentence_count():
    # Область 9 §9.3: "3-5 предложений" as a hard requirement is replaced by a
    # qualitative per-sentence criterion (а/б/в).
    system = direction_prompt._SYSTEM_PROMPT
    assert "description — 3-5 предложений" not in system


def test_university_requirements_block_never_shown_for_non_university_goals():
    # Backend passes [] for every non-university goal (roadmap_builder never
    # even computes it) — but guard the prompt layer too, in case that ever
    # changes: the block must key off "is it non-empty", not off the goal.
    reqs = [
        UniversityRequirement(
            program_name="p", university_name="u", city="c", exams=[],
        )
    ]
    _, user_message = direction_prompt.build_messages(_context("explore"), _DIRECTION, reqs)
    assert "ДАННЫЕ ПО ВУЗАМ" in user_message["content"]
