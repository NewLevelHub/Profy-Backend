"""Generation pipeline for the psychologist-view AI analysis: prompt → LLM →
validate → retry → give up (no deterministic fallback, unlike
report_narrative_service.py — see module docstring below for why).

Logging is structured and shallow, same rule as report_narrative_service.py
and llm_client.py: only attempt number, pass/fail, and validation issue
*codes* ever get logged — never issue.detail, the raw LLM response, or
anything from PsychAiAnalysisContext (student-derived data)."""
import json
import logging

from pydantic import ValidationError

from app.prompts import psych_ai_analysis as prompt
from app.schemas.psych_ai_analysis import PsychAiAnalysisOutput
from app.services import llm_client
from app.services.psych_ai_analysis_context import PsychAiAnalysisContext
from app.services.psych_ai_analysis_validator import ValidationIssue, validate

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # 1 initial + 2 retries

_CORRECTION_HINTS: dict[str, str] = {
    "missing_block_analysis": (
        "В block_analyses не хватает комментария для блока(ов): {detail}. "
        "Добавь по одному элементу block_analyses на каждый из них."
    ),
    "unknown_block": (
        "block_analyses ссылается на несуществующий блок: {detail}. "
        "Используй только значения block, совпадающие с key блоков из "
        "\"Блоки данных\"."
    ),
    "duplicate_block_analysis": (
        "Блок(и) {detail} упомянуты в block_analyses больше одного раза. "
        "Оставь ровно один элемент block_analyses на каждый блок."
    ),
    "empty_block_analysis": (
        "У блока {detail} пустой текст в block_analyses. Напиши реальный "
        "комментарий по данным этого блока."
    ),
    "final_summary_wrong_length": (
        "final_summary состоит из неверного числа предложений ({detail}). "
        "Перепиши final_summary так, чтобы в нём было 5-7 предложений."
    ),
    "recommended_profession_not_in_careers": (
        "recommended_profession.slug={detail!r} не входит в список "
        "профессий ученика. Выбери slug БУКВАЛЬНО из списка профессий, "
        "приведённого в данных — не изменяй и не придумывай его."
    ),
    "recommended_profession_no_reasoning": (
        "У recommended_profession пустой reasoning. Напиши, почему именно "
        "эта профессия из списка подходит этому ученику по совокупности "
        "данных."
    ),
    "recommended_profession_when_none_available": (
        "Список профессий пуст, но recommended_profession.slug={detail!r} "
        f"не равен \"{prompt.NO_RECOMMENDATION_SLUG}\". Верни ровно "
        f'{{"slug": "{prompt.NO_RECOMMENDATION_SLUG}", "name": "", "reasoning": ""}}.'
    ),
    "recommended_profession_missing": "Поле recommended_profession обязательно, даже если список профессий пуст.",
}


def _log_generation_error(attempt: int, exc: Exception) -> None:
    logger.warning("psych_ai_analysis attempt=%s status=error error_type=%s", attempt, type(exc).__name__)


def _log_attempt(attempt: int, issues: list[ValidationIssue]) -> None:
    if not issues:
        logger.info("psych_ai_analysis attempt=%s status=ok", attempt)
        return
    codes = sorted({issue.code for issue in issues})
    logger.warning(
        "psych_ai_analysis attempt=%s status=invalid issue_codes=%s issue_count=%s",
        attempt, codes, len(issues),
    )


def _correction_message(issues: list[ValidationIssue]) -> str:
    lines = []
    for issue in issues:
        hint = _CORRECTION_HINTS.get(issue.code)
        lines.append(f"- {hint.format(detail=issue.detail)}" if hint else f"- {issue.code}: {issue.detail}")
    return (
        "Твой предыдущий ответ не прошёл проверку. Конкретные проблемы:\n"
        + "\n".join(lines)
        + "\n\nПришли новый полный JSON-ответ по той же схеме, который "
        "исправляет именно эти проблемы — не меняй остальное без необходимости."
    )


def _drop_no_recommendation_sentinel(output: PsychAiAnalysisOutput) -> PsychAiAnalysisOutput:
    """After validation passes, a sentinel slug (junior / careers-less
    context) becomes a real `None` for every downstream consumer — no
    caller outside this module should ever see the sentinel string."""
    if output.recommended_profession is not None and output.recommended_profession.slug == prompt.NO_RECOMMENDATION_SLUG:
        return output.model_copy(update={"recommended_profession": None})
    return output


async def generate_psych_ai_analysis(
    context: PsychAiAnalysisContext,
) -> tuple[PsychAiAnalysisOutput | None, bool]:
    """Returns (analysis, is_ai_generated). Unlike report_narrative_service
    (which MUST always show a student something), a psychologist can
    tolerate "not available right now" — so on total failure this returns
    (None, False) rather than a deterministic template pretending to be
    real analysis of data it never actually looked at."""
    if not llm_client.is_enabled():
        return None, False

    messages = prompt.build_messages(context)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = await llm_client.complete_json(messages, prompt.JSON_SCHEMA, "psych_ai_analysis")
            output = PsychAiAnalysisOutput.model_validate(raw)
        except (llm_client.LLMError, ValidationError, TypeError) as exc:
            _log_generation_error(attempt, exc)
            continue

        issues = validate(output, context)
        _log_attempt(attempt, issues)
        if not issues:
            return _drop_no_recommendation_sentinel(output), True

        if attempt < MAX_ATTEMPTS:
            messages = messages + [
                {"role": "assistant", "content": json.dumps(raw, ensure_ascii=False)},
                {"role": "user", "content": _correction_message(issues)},
            ]

    return None, False
