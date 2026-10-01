"""PRO-338+ — psych_ai_analysis_service.py: prompt -> LLM -> validate ->
retry -> give up. Mocks llm_client entirely (no real network calls)."""
from unittest.mock import AsyncMock, patch

import pytest

from app.prompts.psych_ai_analysis import NO_RECOMMENDATION_SLUG
from app.services import llm_client, psych_ai_analysis_service
from app.services.psych_ai_analysis_context import BlockData, CareerOption, PsychAiAnalysisContext


def _context(*, careers: list[CareerOption] | None = None) -> PsychAiAnalysisContext:
    return PsychAiAnalysisContext(
        student_name="Т",
        blocks=[BlockData(key="riasec", label="Карта интересов", facts={"x": 1})],
        careers=careers or [],
    )


def _valid_raw(*, profession_slug: str = "swe") -> dict:
    return {
        "block_analyses": [{"block": "riasec", "text": "Комментарий по интересам."}],
        "final_summary": "Раз. Два. Три. Четыре.",
        "recommended_profession": {"slug": profession_slug, "name": "Разработчик", "reasoning": "Обоснование."},
    }


async def test_disabled_llm_returns_none_false() -> None:
    with patch.object(llm_client, "is_enabled", return_value=False):
        output, is_ai_generated = await psych_ai_analysis_service.generate_psych_ai_analysis(_context())

    assert output is None
    assert is_ai_generated is False


async def test_valid_first_attempt_succeeds() -> None:
    context = _context(careers=[CareerOption(slug="swe", name="Разработчик", why="почему")])
    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_valid_raw())),
    ):
        output, is_ai_generated = await psych_ai_analysis_service.generate_psych_ai_analysis(context)

    assert is_ai_generated is True
    assert output is not None
    assert output.recommended_profession.slug == "swe"
    assert output.block_analyses[0].block == "riasec"


async def test_no_recommendation_sentinel_becomes_none_after_validation() -> None:
    context = _context(careers=[])
    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=_valid_raw(profession_slug=NO_RECOMMENDATION_SLUG))),
    ):
        output, is_ai_generated = await psych_ai_analysis_service.generate_psych_ai_analysis(context)

    assert is_ai_generated is True
    assert output.recommended_profession is None


async def test_invalid_then_corrected_output_succeeds_on_retry() -> None:
    context = _context(careers=[CareerOption(slug="swe", name="Разработчик", why="почему")])
    invented = _valid_raw(profession_slug="astronaut")  # not in careers -> validator rejects
    corrected = _valid_raw(profession_slug="swe")

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(side_effect=[invented, corrected])) as mock_complete,
    ):
        output, is_ai_generated = await psych_ai_analysis_service.generate_psych_ai_analysis(context)

    assert is_ai_generated is True
    assert output.recommended_profession.slug == "swe"
    assert mock_complete.call_count == 2
    # The retry's messages include the corrective feedback, not a blind repeat.
    second_call_messages = mock_complete.call_args_list[1].args[0]
    assert any("astronaut" in m["content"] or "не входит" in m["content"] for m in second_call_messages)


async def test_persistent_invalid_output_gives_up_after_max_attempts() -> None:
    context = _context(careers=[CareerOption(slug="swe", name="Разработчик", why="почему")])
    always_invented = _valid_raw(profession_slug="astronaut")

    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(return_value=always_invented)) as mock_complete,
    ):
        output, is_ai_generated = await psych_ai_analysis_service.generate_psych_ai_analysis(context)

    assert output is None
    assert is_ai_generated is False
    assert mock_complete.call_count == psych_ai_analysis_service.MAX_ATTEMPTS


async def test_llm_error_every_attempt_gives_up_gracefully() -> None:
    context = _context()
    with (
        patch.object(llm_client, "is_enabled", return_value=True),
        patch.object(llm_client, "complete_json", new=AsyncMock(side_effect=llm_client.LLMError("boom"))),
    ):
        output, is_ai_generated = await psych_ai_analysis_service.generate_psych_ai_analysis(context)

    assert output is None
    assert is_ai_generated is False
