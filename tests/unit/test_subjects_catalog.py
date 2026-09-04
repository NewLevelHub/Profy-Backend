"""KZ-503 — the school-subject / admission-term catalog.

`school_subjects` is keyed by the canonical Russian subject string the frontend
stores on the profile (`SUBJECT_OPTIONS[].value` in `ProfileSetupPage.tsx`).
The 13 keys are frozen here so a change on either side is caught; the frontend
half is pinned by `Profy-Frontend/scripts/i18n-subjects.mjs`.
"""
from app.i18n import use_locale
from app.i18n.catalog import subjects, tr
from app.prompts._locale import glossary_block

# The exact canonical strings the frontend sends. Do not edit without updating
# `SUBJECT_OPTIONS` in ProfileSetupPage.tsx and `subject.*` in onboarding.json.
_CANONICAL_SUBJECTS = {
    "Математика", "Физика", "Химия", "Биология", "История", "География",
    "Русский язык", "Литература", "Английский язык", "Информатика",
    "Физкультура", "Рисование", "Музыка",
}


def test_ru_and_kk_school_subject_keys_match_and_are_canonical():
    assert set(subjects.RU["school_subjects"]) == _CANONICAL_SUBJECTS
    assert set(subjects.KK["school_subjects"]) == set(subjects.RU["school_subjects"])


def test_ru_school_subject_values_are_identity():
    for key, value in subjects.RU["school_subjects"].items():
        assert value == key


def test_kk_translates_the_subjects_that_differ():
    kk = subjects.KK["school_subjects"]
    assert kk["История"] == "Тарих"
    assert kk["Русский язык"] == "Орыс тілі"
    assert kk["Английский язык"] == "Ағылшын тілі"
    assert kk["Литература"] == "Әдебиет"
    assert kk["Физкультура"] == "Дене шынықтыру"
    assert kk["Рисование"] == "Сурет салу"
    # names that are the same term in both
    assert kk["Математика"] == "Математика"


def test_admission_terms_ent_pair():
    assert subjects.RU["admission_terms"]["ent"] == "ЕНТ"
    assert subjects.KK["admission_terms"]["ent"] == "ҰБТ"
    assert subjects.KK["admission_terms"]["profile_subjects"] == "бейіндік пәндер"
    assert subjects.KK["admission_terms"]["threshold_score"] == "шекті балл"


def test_tr_resolves_by_locale():
    with use_locale("kk"):
        assert tr("subjects")["school_subjects"]["История"] == "Тарих"
    with use_locale("ru"):
        assert tr("subjects")["school_subjects"]["История"] == "История"


def test_ai_glossary_uses_the_catalog_terms():
    """The KZ-401 prompt glossary must not carry its own copy of the ЕНТ/ҰБТ
    pair — it builds from the KZ-503 catalog."""
    block = glossary_block("kk")
    assert subjects.KK["admission_terms"]["ent"] in block
    assert subjects.KK["admission_terms"]["profile_subjects"] in block
    assert subjects.KK["admission_terms"]["threshold_score"] in block
    assert subjects.RU["admission_terms"]["ent"] in block  # "«ЕНТ» орнына «ҰБТ»"
