"""Per-locale strings for the careers' «Почему тебе подходит»
(`app/services/career_fit_service.py`). Same catalog shape as KZ-307.

A fact reason reuses the vetted «Сильные стороны» card title for the fact
(`student_strengths.cards.*.title`) and the profession's own catalog skill;
only the glue sentence lives here. Subject names come from
`subjects.school_subjects`.
"""

RU = {
    "list_conjunction": " и ",
    # Interest fallback when no concrete reason renders: the RIASEC types
    # above the average for both student and profession, strongest first.
    "summary": "Совпадает с тем, что тебе ближе всего: {items}.",
    # Neither a concrete reason nor a confirmed interest can explain it.
    "summary_general": "Это направление подобрано по общей картине твоих ответов.",
    # One short item per type, no inner «и» / commas — they are listed.
    "letters": {
        "R": "практическая работа",
        "I": "исследование",
        "A": "творчество",
        "S": "помощь людям",
        "E": "инициатива",
        "C": "порядок",
    },
    # Fact wording that replaces the strength card title in a reason: the
    # cross-test titles end with a note on how the fact was confirmed
    # («…и это подтверждается»), which reads odd next to a profession.
    "fact_titles": {
        "cross.lead": "Тебе нравится брать инициативу",
        "cross.order": "Тебе близка упорядоченная работа",
        "cross.research": "Тебе интересно разбираться, как всё устроено",
    },
    "reason_fact_skill": "{fact} — здесь это пригодится: {skill}.",
    # Join the second / third concrete reason into the `why` synthesis.
    # `text` is lower-cased by the renderer and has no trailing full stop.
    "reason_additional": "А ещё {text}.",
    "reason_more": "Кроме того, {text}.",
    "reason_subject_easy": "Тебе легко даётся предмет «{subject}» — в этой профессии он понадобится.",
    "reason_subject_liked": "Тебе нравится предмет «{subject}» — в этой профессии он понадобится.",
    "reason_subject_easy_skill": "Тебе легко даётся предмет «{subject}» — здесь это пригодится: {skill}.",
    "reason_subject_liked_skill": "Тебе нравится предмет «{subject}» — здесь это пригодится: {skill}.",
    "profession_skill": "В этой профессии особенно важно: {skill}.",
    "reason_skill_fallback": (
        "В этой профессии особенно важно: {skill}. По твоим результатам пока недостаточно данных, "
        "чтобы уверенно связать это с твоими сильными сторонами — направление лучше проверить на практике."
    ),
}

KK = {
    "list_conjunction": " және ",
    "summary": "Бұл мамандық саған ең жақын нәрсеге сәйкес келеді: {items}.",
    "summary_general": "Бұл бағыт жауаптарыңның жалпы көрінісі бойынша таңдалды.",
    "letters": {
        "R": "практикалық жұмыс",
        "I": "зерттеу",
        "A": "шығармашылық",
        "S": "адамдарға көмек",
        "E": "бастамашылдық",
        "C": "реттілік",
    },
    "fact_titles": {
        "cross.lead": "Бастама көтеру саған ұнайды",
        "cross.order": "Жүйелі жұмыс саған жақын",
        "cross.research": "Бәрінің қалай құрылғанын түсіну саған қызық",
    },
    "reason_fact_skill": "{fact} — бұл мамандықта мұның мынаған пайдасы тиеді: {skill}.",
    "reason_additional": "Сонымен қатар, {text}.",
    "reason_more": "Оған қоса, {text}.",
    "reason_subject_easy": "«{subject}» пәні саған оңай беріледі — бұл мамандықта ол керек болады.",
    "reason_subject_liked": "Саған «{subject}» пәні ұнайды — бұл мамандықта ол керек болады.",
    "reason_subject_easy_skill": "«{subject}» пәні саған оңай беріледі — бұл мамандықта мұның мынаған пайдасы тиеді: {skill}.",
    "reason_subject_liked_skill": "Саған «{subject}» пәні ұнайды — бұл мамандықта мұның мынаған пайдасы тиеді: {skill}.",
    "profession_skill": "Бұл мамандықта әсіресе маңыздысы: {skill}.",
    "reason_skill_fallback": (
        "Бұл мамандықта әсіресе маңыздысы: {skill}. Әзірге нәтижелерің бойынша мұны күшті жақтарыңмен "
        "нақты байланыстыру қиын — бағытты іс жүзінде байқап көрген дұрыс."
    ),
}
