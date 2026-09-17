"""Unit tests for Kazakh language validation guard and retry/fallback (KZ-402)."""
from unittest.mock import AsyncMock, patch
import pytest

from app.models.profile import AgeGroup
from app.schemas.report_narrative import (
    InterestCard,
    MotivationNarrative,
    NarrativeCard,
    ReportNarrativeOutput,
)
from app.schemas.report_narrative_context import EvidenceItem, ReportNarrativeContext
from app.services.report_narrative_service import (
    _correction_message,
    generate_report_narrative,
    metric_counts,
    record_fallback,
    record_language_mismatch,
)
from app.services.report_narrative_validator import (
    ValidationIssue,
    _all_texts,
    _check_language_kk,
    validate,
)

# 10 realistic proforientation text paragraphs in Kazakh
REAL_KAZAKH_PARAGRAPHS: list[str] = [
    "Сенің бойыңда зерттеушілік қабілет пен логикалық ойлау мықты дамыған. "
    "Сен күрделі мәселелерді талдап, олардың түпкі себебін түсінуге тырысасың.",

    "Бұл қасиет саған ғылым, ақпараттық технологиялар немесе инженерия бағытында "
    "үлкен мүмкіндік береді. Жаңа білім алуды жақсы көресің.",

    "Алдағы уақытта практикалық жобалармен айналысып, өз дағдыларыңды шыңдау ұсынылады. "
    "Мектеп қабырғасында профильдік олимпиадаларға қатысып, тәжірибе жинақтау қажет.",

    "Сенің табандылығың мен қызығушылығың болашақта табысты маман болуға көмектеседі. "
    "Командамен жұмыс істеу барысында өз ойыңды еркін жеткізуді үйрену керек.",

    "Жүйелі түрде кітап оқып, кәсіби сала өкілдерінен кеңес алған дұрыс. "
    "Қазіргі таңда цифрлық сауаттылық пен сыни көзқарас ең басты орында тұр.",

    "Математика мен алгоритмдер әлемі саған ерекше шабыт сыйлайды. "
    "Күрделі есептерді шешу арқылы логикалық ойлау қабілетіңді күннен-күнге дамытып келесің.",

    "Шығармашылық идеяларды өмірде қолдану үшін нақты жоспар құрып, соған сай әрекет ету маңызды. "
    "Өз жобаларыңды портфолио түрінде жинақтау болашақта үлкен көмек береді.",

    "Сен адамдармен тез тіл табысып, оларға қолдау көрсетуге әрқашан дайынсың. "
    "Бұл бағыт әлеуметтік салалар мен педагогикада өзіңді көрсетуге мүмкіндік береді.",

    "Өз күшіңе сенімділік пен жауапкершілік сенің басты артықшылығың болып табылады. "
    "Кез келген істі соңына дейін жеткізіп, сапалы нәтижеге қол жеткізуді көздейсің.",

    "Техникалық құрылғылардың қалай жұмыс істейтінін білуге деген құштарлық сені үнемі алға жетелейді. "
    "Үйірмелерге қатысып, практикалық дағдыларды арттыру өте пайдалы болады."
]


def _sample_context() -> ReportNarrativeContext:
    return ReportNarrativeContext(
        age_group=AgeGroup.senior.value,
        interest_instrument="riasec",
        categories=["R", "I"],
        personality_notes={"openness": "любит исследовать"},
        thinking_style_notes={"systematic": "логичен"},
        motivation_notes={"interest": "мастерство"},
        evidence=[
            EvidenceItem(source_id="riasec:R", source_type="riasec_category", text="Реалистичный"),
            EvidenceItem(source_id="riasec:I", source_type="riasec_category", text="Исследовательский"),
            EvidenceItem(source_id="personality:openness", source_type="personality", text="Любознательность"),
            EvidenceItem(source_id="thinking_style:systematic", source_type="thinking_style", text="Аналитичность"),
            EvidenceItem(source_id="motivation:interest", source_type="motivation", text="Мастерство"),
        ],
    )


def _russian_narrative_output() -> ReportNarrativeOutput:
    return ReportNarrativeOutput(
        summary=(
            "У тебя отлично развито аналитическое мышление и способность глубоко погружаться в суть задач. "
            "Ты стремишься к постоянному развитию и любишь находить нестандартные решения. "
            "Твои сильные стороны лежат в области логики, системного анализа и работы с данными. "
            "В будущем эти качества откроют отличные перспективы в сфере инженерии и технологий. "
            "Продолжай развивать свои навыки через участие в профильных проектах и олимпиадах."
        ),
        strength_cards=[
            NarrativeCard(
                title="Аналитический склад ума",
                description="Ты умеешь структурировать информацию и находить неочевидные закономерности в сложных ситуациях.",
                evidence_ids=["personality:openness"],
            )
        ],
        interests=[
            InterestCard(
                category="R",
                title="Реалистический",
                tier="strong",
                description="Интерес к конкретным практическим задачам и техническим инструментам.",
            ),
            InterestCard(
                category="I",
                title="Исследовательский",
                tier="strong",
                description="Любовь к научному поиску, аналитике и логическим экспериментам.",
            ),
            InterestCard(
                category="A",
                title="Артистический",
                tier="steady",
                description="Интерес к творчеству и самовыражению.",
            ),
            InterestCard(
                category="S",
                title="Социальный",
                tier="steady",
                description="Взаимодействие с людьми и помощь другим.",
            ),
            InterestCard(
                category="E",
                title="Предприимчивый",
                tier="steady",
                description="Лидерство, управление и проектная деятельность.",
            ),
            InterestCard(
                category="C",
                title="Конвенциональный",
                tier="steady",
                description="Работа с четкими инструкциями, правилами и регламентами.",
            ),
        ],
        thinking_style_notes=[
            NarrativeCard(
                title="Системное мышление",
                description="Опирается на логический анализ и проверку гипотез перед принятием решений.",
                evidence_ids=["thinking_style:systematic"],
            )
        ],
        motivation_narrative=MotivationNarrative(
            title="Стремление к мастерству",
            description="Тебя мотивирует глубокое понимание своего дела и постоянный профессиональный рост.",
            evidence_ids=["motivation:interest"],
        ),
        career_narrative=[
            NarrativeCard(
                title="Инженер-аналитик",
                description="Специалист, сочетающий технические компетенции и аналитические методы исследования.",
                evidence_ids=["riasec:R"],
            )
        ],
        final_analysis=(
            "Сочетание исследовательского интереса и системного стиля мышления даёт сильную базу. "
            "Твоя внутренняя мотивация к мастерству помогает доводить начатые проекты до конца. "
            "Рекомендуется сосредоточиться на углубленном изучении профильных дисциплин."
        ),
    )


# ─── 1. Detection of Russian text when expecting Kazakh ───────────────────────


def test_russian_text_detected_as_language_mismatch_on_kk():
    output = _russian_narrative_output()
    context = _sample_context()

    issues = validate(output, context, language="kk")
    mismatch_issues = [i for i in issues if i.code == "LANGUAGE_MISMATCH"]
    assert len(mismatch_issues) >= 1
    assert "LANGUAGE_MISMATCH" in [i.code for i in issues]


def test_russian_snippets_fail_kk_check():
    ru_snippets = [
        "У тебя отлично развито логическое мышление и аналитический склад ума.",
        "Ты любишь структурировать данные и докапываться до сути происходящего.",
        "Это качество открывает широкие возможности в IT, инженерии и науке.",
        "Тебе нравится самостоятельно разбираться в сложных задачах и алгоритмах.",
    ]
    for snippet in ru_snippets:
        issues = _check_language_kk([snippet])
        assert any(i.code == "LANGUAGE_MISMATCH" for i in issues), f"Failed to catch Russian snippet: {snippet}"


# ─── 2. Authentic Kazakh text passes without false positive ───────────────────


def test_authentic_kazakh_paragraphs_pass_without_false_positive():
    assert len(REAL_KAZAKH_PARAGRAPHS) >= 10
    for idx, paragraph in enumerate(REAL_KAZAKH_PARAGRAPHS):
        issues = _check_language_kk([paragraph])
        assert not issues, f"False positive on real Kazakh paragraph [{idx}]: {paragraph} -> issues: {issues}"


def test_complete_kazakh_response_passes_language_check():
    # Synthetic complete narrative in Kazakh
    kk_texts = [
        REAL_KAZAKH_PARAGRAPHS[0],
        REAL_KAZAKH_PARAGRAPHS[1],
        REAL_KAZAKH_PARAGRAPHS[2],
        "Зерттеушілік дағды",
        REAL_KAZAKH_PARAGRAPHS[3],
        "Ақпараттық технологиялар",
        REAL_KAZAKH_PARAGRAPHS[4],
    ]
    issues = _check_language_kk(kk_texts)
    assert not issues


# ─── 3. Localized Correction Messages ─────────────────────────────────────────


def test_correction_message_localized_in_kazakh():
    issues = [ValidationIssue("LANGUAGE_MISMATCH", "детали")]
    msg_kk = _correction_message(issues, language="kk")
    assert "Алдыңғы жауабың тексеруден өтпеді" in msg_kk
    assert "Жауап орыс тілінде берілген" in msg_kk
    assert "ә, ғ, қ, ң, ө, ұ, ү, һ, і" in msg_kk

    msg_ru = _correction_message(issues, language="ru")
    assert "Твой предыдущий ответ не прошёл проверку" in msg_ru
    assert "Ответ дан не на том языке" in msg_ru


# ─── 4. Persistent mismatch triggers fallback and metrics ─────────────────────


@pytest.mark.asyncio
async def test_persistent_language_mismatch_triggers_fallback_and_metrics():
    context = _sample_context()
    russian_dict = _russian_narrative_output().model_dump()

    with patch("app.services.llm_client.is_enabled", return_value=True), \
         patch("app.services.llm_client.complete_json", AsyncMock(return_value=russian_dict)):
        output, is_ai = await generate_report_narrative(context, language="kk")

    # When LLM persistently returns Russian, user must get fallback, not Russian AI text
    assert is_ai is False
    assert output is not None

    # Check metrics
    counts = metric_counts()
    assert counts.get("llm.language_mismatch:locale=kk", 0) >= 1
    assert counts.get("llm.fallback:reason=language", 0) >= 1


# ─── 5. Regression: Russian mode behavior unchanged ───────────────────────────


def test_russian_mode_behavior_unchanged():
    output = _russian_narrative_output()
    context = _sample_context()

    # In Russian mode, Russian text has NO language issues
    issues_ru = validate(output, context, language="ru")
    language_issues = [i for i in issues_ru if i.code in ("language", "LANGUAGE_MISMATCH")]
    assert len(language_issues) == 0

    # Non-cyrillic text (e.g. English) in Russian mode still produces "language" code
    english_output = _russian_narrative_output()
    english_output.summary = (
        "This is an English summary that contains absolutely no cyrillic letters whatsoever."
    )
    issues_en = validate(english_output, context, language="ru")
    assert any(i.code == "language" for i in issues_en)
    assert not any(i.code == "LANGUAGE_MISMATCH" for i in issues_en)


# ─── 6. Kazakh quality guards, not just the language check (review finding) ────


def _kk_output(*, summary: str, final_analysis: str,
               card_title: str = "Зерттеушілік ойлау",
               card_desc: str = "Сен күрделі мәселелерді талдап, түпкі себебін түсінуге тырысасың.") -> ReportNarrativeOutput:
    base = _russian_narrative_output()
    base.summary = summary
    base.final_analysis = final_analysis
    base.strength_cards = [NarrativeCard(title=card_title, description=card_desc,
                                         evidence_ids=["personality:openness"])]
    base.interests = [
        InterestCard(category="R", title="Реалистік", tier="strong",
                     description="Нақты практикалық міндеттер мен техникалық құралдарға қызығушылық."),
        InterestCard(category="I", title="Зерттеушілік", tier="strong",
                     description="Ғылыми ізденіс пен логикалық талдауды ұнату."),
        InterestCard(category="A", title="Артистік", tier="steady",
                     description="Шығармашылық пен өзін көрсетуге қызығушылық."),
        InterestCard(category="S", title="Әлеуметтік", tier="steady",
                     description="Адамдармен қарым-қатынас пен көмек."),
        InterestCard(category="E", title="Кәсіпкерлік", tier="steady",
                     description="Бастама көтеру мен ұйымдастыру."),
        InterestCard(category="C", title="Конвенциялық", tier="steady",
                     description="Ретпен, деректермен жұмыс."),
    ]
    base.thinking_style_notes = [NarrativeCard(
        title="Саған жүйелі ойлау жақын",
        description="Сен алдымен нақты рет құрып, сосын іске кірісесің; осындай "
                    "адамдар күрделі істерде тәртіп орната алады.",
        evidence_ids=["thinking_style:systematic"],
    )]
    base.motivation_narrative = MotivationNarrative(
        title="Сені не қозғайды",
        description="Іске деген қызығушылық пен жаңаны ашу.",
        evidence_ids=["motivation:interest"],
    )
    base.career_narrative = []
    return base


_KK_SUMMARY_OK = (
    "Жауаптарыңнан белгілі бір салалар саған қызық екені байқалады. "
    "Тестте дұрыс не бұрыс жауап болмады — өзің сезінгендей жауап бердің. "
    "Есептің әрі қарайғы бөлігінде саған не жақсы шығатыны талданған. "
    "Мұның бәрі сенің өз жауаптарыңа сүйеніп жасалған. "
    "Ең қатты жаныңа жақын нәрсеге назар аудар да, тәжірибеде байқап көр. "
    "Есепті бастау нүктесі ретінде пайдалан."
)
_KK_FINAL_OK = (
    "Бәрін біріктірсек: қызығушылықтарың сені қайда тартатынын көрсетеді. "
    "Бұл бөлек фактілер емес, бір ғана сенің әртүрлі қырларың. "
    "Байқауларды бөлек емес, бәрін бірге пайдалан."
)


def test_kazakh_condescending_phrase_is_flagged():
    out = _kk_output(
        summary=_KK_SUMMARY_OK,
        final_analysis=_KK_FINAL_OK,
        card_desc="Өкінішке орай, бұл мамандық саған арналмаған, басқасын таңдаған дұрыс.",
    )
    issues = validate(out, _sample_context(), language="kk")
    assert any(i.code == "banned_phrase" for i in issues), issues


def test_kazakh_junior_career_term_is_flagged():
    ctx = ReportNarrativeContext(
        age_group=AgeGroup.junior.value, interest_instrument="mi",
        categories=[], evidence=[],
    )
    out = _kk_output(
        summary=_KK_SUMMARY_OK.replace("салалар", "мамандықтар және емтихан"),
        final_analysis=_KK_FINAL_OK,
    )
    issues = validate(out, ctx, language="kk")
    assert any(i.code == "junior_career_term" for i in issues), issues


def test_kazakh_disclaimer_paraphrase_is_flagged():
    out = _kk_output(
        summary=_KK_SUMMARY_OK + " Бұл түпкілікті таңдау емес, тек мүмкін бағыттардың картасы.",
        final_analysis=_KK_FINAL_OK,
    )
    issues = validate(out, _sample_context(), language="kk")
    assert any(i.code == "summary_duplicates_disclaimer" for i in issues), issues


def test_kazakh_card_with_allowed_latin_proper_nouns_is_not_language_mismatch():
    """Review finding: a mostly-Kazakh card citing 'Nazarbayev University' /
    'Data Engineer' must not trip the Cyrillic-ratio check (step 1)."""
    kk_with_latin = [
        "Nazarbayev University-де оқуды жалғастырып, кейін Data Engineer "
        "мамандығын игеруге болады — бұл саған қызық сала.",
        "DevOps және IT бағытында тәжірибе жинақтап, жобаларға қатыс.",
    ]
    assert _check_language_kk(kk_with_latin) == []


def test_actually_english_text_still_flagged_despite_allowlist():
    english = [
        "You are good at solving abstract problems and analysing complex "
        "systems, and you enjoy scientific research and logical experiments.",
    ]
    issues = _check_language_kk(english)
    assert issues and issues[0].code == "LANGUAGE_MISMATCH"


def test_ru_banned_vocab_unaffected_by_kk_additions():
    """The kk sets are additive — ru validation must be byte-identical."""
    out = _russian_narrative_output()
    out.strength_cards = [NarrativeCard(
        title="Тест", description="Это твоя слабая сторона, тебе не подходит эта профессия.",
        evidence_ids=["personality:openness"],
    )]
    issues = validate(out, _sample_context(), language="ru")
    assert sum(1 for i in issues if i.code == "banned_phrase") >= 2
