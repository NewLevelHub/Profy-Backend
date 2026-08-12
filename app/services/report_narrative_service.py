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


async def generate_report_narrative(
    context: ReportNarrativeContext,
    *,
    language: str = "ru",
) -> tuple[ReportNarrativeOutput, bool]:
    """Returns (narrative, is_ai_generated). Never raises — always resolves
    to a valid narrative, falling back deterministically on any failure."""
    if llm_client.is_enabled():
        messages = prompt.build_messages(context, language=language)
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

    logger.warning(
        "report_narrative fallback age_group=%s interest_instrument=%s",
        context.age_group, context.interest_instrument,
    )
    return build_fallback_narrative(context), False
