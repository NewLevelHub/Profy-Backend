"""Post-generation validator for the report narrative — the gate between
app.services.llm_client's structured output and anything that could reach a
child. Every rule traces to TZ_Profi.md §17.7 (validation requirements) and
Приложение C (banned/allowed phrasing).

Pure functions, no DB/LLM access, so the exact same checks run against both
the AI path (report_narrative_service.py) and the deterministic fallback
(report_narrative_fallback.py) — the fallback's own test suite asserts it
always produces zero issues here.
"""
import re
from dataclasses import dataclass

from app.models.profile import AgeGroup
from app.schemas.report_narrative import ReportNarrativeOutput
from app.schemas.report_narrative_context import ReportNarrativeContext
from app.services.mi_content import MI_LABELS
from app.services.report_narrative_context import unknown_source_ids
from app.services.riasec_content import RIASEC_LABELS

# Приложение C, В.1 — verbatim phrases, matched as lowercase substrings.
# Diagnoses/states is explicitly open-ended in the TZ ("любые формулировки о
# психическом или физическом состоянии") — the four roots below are a
# heuristic floor, not full coverage; TZ §17.7 pairs automated checks with
# admin review for exactly this reason.
BANNED_PHRASES: tuple[str, ...] = (
    "ты гуманитарий", "ты технарь", "ты творческая личность", "твой тип —",
    "ты относишься к типу", "ты интроверт", "ты экстраверт",
    "у тебя нет способностей", "тебе не даётся", "это не твоё",
    "тебе будет сложно в", "ты не справишься",
    "тебе не подходит", "эта профессия не для тебя", "не стоит идти в",
    "лучше выбери другое",
    "ты должен стать", "тебе нужно выбрать", "твоя профессия —",
    "низкий результат", "слабая сторона", "плохой показатель",
    "недостаточно", "провал", "отставание",
    "лучше, чем у большинства", "хуже, чем у сверстников",
    "средний уровень по возрасту",
    "ты точно поступишь", "у тебя высокие шансы",
    "вероятность поступления", "ты добьёшься успеха",
    "если не начнёшь сейчас", "ты уже отстаёшь",
    "времени почти не осталось",
    "диагноз", "расстройство", "синдром", "психическое состояние",
)

# TZ §4.1 / mi_content.py: junior is not career-oriented — no profession,
# university or exam language anywhere in a junior narrative.
JUNIOR_CAREER_TERMS: tuple[str, ...] = (
    "професси", "карьер", "университет", "поступлени", "специальност",
    "экзамен", "зарплат", "резюме", "собеседован", "диплом",
)

_MAX_CAREER_CARDS = 3

# Not exact TZ numbers (the TZ gives relative guidance — "объём в 2-3 раза
# меньше" — not char counts): a generous per-age ceiling that still keeps
# junior meaningfully shorter than senior, catching a runaway/rambling
# generation without rejecting normal evidence-derived sentences.
_SUMMARY_MAX_LEN = {AgeGroup.junior: 350, AgeGroup.middle: 550, AgeGroup.senior: 750}
_CARD_DESC_MAX_LEN = {AgeGroup.junior: 160, AgeGroup.middle: 240, AgeGroup.senior: 320}

_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)
_DIGIT_OR_PERCENT_RE = re.compile(r"[\d%]")
_MIN_CYRILLIC_RATIO = 0.85


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    detail: str


def _all_texts(output: ReportNarrativeOutput) -> list[str]:
    texts = [output.summary]
    for card in output.strength_cards + output.thinking_style_notes + output.career_narrative:
        texts += [card.title, card.description]
    for interest in output.interests:
        texts += [interest.title, interest.description]
    texts += [output.motivation_narrative.title, output.motivation_narrative.description]
    return texts


_MIN_LETTERS_TO_JUDGE = 15


def _check_language(texts: list[str], language: str) -> list[ValidationIssue]:
    if language != "ru":
        # Only ru content/vocabulary exists to validate against right now
        # (TZ_Profi.md §30 localization is future scope) — nothing to check.
        return []
    # Per-text, not aggregated: one field written in the wrong language must
    # not be diluted into a passing ratio by every other (correct) field.
    for text in texts:
        cyrillic = _CYRILLIC_RE.findall(text)
        letters = cyrillic + _LATIN_RE.findall(text)
        if len(letters) < _MIN_LETTERS_TO_JUDGE:
            continue  # too short to judge reliably (e.g. a bare category title)
        ratio = len(cyrillic) / len(letters)
        if ratio < _MIN_CYRILLIC_RATIO:
            return [ValidationIssue("language", f"cyrillic ratio {ratio:.2f} below {_MIN_CYRILLIC_RATIO}")]
    return []


def _check_banned_vocabulary(texts: list[str], age_group: AgeGroup) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    lowered = [t.lower() for t in texts]
    for phrase in BANNED_PHRASES:
        if any(phrase in t for t in lowered):
            issues.append(ValidationIssue("banned_phrase", phrase))
    if age_group == AgeGroup.junior:
        for term in JUNIOR_CAREER_TERMS:
            if any(term in t for t in lowered):
                issues.append(ValidationIssue("junior_career_term", term))
    return issues


def _check_no_new_numbers(texts: list[str]) -> list[ValidationIssue]:
    if any(_DIGIT_OR_PERCENT_RE.search(t) for t in texts):
        return [ValidationIssue("numeric_leak", "digit or percent sign in narrative text")]
    return []


def _check_evidence_ids(output: ReportNarrativeOutput, context: ReportNarrativeContext) -> list[ValidationIssue]:
    claimed: list[str] = list(output.motivation_narrative.evidence_ids)
    for card in output.strength_cards + output.thinking_style_notes + output.career_narrative:
        claimed += card.evidence_ids
    unknown = unknown_source_ids(context, claimed)
    return [ValidationIssue("unknown_evidence_id", sid) for sid in sorted(unknown)]


def _check_interests(output: ReportNarrativeOutput, context: ReportNarrativeContext) -> list[ValidationIssue]:
    labels = MI_LABELS if context.interest_instrument == "mi" else RIASEC_LABELS
    expected = set(labels.keys())
    got_categories = [i.category for i in output.interests]
    issues: list[ValidationIssue] = []

    if len(output.interests) != len(expected):
        issues.append(ValidationIssue(
            "interest_count", f"expected {len(expected)}, got {len(output.interests)}",
        ))
    if set(got_categories) != expected:
        issues.append(ValidationIssue(
            "interest_cardinality",
            f"expected categories {sorted(expected)}, got {sorted(set(got_categories))}",
        ))

    strength_source_type = "mi_category" if context.interest_instrument == "mi" else "riasec_category"
    strong_categories = {
        e.source_id.split(":", 1)[1] for e in context.evidence if e.source_type == strength_source_type
    }
    for item in output.interests:
        if item.tier == "strong" and item.category not in strong_categories:
            issues.append(ValidationIssue("interest_tier_unsupported", item.category))
    return issues


def _check_thinking_style_count(output: ReportNarrativeOutput, context: ReportNarrativeContext) -> list[ValidationIssue]:
    expected = sum(1 for e in context.evidence if e.source_type == "thinking_style")
    if len(output.thinking_style_notes) != expected:
        return [ValidationIssue(
            "thinking_style_count", f"expected {expected}, got {len(output.thinking_style_notes)}",
        )]
    return []


def _check_strength_card_count(output: ReportNarrativeOutput, context: ReportNarrativeContext) -> list[ValidationIssue]:
    available = len(context.evidence)
    lo, hi = min(5, available), min(7, available)
    count = len(output.strength_cards)
    if not (lo <= count <= hi):
        return [ValidationIssue("strength_card_count", f"expected {lo}-{hi}, got {count}")]
    return []


def _check_career_narrative(
    output: ReportNarrativeOutput, context: ReportNarrativeContext, age_group: AgeGroup
) -> list[ValidationIssue]:
    if age_group == AgeGroup.junior:
        if output.career_narrative:
            return [ValidationIssue("junior_career_narrative", "junior must not receive a career narrative")]
        return []

    issues: list[ValidationIssue] = []
    if len(output.career_narrative) > _MAX_CAREER_CARDS:
        issues.append(ValidationIssue(
            "career_narrative_count", f"at most {_MAX_CAREER_CARDS}, got {len(output.career_narrative)}",
        ))
    riasec_ids = {e.source_id for e in context.evidence if e.source_type == "riasec_category"}
    for card in output.career_narrative:
        if not card.evidence_ids or not set(card.evidence_ids) <= riasec_ids:
            issues.append(ValidationIssue("career_narrative_evidence", card.title))
    return issues


def _check_motivation_grounding(output: ReportNarrativeOutput, context: ReportNarrativeContext) -> list[ValidationIssue]:
    has_motivation_evidence = any(e.source_type == "motivation" for e in context.evidence)
    if has_motivation_evidence and not output.motivation_narrative.evidence_ids:
        return [ValidationIssue("motivation_ungrounded", "motivation evidence exists but wasn't cited")]
    return []


def _check_lengths(output: ReportNarrativeOutput, age_group: AgeGroup) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    summary_max = _SUMMARY_MAX_LEN[age_group]
    if not (10 <= len(output.summary) <= summary_max):
        issues.append(ValidationIssue("summary_length", f"len={len(output.summary)}, max={summary_max}"))

    desc_max = _CARD_DESC_MAX_LEN[age_group]
    all_cards = output.strength_cards + output.thinking_style_notes + output.career_narrative + [output.motivation_narrative]
    for card in all_cards:
        if not (5 <= len(card.description) <= desc_max):
            issues.append(ValidationIssue("card_length", f"{card.title!r} len={len(card.description)}, max={desc_max}"))
    return issues


def validate(
    output: ReportNarrativeOutput,
    context: ReportNarrativeContext,
    *,
    language: str = "ru",
) -> list[ValidationIssue]:
    age_group = AgeGroup(context.age_group)
    texts = _all_texts(output)

    issues: list[ValidationIssue] = []
    issues += _check_language(texts, language)
    issues += _check_banned_vocabulary(texts, age_group)
    issues += _check_no_new_numbers(texts)
    issues += _check_evidence_ids(output, context)
    issues += _check_interests(output, context)
    issues += _check_thinking_style_count(output, context)
    issues += _check_strength_card_count(output, context)
    issues += _check_career_narrative(output, context, age_group)
    issues += _check_motivation_grounding(output, context)
    issues += _check_lengths(output, age_group)
    return issues
