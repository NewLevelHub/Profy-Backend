"""Deterministic, LLM-free narrative builder — TZ_Profi.md §17.8: shown to
the student when the LLM is disabled/unavailable or fails validation on all
attempts (see report_narrative_service.py). Reuses the exact same evidence
catalog and label tables (mi_content.py/riasec_content.py) as the AI path —
same source of truth, just no personalization — so it tells the same
underlying story instead of a generic placeholder.

Built to satisfy report_narrative_validator.validate() by construction:
every fact is reused verbatim from ReportNarrativeContext.evidence, nothing
here is invented, so a validator failure on this output would mean the
validator itself is wrong (see tests/unit/test_report_narrative_fallback.py).
"""
from app.models.profile import AgeGroup
from app.schemas.report_narrative import (
    InterestCard,
    MotivationNarrative,
    NarrativeCard,
    ReportNarrativeOutput,
)
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.mi_content import MI_LABELS
from app.services.riasec_content import RIASEC_LABELS

# TZ_Profi.md §17.5 point 7 / Приложение C В.2 — required framing, reused
# verbatim by both this fallback and instructed identically to the LLM.
_FRAME_PHRASE = "Это не окончательный выбор, а карта возможных направлений."

_STRENGTH_CARD_TITLES: dict[str, str] = {
    "mi_category": "Тебе интересно",
    "riasec_category": "Тебе интересно",
    "personality": "Твой характер",
    "motivation": "Что тебя драйвит",
    "thinking_style": "Как тебе легче думать",
    "subject_liked": "Любимый предмет",
    "subject_easy": "Даётся легко",
    "artifact": "Твой опыт",
}

# Приложение C В.2 style ("вместо слабой стороны — проверяемое действие") —
# never framed as a deficiency, just quieter than the evidenced categories.
_STEADY_INTEREST_NOTE = (
    "Сейчас это проявляется тише, чем другие сферы — и это нормально: "
    "широкие интересы дают больше вариантов, куда можно посмотреть."
)

_NO_MOTIVATION_SIGNAL = "Пока рано выделять что-то одно — и это нормально, интерес может проявиться позже."

_CAREER_CARD_DESCRIPTION = (
    "Это направление хорошо совпало с твоими ответами — можно попробовать "
    "что-то в этой сфере и посмотреть, откликается ли."
)


def _summary(age_group: AgeGroup) -> str:
    if age_group == AgeGroup.junior:
        return f"Ты попробовал разные задания, и по ответам видно, чем тебе интересно заниматься. {_FRAME_PHRASE}"
    return (
        f"По твоим ответам заметно, что тебе интересны определённые сферы и есть сильные стороны, на "
        f"которые стоит опереться. {_FRAME_PHRASE}"
    )


def _strength_cards(context: ReportNarrativeContext) -> list[NarrativeCard]:
    count = min(7, len(context.evidence))
    return [
        NarrativeCard(
            title=_STRENGTH_CARD_TITLES.get(item.source_type, "Сильная сторона"),
            description=item.text,
            evidence_ids=[item.source_id],
        )
        for item in context.evidence[:count]
    ]


def _interests(context: ReportNarrativeContext) -> list[InterestCard]:
    is_mi = context.interest_instrument == "mi"
    labels = MI_LABELS if is_mi else RIASEC_LABELS
    source_type = "mi_category" if is_mi else "riasec_category"
    strong: dict[str, EvidenceItem] = {
        e.source_id.split(":", 1)[1]: e for e in context.evidence if e.source_type == source_type
    }
    cards = []
    for key, label in labels.items():
        if key in strong:
            cards.append(InterestCard(category=key, tier="strong", title=label, description=strong[key].text))
        else:
            cards.append(InterestCard(category=key, tier="steady", title=label, description=_STEADY_INTEREST_NOTE))
    return cards


def _thinking_style_notes(context: ReportNarrativeContext) -> list[NarrativeCard]:
    return [
        NarrativeCard(title="Как тебе легче думать", description=e.text, evidence_ids=[e.source_id])
        for e in context.evidence
        if e.source_type == "thinking_style"
    ]


def _motivation_narrative(context: ReportNarrativeContext) -> MotivationNarrative:
    items = [e for e in context.evidence if e.source_type == "motivation"]
    if not items:
        return MotivationNarrative(title="Что тебя драйвит", description=_NO_MOTIVATION_SIGNAL, evidence_ids=[])
    return MotivationNarrative(
        title="Что тебя драйвит",
        description=" ".join(e.text for e in items),
        evidence_ids=[e.source_id for e in items],
    )


def _career_narrative(context: ReportNarrativeContext, age_group: AgeGroup) -> list[NarrativeCard]:
    if age_group == AgeGroup.junior:
        return []
    riasec_items = [e for e in context.evidence if e.source_type == "riasec_category"][:3]
    return [
        NarrativeCard(
            title=f"Стоит посмотреть в сторону: {e.text}",
            description=_CAREER_CARD_DESCRIPTION,
            evidence_ids=[e.source_id],
        )
        for e in riasec_items
    ]


def build_fallback_narrative(context: ReportNarrativeContext) -> ReportNarrativeOutput:
    age_group = AgeGroup(context.age_group)
    return ReportNarrativeOutput(
        summary=_summary(age_group),
        strength_cards=_strength_cards(context),
        interests=_interests(context),
        thinking_style_notes=_thinking_style_notes(context),
        motivation_narrative=_motivation_narrative(context),
        career_narrative=_career_narrative(context, age_group),
    )
