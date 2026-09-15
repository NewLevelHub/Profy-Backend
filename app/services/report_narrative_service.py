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

from app.i18n.catalog import tr
from app.models.profile import AgeGroup
from app.prompts import report_narrative as prompt
from app.prompts import report_narrative_translate as translate_prompt
from app.schemas.report_narrative import NarrativeCard, ReportNarrativeOutput
from app.schemas.report_narrative_context import ReportNarrativeContext
from app.services import llm_client
from app.services.report_narrative_fallback import build_fallback_narrative
from app.services.report_narrative_validator import (
    ValidationIssue,
    _check_banned_vocabulary,
    _check_language,
    validate,
)

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 3  # 1 initial + 2 retries

_metric_counts: dict[str, int] = {}


def record_language_mismatch(locale: str) -> None:
    key = f"llm.language_mismatch:locale={locale}"
    _metric_counts[key] = _metric_counts.get(key, 0) + 1
    logger.warning("llm.language_mismatch locale=%s", locale)


def record_fallback(reason: str) -> None:
    key = f"llm.fallback:reason={reason}"
    _metric_counts[key] = _metric_counts.get(key, 0) + 1
    logger.warning("llm.fallback reason=%s", reason)


def metric_counts() -> dict[str, int]:
    return dict(_metric_counts)


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
    "source_id_leak": (
        "В видимом тексте (title/description) буквально встречается "
        "source_id {detail!r} — так писать нельзя, это внутренний "
        "идентификатор, а не часть текста для ребёнка. Убери его из текста "
        "полностью (не заменяй похожей фразой в скобках) — ссылка на этот "
        "факт должна быть только в поле evidence_ids этой же карточки."
    ),
    "summary_wrong_length": (
        "summary состоит из неверного числа предложений ({detail}). "
        "Перепиши summary так, чтобы в нём было РОВНО 5-6 полных предложений, "
        "и каждое добавляло новое содержание, а не повторяло другое (не "
        "используй фразу про «карту возможностей» — см. следующее правило)."
    ),
    "summary_duplicates_disclaimer": (
        "summary содержит фразу {detail!r} — это дублирует отдельный "
        "disclaimer, который и так показывается рядом с summary на странице. "
        "Убери это предложение целиком и замени его предложением с новым "
        "содержанием (например практичный совет, на что обратить внимание "
        "дальше в отчёте)."
    ),
    "final_analysis_too_short": (
        "final_analysis состоит из недостаточного числа предложений "
        "({detail}). Должно быть минимум 3 предложения, связывающих минимум "
        "два разных раздела отчёта между собой (например интересы + "
        "характер, или стиль мышления + мотивация) — не пересказ одного "
        "раздела."
    ),
    "final_analysis_duplicates_disclaimer": (
        "final_analysis содержит фразу {detail!r} — это дублирует "
        "disclaimer. Убери это предложение и замени его мыслью о том, как "
        "разделы отчёта связаны между собой."
    ),
    "final_analysis_length": (
        "final_analysis слишком длинный или слишком короткий ({detail}). "
        "Должно быть 3-5 содержательных предложений, не больше."
    ),
}


def _correction_message(issues: list[ValidationIssue], *, language: str = "ru") -> str:
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
    catalog = tr("validator", locale=language)
    header = catalog.get("correction_header", "Твой предыдущий ответ не прошёл проверку. Конкретные проблемы:\n")
    footer = catalog.get(
        "correction_footer",
        "\n\nПришли новый полный JSON-ответ по той же схеме, который "
        "исправляет именно эти проблемы — не меняй остальное без необходимости.",
    )
    lines = []
    for issue in issues:
        hint = catalog.get(issue.code) or _CORRECTION_HINTS.get(issue.code)
        if hint:
            try:
                lines.append(f"- {hint.format(detail=issue.detail)}")
            except Exception:
                lines.append(f"- {hint}")
        else:
            lines.append(f"- {issue.code}: {issue.detail}")
    return header + "\n".join(lines) + footer


async def generate_report_narrative(
    context: ReportNarrativeContext,
    *,
    language: str = "ru",
) -> tuple[ReportNarrativeOutput, bool]:
    """Returns (narrative, is_ai_generated). Never raises — always resolves
    to a valid narrative, falling back deterministically on any failure."""
    if not llm_client.is_enabled():
        # Deterministic narrative is the *intended* path when the LLM is off,
        # not a fallback event — don't touch llm.fallback / log a warning, or
        # the validation-fallback rate alerts fire purely because a config
        # flag is off (nothing was generated, nothing failed validation).
        return build_fallback_narrative(context, locale=language), False

    had_language_mismatch = False
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

        if any(issue.code == "LANGUAGE_MISMATCH" for issue in issues):
            had_language_mismatch = True
            record_language_mismatch(language)

        last_raw = raw

        if attempt < MAX_ATTEMPTS:
            # Corrective retry: quote the model's own mistake back to it
            # instead of blindly resending the identical prompt (see
            # _correction_message docstring for why this matters).
            messages = messages + [
                {"role": "assistant", "content": json.dumps(last_raw, ensure_ascii=False)},
                {"role": "user", "content": _correction_message(issues, language=language)},
            ]

    if had_language_mismatch:
        record_fallback("language")
    else:
        record_fallback("validation")

    logger.warning(
        "report_narrative fallback age_group=%s interest_instrument=%s language=%s had_language_mismatch=%s",
        context.age_group, context.interest_instrument, language, had_language_mismatch,
    )
    return build_fallback_narrative(context, locale=language), False


def _translated_texts(raw: dict) -> list[str]:
    cards = list(raw.get("strength_cards") or []) + list(raw.get("thinking_style_notes") or [])
    return (
        [raw.get("summary") or "", raw.get("final_analysis") or ""]
        + [c.get("title") or "" for c in cards]
        + [c.get("description") or "" for c in cards]
    )


_KK_SPECIFIC = set("әғқңөұүһі")


def _kazakh_leak_into_ru(texts: list[str]) -> list[ValidationIssue]:
    """`_check_language(..., "ru")` compares Cyrillic-vs-Latin and treats
    Kazakh-only letters as neither, so a kk->ru translation that stayed
    half-Kazakh slips through. Flag it if Kazakh-specific letters are more
    than a rounding error of the Cyrillic mass (a couple of proper nouns
    like «әл-Фараби» are fine)."""
    blob = " ".join(texts).lower()
    cyr = sum(1 for c in blob if "а" <= c <= "я" or c == "ё" or c in _KK_SPECIFIC)
    kk = sum(1 for c in blob if c in _KK_SPECIFIC)
    if cyr >= 40 and kk / cyr > 0.02:
        return [ValidationIssue("LANGUAGE_MISMATCH", f"kk-specific letters {kk}/{cyr} in ru translation")]
    return []


async def translate_report_narrative(
    context: ReportNarrativeContext,
    *,
    source: dict,
    source_locale: str,
    target_locale: str,
) -> tuple[ReportNarrativeOutput, bool]:
    """Render an already-generated & validated narrative (`source`: the primary
    locale's stored `summary` / `final_analysis` / `strength_cards` /
    `thinking_style_notes`) into `target_locale` with ONE LLM call, so both
    locales' reports say the same thing instead of being two independent
    generations.

    Only the four persisted text fields are translated; the transient
    interests / motivation / career narrative come from the deterministic
    scaffold (they're rebuilt deterministically on every read anyway —
    report_service._shape_response). Validation here is language + banned
    vocabulary only: structure is inherited from the source, which already
    passed the full `validate()`.

    Returns `(ReportNarrativeOutput, is_ai)`. Falls back to the deterministic
    narrative (in `target_locale`) on any failure — never raises."""
    base = build_fallback_narrative(context, locale=target_locale)
    if not llm_client.is_enabled():
        return base, False

    age_group = AgeGroup(context.age_group)
    n_cards = len(source["strength_cards"])
    n_notes = len(source["thinking_style_notes"])
    messages = translate_prompt.build_messages(
        source, source_locale=source_locale, target_locale=target_locale
    )
    last_raw: dict | None = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            raw = await llm_client.complete_json(
                messages, translate_prompt.TRANSLATE_JSON_SCHEMA, "report_narrative_translate"
            )
        except (llm_client.LLMError, TypeError) as exc:
            _log_generation_error(attempt, exc)
            continue

        cards = list(raw.get("strength_cards") or [])
        notes = list(raw.get("thinking_style_notes") or [])
        structural = []
        if len(cards) != n_cards or len(notes) != n_notes:
            structural = [ValidationIssue("translate_structure_mismatch",
                                          f"cards {len(cards)}/{n_cards} notes {len(notes)}/{n_notes}")]
        texts = _translated_texts(raw)
        issues = structural + _check_language(texts, target_locale) + \
            _check_banned_vocabulary(texts, age_group, target_locale)
        if target_locale == "ru":
            issues += _kazakh_leak_into_ru(texts)
        _log_attempt(attempt, issues)

        if not issues:
            return base.model_copy(update={
                "summary": raw["summary"],
                "final_analysis": raw["final_analysis"],
                "strength_cards": [
                    NarrativeCard(title=c["title"], description=c["description"]) for c in cards
                ],
                "thinking_style_notes": [
                    NarrativeCard(title=n["title"], description=n["description"]) for n in notes
                ],
            }), True

        if any(i.code == "LANGUAGE_MISMATCH" for i in issues):
            record_language_mismatch(target_locale)
        last_raw = raw
        if attempt < MAX_ATTEMPTS:
            messages = messages + [
                {"role": "assistant", "content": json.dumps(last_raw, ensure_ascii=False)},
                {"role": "user", "content": translate_prompt.correction_message(target_locale)},
            ]

    record_fallback("translate")
    logger.warning(
        "report_narrative translate fallback source=%s target=%s", source_locale, target_locale
    )
    return base, False
