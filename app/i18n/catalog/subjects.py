"""School-subject names + admission-campaign terms, per locale (KZ-503).

`school_subjects` is keyed by the **canonical Russian subject string** — the
exact value the frontend stores on `profiles.subjects_liked` / `subjects_easy`
(`SUBJECT_OPTIONS[].value` in `ProfileSetupPage.tsx`, display code `subject.*`
in `onboarding.json`). That Russian string is the locale-independent join key;
this table only resolves it to a display name. The 13 keys here MUST stay in
sync with the frontend list — `Profy-Frontend/scripts/i18n-subjects.mjs` and
`tests/unit/test_subjects_catalog.py` pin both sides.

`admission_terms` is the single backend home for the ЕНТ/ҰБТ terminology pair
(contract §12). `app/prompts/_locale.py::glossary_block` builds the AI-prompt
glossary from it, so the prompt rule and any user-facing use never drift.
"""

RU = {
    "school_subjects": {
        "Математика": "Математика",
        "Физика": "Физика",
        "Химия": "Химия",
        "Биология": "Биология",
        "История": "История",
        "География": "География",
        "Русский язык": "Русский язык",
        "Литература": "Литература",
        "Английский язык": "Английский язык",
        "Информатика": "Информатика",
        "Физкультура": "Физкультура",
        "Рисование": "Рисование",
        "Музыка": "Музыка",
    },
    "admission_terms": {
        "ent": "ЕНТ",
        "profile_subjects": "профильные предметы",
        "threshold_score": "пороговый балл",
        "creative_exam": "творческий экзамен",
    },
}

KK = {
    "school_subjects": {
        "Математика": "Математика",
        "Физика": "Физика",
        "Химия": "Химия",
        "Биология": "Биология",
        "История": "Тарих",
        "География": "География",
        "Русский язык": "Орыс тілі",
        "Литература": "Әдебиет",
        "Английский язык": "Ағылшын тілі",
        "Информатика": "Информатика",
        "Физкультура": "Дене шынықтыру",
        "Рисование": "Сурет салу",
        "Музыка": "Музыка",
    },
    "admission_terms": {
        "ent": "ҰБТ",
        "profile_subjects": "бейіндік пәндер",
        "threshold_score": "шектік балл",
        "creative_exam": "шығармашылық емтихан",
    },
}
