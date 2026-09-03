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
from app.services.mi_content import mi_labels
from app.services.report_narrative_context import STRENGTH_CARD_EXCLUDED_SOURCE_TYPES, unknown_source_ids
from app.services.riasec_content import riasec_labels

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
# generation without rejecting normal evidence-derived sentences. Raised
# 2026-08-17 alongside the 3->5-6 sentence bump (product decision) — must
# stay above report_narrative_fallback._summary()'s own length for every
# age group, or the fallback would fail its own validator.
_SUMMARY_MAX_LEN = {AgeGroup.junior: 550, AgeGroup.middle: 800, AgeGroup.senior: 1000}
_CARD_DESC_MAX_LEN = {AgeGroup.junior: 160, AgeGroup.middle: 240, AgeGroup.senior: 320}
# thinking_style_notes gets its own, larger budget: it's now one card
# merging up to 2 signals (cue + example each) plus, for middle/senior, a
# real-world-relevance sentence AND (when there's a high-tier personality
# trait) one more sentence synthesizing it with the style — more genuine
# content than a single strength/career card ever carries, not padding.
_THINKING_STYLE_DESC_MAX_LEN = {AgeGroup.junior: 220, AgeGroup.middle: 480, AgeGroup.senior: 560}
# final_analysis: last section of the report, 3-5 sentences tying multiple
# earlier sections together — naturally longer than a single card.
_FINAL_ANALYSIS_MAX_LEN = {AgeGroup.junior: 400, AgeGroup.middle: 550, AgeGroup.senior: 650}

_CYRILLIC_RE = re.compile(r"[а-яё]", re.IGNORECASE)
_LATIN_RE = re.compile(r"[a-z]", re.IGNORECASE)
_DIGIT_OR_PERCENT_RE = re.compile(r"[\d%]")
_MIN_CYRILLIC_RATIO = 0.85
_SENTENCE_END_RE = re.compile(r"[.!?]+(?=\s|$)")
# Product decision, 2026-08-17: summary must be 5-6 sentences, not the
# earlier 3-5 — each new sentence must add real framing (see
# report_narrative_fallback._summary's own docstring), not pad toward the
# count, so the range is enforced both ways rather than just a floor.
_MIN_SUMMARY_SENTENCES = 5
_MAX_SUMMARY_SENTENCES = 6
_MIN_FINAL_ANALYSIS_SENTENCES = 3


@dataclass(frozen=True)
class ValidationIssue:
    code: str
    detail: str


def _all_texts(output: ReportNarrativeOutput) -> list[str]:
    texts = [output.summary, output.final_analysis]
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
    labels = mi_labels() if context.interest_instrument == "mi" else riasec_labels()
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
    """1 or 2 real thinking_style signals must land in exactly ONE merged
    card, not one card each (2 separate, identically-titled cards read as
    duplicated — user feedback). The card must cite every thinking_style
    source_id that exists, not just one of two."""
    thinking_style_ids = {e.source_id for e in context.evidence if e.source_type == "thinking_style"}
    expected_cards = 1 if thinking_style_ids else 0
    if len(output.thinking_style_notes) != expected_cards:
        return [ValidationIssue(
            "thinking_style_count", f"expected {expected_cards} card(s), got {len(output.thinking_style_notes)}",
        )]
    if expected_cards == 1:
        cited = set(output.thinking_style_notes[0].evidence_ids)
        if not thinking_style_ids <= cited:
            return [ValidationIssue(
                "thinking_style_incomplete",
                f"card must cite all of {sorted(thinking_style_ids)}, cited {sorted(cited)}",
            )]
    return []


def _check_strength_card_count(output: ReportNarrativeOutput, context: ReportNarrativeContext) -> list[ValidationIssue]:
    # thinking_style evidence doesn't count here — it's reserved for
    # thinking_style_notes (see _check_strength_card_sources below), so it
    # can't inflate the pool this cardinality is measured against.
    available = sum(1 for e in context.evidence if e.source_type not in STRENGTH_CARD_EXCLUDED_SOURCE_TYPES)
    lo, hi = min(5, available), min(7, available)
    count = len(output.strength_cards)
    if not (lo <= count <= hi):
        return [ValidationIssue("strength_card_count", f"expected {lo}-{hi}, got {count}")]
    return []


def _check_strength_card_sources(output: ReportNarrativeOutput, context: ReportNarrativeContext) -> list[ValidationIssue]:
    """TZ_Profi.md §18.2 п.2 vs п.4: "Сильные стороны" and "Стиль мышления"
    are two different sections — a strength_card citing thinking_style
    evidence would duplicate thinking_style_notes verbatim, so this is
    rejected structurally rather than left to prompt-following alone."""
    excluded_ids = {e.source_id for e in context.evidence if e.source_type in STRENGTH_CARD_EXCLUDED_SOURCE_TYPES}
    issues: list[ValidationIssue] = []
    for card in output.strength_cards:
        leaked = excluded_ids & set(card.evidence_ids)
        if leaked:
            issues.append(ValidationIssue("strength_card_excluded_source_leak", card.title))
    return issues


def _check_strength_card_duplicate_evidence(output: ReportNarrativeOutput) -> list[ValidationIssue]:
    """_check_strength_card_count only bounds the total number of cards — it
    never stops the model from citing the same source_id from more than one
    card, paraphrased differently each time. Measured live: with a small
    evidence pool, gpt-4o-mini did exactly this (one real fact turned into
    2-3 "different" strength cards) — the student sees the same observation
    repeated in different words, which reads as duplication/padding."""
    seen: set[str] = set()
    issues: list[ValidationIssue] = []
    for card in output.strength_cards:
        for source_id in card.evidence_ids:
            if source_id in seen:
                issues.append(ValidationIssue("strength_card_duplicate_evidence", source_id))
            seen.add(source_id)
    return issues


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


def _check_no_source_id_leak(output: ReportNarrativeOutput, context: ReportNarrativeContext) -> list[ValidationIssue]:
    """evidence_ids (e.g. "riasec:E") are internal citation keys for
    grounding, never meant for the child to read. Found live: a strength
    card ending "...организовывать других (riasec:E)." — the model citing
    its source inline like a footnote instead of using evidence_ids as
    instructed. _check_language's Cyrillic-ratio check doesn't catch this
    (the leaked id is a tiny fraction of an otherwise-Russian sentence)."""
    texts = _all_texts(output)
    issues: list[ValidationIssue] = []
    for evidence in context.evidence:
        if any(evidence.source_id in t for t in texts):
            issues.append(ValidationIssue("source_id_leak", evidence.source_id))
    return issues


def _check_motivation_grounding(output: ReportNarrativeOutput, context: ReportNarrativeContext) -> list[ValidationIssue]:
    has_motivation_evidence = any(e.source_type == "motivation" for e in context.evidence)
    if has_motivation_evidence and not output.motivation_narrative.evidence_ids:
        return [ValidationIssue("motivation_ungrounded", "motivation evidence exists but wasn't cited")]
    return []


# Substrings of the "не окончательный выбор / карта возможных направлений"
# framing — DISCLAIMER (app/schemas/result_v2.py) already carries this exact
# idea, shown right next to summary on the page every time, unconditionally.
# A prompt instruction alone wasn't reliable here (this is what the model
# used to be *required* to write, so it needs an active check now that the
# requirement is reversed, not just silence) — user feedback: it showed up
# in the summary "often", duplicating the disclaimer line right below it.
_FRAME_PHRASE_SUBSTRINGS: tuple[str, ...] = (
    "не окончательный выбор",
    "карта возможных направлений",
)


def _check_no_disclaimer_duplicate(output: ReportNarrativeOutput) -> list[ValidationIssue]:
    """Applies to both summary and final_analysis — same reasoning either
    way: DISCLAIMER already carries this exact idea, shown unconditionally
    on the page, so writing it again anywhere in the LLM's own text
    duplicates that line."""
    issues: list[ValidationIssue] = []
    for field_name, text in (("summary", output.summary), ("final_analysis", output.final_analysis)):
        lowered = text.lower()
        for phrase in _FRAME_PHRASE_SUBSTRINGS:
            if phrase in lowered:
                code = "summary_duplicates_disclaimer" if field_name == "summary" else "final_analysis_duplicates_disclaimer"
                issues.append(ValidationIssue(code, phrase))
                break
    return issues


def _check_summary_sentence_count(output: ReportNarrativeOutput) -> list[ValidationIssue]:
    """TZ_Profi.md §18.2 п.1's summary read as too thin at 2-3 sentences —
    user feedback (2026-08-17) asked for exactly 5-6, enforced as a range
    (not just a floor) so the model can't pad past 6 with filler either."""
    count = len(_SENTENCE_END_RE.findall(output.summary.strip()))
    if count < _MIN_SUMMARY_SENTENCES or count > _MAX_SUMMARY_SENTENCES:
        return [ValidationIssue(
            "summary_wrong_length",
            f"expected {_MIN_SUMMARY_SENTENCES}-{_MAX_SUMMARY_SENTENCES} sentences, got {count}",
        )]
    return []


def _check_final_analysis_sentence_count(output: ReportNarrativeOutput) -> list[ValidationIssue]:
    """final_analysis is the closing, whole-report synthesis — asked for
    explicitly (user feedback) as its own 3-5 sentence block, distinct from
    summary (written first, before the reader has seen the rest)."""
    count = len(_SENTENCE_END_RE.findall(output.final_analysis.strip()))
    if count < _MIN_FINAL_ANALYSIS_SENTENCES:
        return [ValidationIssue(
            "final_analysis_too_short", f"expected >= {_MIN_FINAL_ANALYSIS_SENTENCES} sentences, got {count}",
        )]
    return []


def _check_lengths(output: ReportNarrativeOutput, age_group: AgeGroup) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    summary_max = _SUMMARY_MAX_LEN[age_group]
    if not (10 <= len(output.summary) <= summary_max):
        issues.append(ValidationIssue("summary_length", f"len={len(output.summary)}, max={summary_max}"))

    final_analysis_max = _FINAL_ANALYSIS_MAX_LEN[age_group]
    if not (10 <= len(output.final_analysis) <= final_analysis_max):
        issues.append(ValidationIssue(
            "final_analysis_length", f"len={len(output.final_analysis)}, max={final_analysis_max}",
        ))

    desc_max = _CARD_DESC_MAX_LEN[age_group]
    all_cards = output.strength_cards + output.career_narrative + [output.motivation_narrative]
    for card in all_cards:
        if not (5 <= len(card.description) <= desc_max):
            issues.append(ValidationIssue("card_length", f"{card.title!r} len={len(card.description)}, max={desc_max}"))

    ts_max = _THINKING_STYLE_DESC_MAX_LEN[age_group]
    for card in output.thinking_style_notes:
        if not (5 <= len(card.description) <= ts_max):
            issues.append(ValidationIssue("card_length", f"{card.title!r} len={len(card.description)}, max={ts_max}"))
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
    issues += _check_strength_card_sources(output, context)
    issues += _check_strength_card_duplicate_evidence(output)
    issues += _check_career_narrative(output, context, age_group)
    issues += _check_no_source_id_leak(output, context)
    issues += _check_motivation_grounding(output, context)
    issues += _check_summary_sentence_count(output)
    issues += _check_final_analysis_sentence_count(output)
    issues += _check_no_disclaimer_duplicate(output)
    issues += _check_lengths(output, age_group)
    return issues
