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
from app.i18n import DEFAULT_LOCALE
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
_PERSONALITY_SYNTHESIS_HINT: dict[str, str] = {
    "openness": "не бояться пробовать непривычные способы",
    "conscientiousness": "доводить начатое до конца, а не бросать на середине",
    "extraversion": "смело предлагать такие идеи вслух, а не держать при себе",
    "agreeableness": "договариваться с другими, если задача общая",
    "emotional_stability": "не сдаваться, если с первого раза не получилось",
}

# TZ_Profi.md §18.2 п.2: each strength card is "короткая формулировка +
# одно предложение объяснения со ссылкой на ответы ребёнка" — the
# formulation (item.text, e.g. "Любишь докапываться до сути и разбираться,
# как всё устроено") is specific enough to BE the title on its own; this
# dict supplies the second sentence, grounding it in how it was observed.
# Previously the card used a generic bucket label ("Тебе интересно"/"Твой
# характер"/...) as the title and the specific phrase as the description —
# backwards from what the LLM path already does, and the reason every
# card of the same source_type looked identically titled.

# Several variants per source_type, cycled deterministically (not random —
# same input always produces the same output) so that 2-3 cards of the same
# source_type (e.g. a student with 3 evidenced RIASEC letters) don't all get
# the literal same explanation sentence — that read as copy-pasted (found
# live: a middle-schooler's report had "Это заметно по тому, какие ответы ты
# выбирал(а) в тесте." verbatim on every riasec_category card).
_STRENGTH_CARD_EXPLANATION_VARIANTS: dict[str, list[str]] = {
    "mi_category": [
        "Это заметно по тому, какие ответы ты выбирал(а) в тесте.",
        "Ты сам(а) показал(а) это своими ответами в тесте.",
        "Это видно из того, как ты отвечал(а) на вопросы теста.",
    ],
    "riasec_category": [
        "Это заметно по тому, какие ответы ты выбирал(а) в тесте.",
        "Ты сам(а) показал(а) это своими ответами в тесте.",
        "Это видно из того, как ты отвечал(а) на вопросы теста.",
    ],
    "personality": [
        "Это видно по тому, как ты отвечаешь на вопросы о себе.",
        "Ты сам(а) описал(а) себя именно так.",
    ],
    # subject_liked/subject_easy/artifact are self-reported at onboarding,
    # not measured by the test (report_narrative_context.
    # ONBOARDING_SOURCE_TYPES) — the explanation says so plainly, so this
    # card doesn't read as if it were part of "what the test found" (that's
    # what also grounds the suggested careers below — mixing them in
    # silently is what made "programming" and "accountant" look like they
    # came from the same evidence when they didn't, user feedback).
    "subject_liked": [
        "Это не из теста — ты сам(а) отметил(а) этот предмет как один из любимых. Можно развивать это отдельно, параллельно.",
        "Ты сам(а) выбрал(а) этот предмет среди тех, что нравятся — само по себе, не как часть теста.",
    ],
    "subject_easy": [
        "Это не из теста — ты сам(а) отметил(а), что этот предмет даётся легко. Стоит развивать это параллельно.",
        "Ты сам(а) сказал(а), что здесь всё получается легко — отдельно от результатов теста.",
    ],
    "artifact": [
        "Это не из теста — ты сам(а) рассказал(а) об этом в своём профиле. Можно развивать это параллельно.",
        "Это ты сам(а) указал(а) в своём профиле — отдельный интерес, не из результатов теста.",
    ],
}
_DEFAULT_STRENGTH_EXPLANATION = "Это видно по твоим ответам."


def _strength_card_explanation(source_type: str, index_within_type: int) -> str:
    variants = _STRENGTH_CARD_EXPLANATION_VARIANTS.get(source_type)
    if not variants:
        return _DEFAULT_STRENGTH_EXPLANATION
    return variants[index_within_type % len(variants)]

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


def _join_ru(items: list[str]) -> str:
    if not items:
        return ""
    if len(items) == 1:
        return items[0]
    return ", ".join(items[:-1]) + " и " + items[-1]


def _summary(age_group: AgeGroup) -> str:
    # TZ_Profi.md §18.2 п.1 wants a short but real summary — 5-6 sentences
    # (product decision, 2026-08-17, up from 3), each adding genuinely new
    # framing rather than repeating a specific claim that already has its
    # own section (strength_cards/interest_map/thinking_style/motivation) —
    # this is the first thing read, so it orients, it doesn't pre-empt.
    # None of these sentences repeat the "не окончательный выбор / карта
    # возможных направлений" idea either — `disclaimer` (app/schemas/
    # result_v2.py, DISCLAIMER) already says that right next to summary on
    # the page (user feedback: repeating it here duplicated that line).
    if age_group == AgeGroup.junior:
        return (
            f"Ты попробовал разные задания, и по ответам видно, чем тебе интересно заниматься. "
            f"Тут не было правильных или неправильных ответов — ты отвечал так, как тебе кажется, "
            f"и это здорово. "
            f"Дальше в отчёте — что у тебя получается лучше всего и что можно попробовать. "
            f"Всё это про тебя, а не про кого-то другого — здесь только твои собственные ответы. "
            f"Пробуй разное и смотри, что нравится тебе больше всего. "
            f"Если что-то откликается — смело занимайся этим ещё больше."
        )
    return (
        f"По твоим ответам заметно, что тебе интересны определённые сферы и есть сильные стороны, на "
        f"которые стоит опереться. "
        f"В тесте не было правильных или неправильных ответов — ты отвечал так, как чувствуешь, и уже "
        f"это само по себе ценная информация о тебе. "
        f"Дальше в отчёте подробно разобрано, что у тебя получается, как ты обычно подходишь к задачам "
        f"и что тебя по-настоящему увлекает. "
        f"Всё это построено на твоих собственных ответах, а не на общих шаблонах — читай это как разговор "
        f"о тебе, а не готовый вердикт. "
        f"Обращай внимание на то, что откликается сильнее всего, и пробуй это на практике. "
        f"Используй отчёт как отправную точку, чтобы самому решить, что хочется исследовать дальше."
    )


def _strength_cards(context: ReportNarrativeContext) -> list[NarrativeCard]:
    # thinking_style/motivation evidence are reserved for their own sections
    # below — excluded here so the same fact never appears twice with
    # identical text.
    pool = [e for e in context.evidence if e.source_type not in STRENGTH_CARD_EXCLUDED_SOURCE_TYPES]
    count = min(7, len(pool))
    type_counters: dict[str, int] = {}
    cards = []
    for item in pool[:count]:
        index_within_type = type_counters.get(item.source_type, 0)
        type_counters[item.source_type] = index_within_type + 1
        cards.append(NarrativeCard(
            title=item.text,
            description=_strength_card_explanation(item.source_type, index_within_type),
            evidence_ids=[item.source_id],
        ))
    return cards


def _interests(context: ReportNarrativeContext) -> list[InterestCard]:
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
            cards.append(InterestCard(category=key, tier="steady", title=label, description=_STEADY_INTEREST_NOTE))
    return cards


def _thinking_style_notes(context: ReportNarrativeContext, age_group: AgeGroup) -> list[NarrativeCard]:
    """One merged card, not one per style — 2 separate cards both titled
    generically "Как тебе легче думать" read as a duplicated/boring section
    (user feedback). Junior gets no abstract style labels or career-adjacent
    "where this shows up" framing (TZ_Profi.md §4.1); middle/senior get a
    named title plus a short real-world-relevance sentence."""
    items = [e for e in context.evidence if e.source_type == "thinking_style"]
    if not items:
        return []
    keys = [e.source_id.split(":", 1)[1] for e in items]
    evidence_ids = [e.source_id for e in items]

    if age_group == AgeGroup.junior:
        clauses = [thinking_style_cue_short()[key] for key in keys]
        description = _join_ru(clauses) + "."
        description = description[0].upper() + description[1:]
        return [NarrativeCard(title="Как тебе легче думать", description=description, evidence_ids=evidence_ids)]

    verb = "близко" if len(keys) == 1 else "близки"
    adjectives = _join_ru([thinking_style_adj()[key] for key in keys])
    title = f"Тебе {verb} {adjectives} мышление"

    cues = " ".join(item.text for item in items)
    impact = _join_ru([thinking_style_impact()[key] for key in keys])
    description = f"{cues} Люди с таким складом ума часто умеют {impact}."

    # New synthesis with one personality trait, not a repeat of "Твой
    # характер" (which shows the trait's own note text verbatim) — see
    # _PERSONALITY_SYNTHESIS_HINT. First high-tier trait found, deterministic
    # (context.evidence order is already fixed by build_report_narrative_context).
    personality_item = next((e for e in context.evidence if e.source_type == "personality"), None)
    if personality_item is not None:
        trait = personality_item.source_id.split(":", 1)[1]
        if trait in _PERSONALITY_SYNTHESIS_HINT and trait in personality_labels():
            label = personality_labels()[trait]
            label = label[0].lower() + label[1:]
            description += f" А твоя {label} помогает {_PERSONALITY_SYNTHESIS_HINT[trait]}."
            evidence_ids = evidence_ids + [personality_item.source_id]

    return [NarrativeCard(title=title, description=description, evidence_ids=evidence_ids)]


def _motivation_narrative(context: ReportNarrativeContext) -> MotivationNarrative:
    items = [e for e in context.evidence if e.source_type == "motivation"]
    if not items:
        return MotivationNarrative(title="Что тебя мотивирует", description=_NO_MOTIVATION_SIGNAL, evidence_ids=[])
    # e.text is now a bare phrase, e.g. "Заниматься тем, что по-настоящему
    # интересно" (motivation_content.highlight_phrases no longer prefixes
    # each one) — lowercase joins into one readable sentence instead of
    # several capitalized fragments run together.
    phrases = [items[0].text] + [e.text[0].lower() + e.text[1:] for e in items[1:]]
    description = _join_ru(phrases) + "."
    return MotivationNarrative(
        title="Что тебя мотивирует",
        description=description,
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


# Shown once, describing what each section *is for* — never the evidence
# text itself (that's already been shown, verbatim, in its own section) —
# so this reads as a synthesis, not a fourth repeat of the same facts.
_FINAL_ANALYSIS_CLAUSES: dict[str, str] = {
    "interests": "твои интересы показывают, куда тебя тянет",
    "personality": "характер — как тебе комфортнее действовать",
    "thinking_style": "стиль мышления — как тебе легче решать задачи",
    "motivation": "мотивация — что удерживает тебя в деле надолго",
}


def _final_analysis(context: ReportNarrativeContext, age_group: AgeGroup) -> str:
    present = []
    if any(e.source_type in ("riasec_category", "mi_category") for e in context.evidence):
        present.append(_FINAL_ANALYSIS_CLAUSES["interests"])
    if any(e.source_type == "personality" for e in context.evidence):
        present.append(_FINAL_ANALYSIS_CLAUSES["personality"])
    if any(e.source_type == "thinking_style" for e in context.evidence):
        present.append(_FINAL_ANALYSIS_CLAUSES["thinking_style"])
    if any(e.source_type == "motivation" for e in context.evidence):
        present.append(_FINAL_ANALYSIS_CLAUSES["motivation"])

    if present:
        first = f"Если сложить всё вместе: {_join_ru(present)}."
    else:
        first = "Каждый раздел этого отчёта — отдельный кусочек общей картины."

    if age_group == AgeGroup.junior:
        return (
            f"{first} Это не разные истории, а разные стороны одного и того же тебя. "
            f"Пробуй то, что откликается сильнее всего, и смотри, что получится."
        )
    return (
        f"{first} Это не отдельные разрозненные факты, а разные стороны одного и того же "
        f"человека — тебя. Используй все эти наблюдения вместе, а не по одному, когда будешь "
        f"решать, что попробовать в первую очередь."
    )


def build_fallback_narrative(
    context: ReportNarrativeContext, *, locale: str = DEFAULT_LOCALE
) -> ReportNarrativeOutput:
    age_group = AgeGroup(context.age_group)
    return ReportNarrativeOutput(
        summary=_summary(age_group),
        strength_cards=_strength_cards(context),
        interests=_interests(context),
        thinking_style_notes=_thinking_style_notes(context, age_group),
        motivation_narrative=_motivation_narrative(context),
        career_narrative=_career_narrative(context, age_group),
        final_analysis=_final_analysis(context, age_group),
    )
