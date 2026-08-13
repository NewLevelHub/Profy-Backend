"""Generation pipeline for the report narrative: prompt → LLM → validate →
retry → deterministic fallback. TZ_Profi.md §17.7/§17.8: at most 2 retries
(3 attempts total) against the validator in report_narrative_validator.py,
then an always-valid template built by report_narrative_fallback.py — the
student must never see an error instead of a report.

Logging is structured and deliberately shallow: only attempt number, pass/
fail, and validation issue *codes* (e.g. "banned_phrase") ever get logged —
never issue.detail (can contain the actual matched phrase or a real
evidence_id), the raw LLM response, or anything from ReportNarrativeContext
itself (student-derived text). This mirrors llm_client.py's own refusal to
log message content.
"""
import json
import logging

from pydantic import ValidationError

from app.prompts import report_narrative as prompt
from app.schemas.report_narrative import ReportNarrativeOutput
from app.schemas.report_narrative_context import ReportNarrativeContext
from app.services import llm_client
from app.services.report_narrative_fallback import build_fallback_narrative
from app.services.report_narrative_validator import ValidationIssue, validate

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # 1 initial + 2 retries


def _log_attempt(attempt: int, issues: list[ValidationIssue]) -> None:
    if not issues:
        logger.info("report_narrative attempt=%s status=ok", attempt)
        return
    codes = sorted({issue.code for issue in issues})
    logger.warning(
        "report_narrative attempt=%s status=invalid issue_codes=%s issue_count=%s",
        attempt, codes, len(issues),
    )


def _log_generation_error(attempt: int, exc: Exception) -> None:
    # type(exc).__name__ only — never str(exc): llm_client embeds raw
    # response fragments in some LLMError messages.
    logger.warning("report_narrative attempt=%s status=error error_type=%s", attempt, type(exc).__name__)


# Plain-language fix instructions per validator code — measured live that
# just echoing "career_narrative_evidence: <card title>" back to gpt-4o-mini
# isn't actionable enough for it to self-correct (docs/rs-progress-notes.md);
# spelling out *what to do about it* is. Falls back to the raw code:detail
# for anything not mapped here (still better than nothing).
_CORRECTION_HINTS: dict[str, str] = {
    "career_narrative_evidence": (
        "У карточки {detail!r} в career_narrative пустой или неверный "
        "evidence_ids. Добавь туда хотя бы один реальный source_id с "
        "source_type \"riasec_category\" из каталога — или, если ни один не "
        "подходит по смыслу, убери эту карточку совсем."
    ),
    "strength_card_excluded_source_leak": (
        "Карточка strength_cards с title {detail!r} ссылается на evidence с "
        "source_type \"thinking_style\" или \"motivation\" — так нельзя, эти "
        "факты только в thinking_style_notes/motivation_narrative. Убери эту "
        "карточку из strength_cards или замени на evidence другого типа."
    ),
    "strength_card_count": (
        "Неверное число карточек strength_cards ({detail}). Посчитай evidence, "
        "у которых source_type НЕ \"thinking_style\" и НЕ \"motivation\", и "
        "сделай ровно столько карточек (в пределах 5-7)."
    ),
    "strength_card_duplicate_evidence": (
        "Source_id {detail!r} процитирован больше чем в одной карточке "
        "strength_cards — какой-то один факт пересказан 2-3 разными "
        "карточками. Оставь этот source_id только в одной карточке, а "
        "остальные карточки с ним убери (не увеличивай их число сверх "
        "количества уникальных фактов)."
    ),
    "thinking_style_count": (
        "Неверное число карточек thinking_style_notes ({detail}). Должна быть "
        "РОВНО ОДНА карточка на ВСЕ evidence с source_type \"thinking_style\" "
        "вместе (даже если таких evidence два — не делай две отдельные "
        "карточки, объедини их в одну), и ноль карточек, если такого evidence "
        "нет вообще."
    ),
    "thinking_style_incomplete": (
        "Карточка thinking_style_notes не ссылается на все нужные evidence "
        "({detail}). Добавь в её evidence_ids source_id каждого сигнала "
        "thinking_style из каталога — сейчас в ней не хватает одного."
    ),
    "motivation_ungrounded": (
        "motivation_narrative.evidence_ids пуст, хотя в каталоге есть evidence "
        "с source_type \"motivation\". Добавь их source_id в evidence_ids."
    ),
    "summary_too_short": (
        "summary состоит из недостаточного числа предложений ({detail}). "
        "Перепиши summary так, чтобы в нём было минимум 3 полных предложения "
        "(рамочная фраза про «карту возможностей» считается одним из них, но "
        "не единственным)."
    ),
}


def _correction_message(issues: list[ValidationIssue]) -> str:
    """Turns this attempt's failures into feedback for the next one. A blind
    retry (same prompt, same mistake) measurably never recovers from a
    systematic misunderstanding — e.g. gpt-4o-mini reliably leaves
    career_narrative's evidence_ids empty regardless of how the base prompt
    phrases the rule, across all 3 attempts, every time this was tested live
    (docs/rs-progress-notes.md). Quoting the model's own mistake back to it,
    translated into a concrete instruction, is what actually gets it to
    self-correct — the bare code:detail pair alone measurably wasn't enough.

    issue.detail here is fine to send back to the model — it's exactly the
    context it needs to fix itself — but the caller must keep logging codes
    only, never detail (see module docstring)."""
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


async def generate_report_narrative(
    context: ReportNarrativeContext,
    *,
    language: str = "ru",
) -> tuple[ReportNarrativeOutput, bool]:
    """Returns (narrative, is_ai_generated). Never raises — always resolves
    to a valid narrative, falling back deterministically on any failure."""
    if llm_client.is_enabled():
        messages = prompt.build_messages(context, language=language)
        last_raw: dict | None = None
        for attempt in range(1, MAX_ATTEMPTS + 1):
            try:
                raw = await llm_client.complete_json(
                    messages, prompt.NARRATIVE_JSON_SCHEMA, "report_narrative"
                )
                output = ReportNarrativeOutput.model_validate(raw)
            except (llm_client.LLMError, ValidationError, TypeError) as exc:
                _log_generation_error(attempt, exc)
                continue

            issues = validate(output, context, language=language)
            _log_attempt(attempt, issues)
            if not issues:
                return output, True
            last_raw = raw

            if attempt < MAX_ATTEMPTS:
                # Corrective retry: quote the model's own mistake back to it
                # instead of blindly resending the identical prompt (see
                # _correction_message docstring for why this matters).
                messages = messages + [
                    {"role": "assistant", "content": json.dumps(last_raw, ensure_ascii=False)},
                    {"role": "user", "content": _correction_message(issues)},
                ]

    logger.warning(
        "report_narrative fallback age_group=%s interest_instrument=%s",
        context.age_group, context.interest_instrument,
    )
    return build_fallback_narrative(context), False
