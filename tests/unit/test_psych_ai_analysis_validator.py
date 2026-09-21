"""PRO-338+ — psych_ai_analysis_validator.py: the grounding check that
enforces "recommended_profession must be one of the student's own top
professions, never invented" server-side, plus block-coverage/shape checks.
Pure functions, no DB/LLM."""
from app.prompts.psych_ai_analysis import NO_RECOMMENDATION_SLUG
from app.schemas.psych_ai_analysis import BlockAnalysisItem, ProfessionRecommendation, PsychAiAnalysisOutput
from app.services.psych_ai_analysis_context import BlockData, CareerOption, PsychAiAnalysisContext
from app.services.psych_ai_analysis_validator import validate

_SEVEN_SENTENCE_SUMMARY = "Раз. Два. Три. Четыре. Пять. Шесть. Семь."
_FOUR_SENTENCE_SUMMARY = "Раз. Два. Три. Четыре."


def _context(*, blocks: list[str] | None = None, careers: list[CareerOption] | None = None) -> PsychAiAnalysisContext:
    return PsychAiAnalysisContext(
        student_name="Т",
        blocks=[BlockData(key=k, label=k, facts={"x": 1}) for k in (blocks or ["riasec"])],
        careers=careers or [],
    )


def _output(
    *, blocks: list[str] | None = None, summary: str = _SEVEN_SENTENCE_SUMMARY,
    profession: ProfessionRecommendation | None = None,
) -> PsychAiAnalysisOutput:
    return PsychAiAnalysisOutput(
        block_analyses=[BlockAnalysisItem(block=k, text="Комментарий.") for k in (blocks or ["riasec"])],
        final_summary=summary,
        recommended_profession=profession,
    )


def test_valid_output_with_a_real_career_passes() -> None:
    context = _context(careers=[CareerOption(slug="swe", name="Разработчик", why="почему")])
    output = _output(profession=ProfessionRecommendation(slug="swe", name="Разработчик", reasoning="Обоснование."))

    assert validate(output, context) == []


def test_invented_profession_slug_is_rejected() -> None:
    context = _context(careers=[CareerOption(slug="swe", name="Разработчик", why="почему")])
    output = _output(profession=ProfessionRecommendation(slug="astronaut", name="Космонавт", reasoning="Обоснование."))

    issues = validate(output, context)
    assert any(i.code == "recommended_profession_not_in_careers" for i in issues)


def test_no_careers_requires_the_sentinel_slug() -> None:
    context = _context(careers=[])
    output = _output(profession=ProfessionRecommendation(slug="swe", name="Разработчик", reasoning="x"))

    issues = validate(output, context)
    assert any(i.code == "recommended_profession_when_none_available" for i in issues)


def test_no_careers_with_sentinel_slug_passes() -> None:
    context = _context(careers=[])
    output = _output(profession=ProfessionRecommendation(slug=NO_RECOMMENDATION_SLUG, name="", reasoning=""))

    assert validate(output, context) == []


def test_missing_recommended_profession_is_rejected() -> None:
    context = _context(careers=[CareerOption(slug="swe", name="Разработчик", why="почему")])
    output = _output(profession=None)

    issues = validate(output, context)
    assert any(i.code == "recommended_profession_missing" for i in issues)


def test_profession_with_empty_reasoning_is_rejected() -> None:
    context = _context(careers=[CareerOption(slug="swe", name="Разработчик", why="почему")])
    output = _output(profession=ProfessionRecommendation(slug="swe", name="Разработчик", reasoning="   "))

    issues = validate(output, context)
    assert any(i.code == "recommended_profession_no_reasoning" for i in issues)


def test_missing_block_analysis_is_flagged() -> None:
    context = _context(blocks=["riasec", "big_five"])
    output = _output(blocks=["riasec"], profession=None)  # profession=None also flags separately, ignored here

    issues = validate(output, context)
    assert any(i.code == "missing_block_analysis" and "big_five" in i.detail for i in issues)


def test_unknown_block_is_flagged() -> None:
    context = _context(blocks=["riasec"])
    output = _output(blocks=["riasec", "made_up_block"])

    issues = validate(output, context)
    assert any(i.code == "unknown_block" for i in issues)


def test_duplicate_block_analysis_is_flagged() -> None:
    context = _context(blocks=["riasec"])
    output = PsychAiAnalysisOutput(
        block_analyses=[
            BlockAnalysisItem(block="riasec", text="Первый."),
            BlockAnalysisItem(block="riasec", text="Второй."),
        ],
        final_summary=_SEVEN_SENTENCE_SUMMARY,
        recommended_profession=None,
    )

    issues = validate(output, context)
    assert any(i.code == "duplicate_block_analysis" for i in issues)


def test_final_summary_too_short_is_flagged() -> None:
    context = _context()
    output = _output(summary="Одно предложение.")

    issues = validate(output, context)
    assert any(i.code == "final_summary_wrong_length" for i in issues)


def test_final_summary_within_range_passes_the_length_check() -> None:
    context = _context(careers=[CareerOption(slug="swe", name="Разработчик", why="почему")])
    output = _output(summary=_FOUR_SENTENCE_SUMMARY, profession=ProfessionRecommendation(slug="swe", name="Разработчик", reasoning="x"))

    issues = validate(output, context)
    assert not any(i.code == "final_summary_wrong_length" for i in issues)
