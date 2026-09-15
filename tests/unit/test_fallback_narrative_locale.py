"""KZ-403 — the deterministic (LLM-free) report narrative in Kazakh.

`build_fallback_narrative(context, locale="kk")` must produce a full, coherent
report that (a) still passes `report_narrative_validator.validate(..., "kk")`
by construction, (b) is actually Kazakh — no Russian-dominant field, and
(c) leaves the `ru` output byte-for-byte unchanged (snapshot).

The label/evidence text interpolated into the templates comes from the KZ-307
accessors, which read `get_locale()`; these tests set it via
`i18n.use_locale("kk")` the same way `report_service._build_narrative`'s
caller does in production.
"""
import pytest

from app import i18n
from app.i18n import use_locale
from app.models.profile import AgeGroup
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.report_narrative_fallback import build_fallback_narrative
from app.services.report_narrative_validator import validate

_KK_CHARS = set("әғқңөұүһі")


def _context(age_group: AgeGroup, instrument: str, evidence: list[EvidenceItem]) -> ReportNarrativeContext:
    return ReportNarrativeContext(age_group=age_group.value, interest_instrument=instrument, evidence=evidence)


def _all_texts(output) -> list[str]:
    texts = [output.summary, output.final_analysis,
             output.motivation_narrative.title, output.motivation_narrative.description]
    for card in output.strength_cards + output.thinking_style_notes + output.career_narrative:
        texts += [card.title, card.description]
    for it in output.interests:
        texts += [it.title, it.description]
    return [t for t in texts if t]


@pytest.fixture(autouse=True)
def _reset_locale():
    i18n._current_locale.set(i18n.DEFAULT_LOCALE)
    yield
    i18n._current_locale.set(i18n.DEFAULT_LOCALE)


def _rich_evidence_kk() -> list[EvidenceItem]:
    # evidence text as the KZ-307 accessors would produce it under kk
    return [
        EvidenceItem(source_id="riasec:R", source_type="riasec_category",
                     text="Қолмен жұмыс істеп, істі нақты нәтижеге жеткізгенді ұнатасың"),
        EvidenceItem(source_id="riasec:I", source_type="riasec_category",
                     text="Мәннің түбіне жетіп, бәрінің қалай құрылғанын түсінгенді ұнатасың"),
        EvidenceItem(source_id="personality:openness", source_type="personality",
                     text="Саған жаңаны сынап көру қызық"),
        EvidenceItem(source_id="thinking_style:creative_think", source_type="thinking_style",
                     text="Саған бір істі жасаудың бірнеше жолын ойлап табу оңай."),
        EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style",
                     text="Саған алдымен нақты рет болғаны ыңғайлы."),
        EvidenceItem(source_id="motivation:interest", source_type="motivation",
                     text="Шынымен қызық іспен айналысу"),
        EvidenceItem(source_id="motivation:creation", source_type="motivation",
                     text="Өзіндік бір нәрсе жасау"),
        EvidenceItem(source_id="subject_liked:Физика", source_type="subject_liked", text="Физика"),
        EvidenceItem(source_id="artifact:1", source_type="artifact", text="Робототехника"),
    ]


@pytest.mark.parametrize("age_group,instrument", [
    (AgeGroup.junior, "mi"),
    (AgeGroup.middle, "riasec"),
    (AgeGroup.senior, "riasec"),
])
def test_kk_fallback_is_valid_by_construction(age_group, instrument):
    ctx = _context(age_group, instrument, [] if age_group == AgeGroup.junior else _rich_evidence_kk())
    with use_locale("kk"):
        out = build_fallback_narrative(ctx, locale="kk")
        assert validate(out, ctx, language="kk") == []


def test_kk_fallback_has_no_russian_dominant_field():
    ctx = _context(AgeGroup.senior, "riasec", _rich_evidence_kk())
    with use_locale("kk"):
        out = build_fallback_narrative(ctx, locale="kk")
    for text in _all_texts(out):
        if len(text) < 15:
            continue
        assert _KK_CHARS & set(text.lower()), f"no Kazakh-specific letters in: {text!r}"


def test_kk_summary_keeps_the_5_to_6_sentence_shape():
    for ag in (AgeGroup.junior, AgeGroup.senior):
        ctx = _context(ag, "riasec", [])
        with use_locale("kk"):
            out = build_fallback_narrative(ctx, locale="kk")
        n = out.summary.count(".") + out.summary.count("!") + out.summary.count("?")
        assert 5 <= n <= 6, (ag, n, out.summary)


def test_kk_placeholders_are_all_filled():
    ctx = _context(AgeGroup.senior, "riasec", _rich_evidence_kk())
    with use_locale("kk"):
        out = build_fallback_narrative(ctx, locale="kk")
    for text in _all_texts(out):
        assert "{" not in text and "}" not in text, f"unfilled placeholder in: {text!r}"
    # career card actually interpolated the direction phrase
    assert any("жеткізгенді ұнатасың" in c.title for c in out.career_narrative)


def test_ru_output_is_unchanged_snapshot():
    """locale=ru must be byte-for-byte what it was before KZ-403."""
    ctx = _context(AgeGroup.senior, "riasec", [
        EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный интерес"),
        EvidenceItem(source_id="thinking_style:creative_think", source_type="thinking_style", text="Идеи."),
        EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Заниматься интересным"),
    ])
    out = build_fallback_narrative(ctx)  # default locale=ru

    assert out.summary.startswith("По твоим ответам заметно, что тебе интересны определённые сферы")
    assert out.motivation_narrative.title == "Что тебя мотивирует"
    assert out.motivation_narrative.description == "Заниматься интересным."
    assert out.career_narrative[0].title == "Стоит посмотреть в сторону: Реалистичный интерес"
    assert out.career_narrative[0].description.startswith("Это направление хорошо совпало")
    assert out.final_analysis.startswith("Если сложить всё вместе: твои интересы показывают, куда тебя тянет")
    assert " и мотивация — что удерживает тебя в деле надолго." in out.final_analysis
    steady = next(i for i in out.interests if i.tier == "steady")
    assert steady.description == (
        "Сейчас это проявляется тише, чем другие сферы — и это нормально: "
        "широкие интересы дают больше вариантов, куда можно посмотреть."
    )
