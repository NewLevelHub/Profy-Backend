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

Localization (KZ-403): every phrase lives in `app/i18n/catalog/narrative_fallback.py`
as identical-shape `RU` / `KK` trees. `build_fallback_narrative` takes an
explicit `locale` (the artifact owner's `users.locale`, not the reader's
request locale — see i18n.use_locale) and resolves the tree once via
`catalog.tr()`; every helper takes that resolved `t` dict. The evidence text
and label values interpolated here come from the KZ-307 accessors, which the
caller (report_service._build_narrative) runs under `use_locale(locale)`, so
they are already in the same language.
"""
from typing import Any

from app.i18n import DEFAULT_LOCALE
from app.i18n.catalog import tr
from app.models.profile import AgeGroup
from app.schemas.report_narrative import (
    InterestCard,
    MotivationNarrative,
    NarrativeCard,
    ReportNarrativeOutput,
)
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.bigfive_content import personality_labels
from app.services.mi_content import mi_labels
from app.services.report_narrative_context import STRENGTH_CARD_EXCLUDED_SOURCE_TYPES
from app.services.riasec_content import riasec_labels
from app.services.thinking_style_content import (
    thinking_style_adj,
    thinking_style_cue_short,
    thinking_style_impact,
)

# middle/senior only — a short "helps to..." clause per Big Five trait, used
# to synthesize thinking_style_notes with personality WITHOUT quoting the
# trait's own note text (that's already shown verbatim in "Твой характер" —
# report_v2_assembler.build_personality_notes). New wording, not a repeat.
# Text now in catalog: narrative_fallback["personality_synthesis_hint"].

# TZ_Profi.md §18.2 п.2: each strength card is "короткая формулировка +
# одно предложение объяснения со ссылкой на ответы ребёнка" — the
# formulation (item.text) is specific enough to BE the title on its own;
# narrative_fallback["strength_explanation_variants"] supplies the second
# sentence, grounding it in how it was observed. Several variants per
# source_type, cycled deterministically (same input -> same output) so 2-3
# cards of the same source_type don't all get the identical explanation.


def _strength_card_explanation(t: dict[str, Any], source_type: str, index_within_type: int) -> str:
    variants = t["strength_explanation_variants"].get(source_type)
    if not variants:
        return t["default_strength_explanation"]
    return variants[index_within_type % len(variants)]


def _join(t: dict[str, Any], items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + t["list_conjunction"] + items[-1]


def _summary(t: dict[str, Any], age_group: AgeGroup) -> str:
    # TZ_Profi.md §18.2 п.1 wants a short but real summary — 5-6 sentences
    # (product decision, 2026-08-17), each adding genuinely new framing
    # rather than repeating a claim that already has its own section. None
    # repeat the "не окончательный выбор / карта возможных направлений" idea
    # — `disclaimer` (result_v2.py DISCLAIMER) already says that next to it.
    if age_group == AgeGroup.junior:
        return t["summary_junior"]
    return t["summary_middle_senior"]


def _strength_cards(t: dict[str, Any], context: ReportNarrativeContext) -> list[NarrativeCard]:
    # thinking_style/motivation/personality evidence are reserved for their
    # own sections — excluded here so the same fact never appears twice.
    pool = [e for e in context.evidence if e.source_type not in STRENGTH_CARD_EXCLUDED_SOURCE_TYPES]
    count = min(7, len(pool))
    type_counters: dict[str, int] = {}
    cards = []
    for item in pool[:count]:
        index_within_type = type_counters.get(item.source_type, 0)
        type_counters[item.source_type] = index_within_type + 1
        cards.append(NarrativeCard(
            title=item.text,
            description=_strength_card_explanation(t, item.source_type, index_within_type),
            evidence_ids=[item.source_id],
        ))
    return cards


def _interests(t: dict[str, Any], context: ReportNarrativeContext) -> list[InterestCard]:
    is_mi = context.interest_instrument == "mi"
    labels = mi_labels() if is_mi else riasec_labels()
    source_type = "mi_category" if is_mi else "riasec_category"
    strong: dict[str, EvidenceItem] = {
        e.source_id.split(":", 1)[1]: e for e in context.evidence if e.source_type == source_type
    }
    cards = []
    for key, label in labels.items():
        if key in strong:
            cards.append(InterestCard(category=key, tier="strong", title=label, description=strong[key].text))
        else:
            cards.append(InterestCard(category=key, tier="steady", title=label, description=t["steady_interest_note"]))
    return cards


def _thinking_style_notes(
    t: dict[str, Any], context: ReportNarrativeContext, age_group: AgeGroup
) -> list[NarrativeCard]:
    """One merged card, not one per style — 2 separate cards both titled
    generically read as a duplicated section (user feedback). Junior gets no
    abstract style labels or career-adjacent framing (TZ_Profi.md §4.1);
    middle/senior get a named title plus a short real-world-relevance
    sentence."""
    items = [e for e in context.evidence if e.source_type == "thinking_style"]
    if not items:
        return []
    keys = [e.source_id.split(":", 1)[1] for e in items]
    evidence_ids = [e.source_id for e in items]

    if age_group == AgeGroup.junior:
        clauses = [thinking_style_cue_short()[key] for key in keys]
        description = _join(t, clauses) + "."
        description = description[0].upper() + description[1:]
        return [NarrativeCard(title=t["thinking_style_junior_title"], description=description, evidence_ids=evidence_ids)]

    verb = t["thinking_style_verb_singular"] if len(keys) == 1 else t["thinking_style_verb_plural"]
    adjectives = _join(t, [thinking_style_adj()[key] for key in keys])
    title = t["thinking_style_title"].format(verb=verb, adjectives=adjectives)

    cues = " ".join(item.text for item in items)
    impact = _join(t, [thinking_style_impact()[key] for key in keys])
    description = t["thinking_style_description"].format(cues=cues, impact=impact)

    # New synthesis with one personality trait, not a repeat of "Твой
    # характер". First high-tier trait found, deterministic (evidence order
    # is fixed by build_report_narrative_context).
    personality_item = next((e for e in context.evidence if e.source_type == "personality"), None)
    if personality_item is not None:
        trait = personality_item.source_id.split(":", 1)[1]
        hints = t["personality_synthesis_hint"]
        if trait in hints and trait in personality_labels():
            label = personality_labels()[trait]
            label = label[0].lower() + label[1:]
            description += t["thinking_style_personality_synthesis"].format(label=label, hint=hints[trait])
            evidence_ids = evidence_ids + [personality_item.source_id]

    return [NarrativeCard(title=title, description=description, evidence_ids=evidence_ids)]


def _motivation_narrative(t: dict[str, Any], context: ReportNarrativeContext) -> MotivationNarrative:
    items = [e for e in context.evidence if e.source_type == "motivation"]
    if not items:
        return MotivationNarrative(title=t["motivation_title"], description=t["no_motivation_signal"], evidence_ids=[])
    # e.text is a bare phrase (highlight_phrases no longer prefixes each) —
    # lowercase the tail so they join into one readable sentence.
    phrases = [items[0].text] + [e.text[0].lower() + e.text[1:] for e in items[1:]]
    description = _join(t, phrases) + "."
    return MotivationNarrative(
        title=t["motivation_title"],
        description=description,
        evidence_ids=[e.source_id for e in items],
    )


def _career_narrative(
    t: dict[str, Any], context: ReportNarrativeContext, age_group: AgeGroup
) -> list[NarrativeCard]:
    if age_group == AgeGroup.junior:
        return []
    riasec_items = [e for e in context.evidence if e.source_type == "riasec_category"][:3]
    return [
        NarrativeCard(
            title=t["career_card_title"].format(name=e.text),
            description=t["career_card_description"],
            evidence_ids=[e.source_id],
        )
        for e in riasec_items
    ]


def _final_analysis(t: dict[str, Any], context: ReportNarrativeContext, age_group: AgeGroup) -> str:
    # Shown once, describing what each section *is for* — never the evidence
    # text itself — so this reads as a synthesis, not a fourth repeat.
    clauses = t["final_analysis_clauses"]
    present = []
    if any(e.source_type in ("riasec_category", "mi_category") for e in context.evidence):
        present.append(clauses["interests"])
    if any(e.source_type == "personality" for e in context.evidence):
        present.append(clauses["personality"])
    if any(e.source_type == "thinking_style" for e in context.evidence):
        present.append(clauses["thinking_style"])
    if any(e.source_type == "motivation" for e in context.evidence):
        present.append(clauses["motivation"])

    if present:
        first = t["final_analysis_prefix"].format(clauses=_join(t, present))
    else:
        first = t["final_analysis_no_signal"]

    if age_group == AgeGroup.junior:
        return first + t["final_analysis_junior_suffix"]
    return first + t["final_analysis_middle_senior_suffix"]


def build_fallback_narrative(
    context: ReportNarrativeContext, *, locale: str = DEFAULT_LOCALE
) -> ReportNarrativeOutput:
    t = tr("narrative_fallback", locale=locale)
    age_group = AgeGroup(context.age_group)
    return ReportNarrativeOutput(
        summary=_summary(t, age_group),
        strength_cards=_strength_cards(t, context),
        interests=_interests(t, context),
        thinking_style_notes=_thinking_style_notes(t, context, age_group),
        motivation_narrative=_motivation_narrative(t, context),
        career_narrative=_career_narrative(t, context, age_group),
        final_analysis=_final_analysis(t, context, age_group),
    )
