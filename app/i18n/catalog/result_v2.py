"""Per-locale strings for the deterministic result_v2 assembler
(`app/services/report_v2_assembler.py`) — the synthesis sentences it composes
without the LLM: interest-map note, personality note, career "why", and the
flat-profile artifact addendum (KZ-403). Same catalog shape as KZ-307.

`RU` reproduces the pre-KZ-403 literals byte-for-byte. Templates carry
`{spheres}` / `{traits}` / `{strengths}` / `{skill}` placeholders filled at
the call site; the sphere/trait/strength names interpolated in come from the
KZ-307 label accessors, which the caller runs under `i18n.use_locale(locale)`.
"""

RU = {
    "list_conjunction": " и ",
    # Fixed, server-authored framing lines (no personalization, never LLM).
    # These RU values MUST stay byte-for-byte equal to DISCLAIMER /
    # EXPLORATION_CLOSING_NOTE in app/schemas/result_v2.py — the schema still
    # carries them as field defaults; the assembler now fills the field from
    # here so `kk` reports get the `kk` text (KZ-403 gap, was always ru).
    "disclaimer": (
        "Это не окончательный выбор, а карта возможных направлений — со временем "
        "картина может измениться, и это нормально."
    ),
    "exploration_note": (
        "Не обязательно пробовать всё сразу — начни с того, что откликается "
        "больше всего. Даже маленький шаг сегодня помогает лучше понять, что "
        "тебе действительно нравится."
    ),
    "flat_profile_artifact_note": (
        " Отдельно ты рассказал(а) о своих увлечениях в профиле — когда баллы "
        "по разным сферам близки друг к другу, как сейчас, эти увлечения могут "
        "точнее говорить о твоих склонностях, чем сам тест. Стоит присмотреться "
        "и к направлениям, связанным с ними, даже если их нет в списке ниже."
    ),
    "interest_map_note_high": "Ярко выражено: {spheres}. Остальные сферы проявляются тише — и это нормально.",
    "interest_map_note_medium": (
        "Заметнее всего проявляется: {spheres} — без резких пиков, "
        "интересы распределены довольно ровно."
    ),
    "interest_map_note_flat": (
        "Пока сложно выделить одну явно ведущую сферу — интересы распределены "
        "довольно ровно, и это нормально: есть время присмотреться к разным направлениям."
    ),
    "personality_note_high": (
        "Ярко выражено: {traits} — это то, что тебе, скорее всего, "
        "даётся естественнее всего."
    ),
    "personality_note_low": "Есть, над чем интересно поработать: {traits}.",
    "personality_note_balanced": (
        "Черты характера выражены сбалансированно, без одной резко доминирующей — "
        "и это нормально, у характера не обязательно должна быть одна главная черта."
    ),
    "career_why_match": "Совпадает с тем, что у тебя выражено: {strengths}.",
    "career_why_skill_matched": " Именно здесь особенно пригодится: {skill}.",
    "career_why_skill_neutral": " В этой сфере особенно ценится: {skill}.",
}

KK = {
    "list_conjunction": " және ",
    # LLM-primary translation, pending native review (KZ-403). Keeps the
    # "not a final choice / a map of possible directions" framing whose
    # substrings report_narrative_validator._FRAME_PHRASE_SUBSTRINGS_KK checks.
    "disclaimer": (
        "Бұл түпкілікті таңдау емес, тек мүмкін бағыттардың картасы — уақыт өте "
        "келе көрініс өзгеруі мүмкін, және бұл қалыпты жағдай."
    ),
    "exploration_note": (
        "Бәрін бірден байқап көру міндетті емес — ең қатты қызықтыратыннан баста. "
        "Бүгін жасалған кішкентай қадам да саған не ұнайтынын жақсырақ түсінуге "
        "көмектеседі."
    ),
    "flat_profile_artifact_note": (
        " Профиліңде әуестенетін істерің туралы бөлек айттың — қазіргідей түрлі салалардың "
        "балдары бір-біріне жақын болғанда, бұл істер сенің бейімділіктерің "
        "туралы тестке қарағанда дәлірек айта алады. Төмендегі тізімде болмаса да, "
        "солармен байланысты бағыттарға да назар аударған жөн."
    ),
    "interest_map_note_high": (
        "Айқын байқалады: {spheres}. Қалған салалар бәсеңдеу байқалады — бұл қалыпты жағдай."
    ),
    "interest_map_note_medium": (
        "Ең байқалатыны: {spheres} — күрт шыңдарсыз, қызығушылықтар біркелкі бөлінген."
    ),
    "interest_map_note_flat": (
        "Әзірге бір айқын жетекші саланы бөліп көрсету қиын — қызығушылықтар біркелкі "
        "бөлінген, бұл қалыпты: түрлі бағыттарға назар аударуға уақыт бар."
    ),
    "personality_note_high": (
        "Айқын байқалады: {traits} — бұл саған, сірә, ең табиғи түрде беріледі."
    ),
    "personality_note_low": "Дамытуға қызық тұстар бар: {traits}.",
    "personality_note_balanced": (
        "Мінез қасиеттерің біркелкі байқалады, біреуі күрт басым емес — бұл қалыпты, "
        "мінезде бір басты белгі болуы міндетті емес."
    ),
    "career_why_match": "Сенде айқын байқалатынмен сәйкес келеді: {strengths}.",
    "career_why_skill_matched": " Дәл осы жерде әсіресе қажет болады: {skill}.",
    "career_why_skill_neutral": " Бұл салада ерекше бағаланады: {skill}.",
}
