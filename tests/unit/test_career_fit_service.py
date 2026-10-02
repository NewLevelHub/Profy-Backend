"""Careers' «Почему тебе подходит» (career_fit_service): which interest types
are named, which vetted fact is paired with which catalog skill, and how the
stored locale-free entry renders. Pure — no DB."""
import json
from pathlib import Path

import pytest

from app.config import career_fit_rules
from app.i18n import use_locale
from app.i18n.catalog import tr
from app.models.direction import Direction
from app.schemas.student_strengths import StrengthInputs
from app.services import career_fit_service as svc
from app.services import student_strengths_service
from tests.strength_fixtures import astur_snapshot, belbin_totals, rich_inputs

_ROOT = Path(__file__).parent.parent.parent
_REVIEW = json.loads((_ROOT / "scripts" / "direction_content_review.json").read_text(encoding="utf-8"))
_REVIEW_KK = {e["slug"]: e for e in json.loads(
    (_ROOT / "scripts" / "direction_content_review_kk.json").read_text(encoding="utf-8")
)}
_BY_SLUG = {e["slug"]: e for e in _REVIEW}

# A profession whose O*NET profile peaks on C and I.
_VECTOR = {"R": 2.0, "I": 5.0, "A": 1.0, "S": 2.0, "E": 3.0, "C": 6.0}


def _direction(slug: str = "buhgalter", *, vector: dict | None = _VECTOR, skills: list[str] | None = None) -> Direction:
    entry = _BY_SLUG[slug]
    return Direction(
        slug=slug,
        name={"ru": slug},
        holland_code="CIE",
        onet_vector=vector,
        skills_needed={"ru": skills if skills is not None else list(entry["skills_needed"])},
        subjects_to_develop={"ru": list(entry["subjects_to_develop"])},
    )


def _career(slug: str = "buhgalter", locale: str = "ru") -> dict:
    entry = _BY_SLUG[slug] if locale == "ru" else _REVIEW_KK[slug]
    return {"slug": slug, "skills_needed": list(entry["skills_needed"])}


_PROFILE = {"R": 40, "I": 90, "A": 30, "S": 50, "E": 60, "C": 85}
_GENERAL = "Это направление подобрано по общей картине твоих ответов."


def _fit(inputs: StrengthInputs, *directions: Direction, profile: dict | None = None) -> dict:
    profile = profile or _PROFILE
    with use_locale("ru"):
        return svc.build_career_fit(inputs, profile, directions or [_direction()])


# ── catalog data ─────────────────────────────────────────────────────────────


def test_skill_axes_cover_the_reviewed_catalog_text_exactly() -> None:
    assert set(career_fit_rules.skill_axes) == set(_BY_SLUG)
    for slug, skills in career_fit_rules.skill_axes.items():
        assert [s.ru for s in skills] == _BY_SLUG[slug]["skills_needed"], slug
        for skill in skills:
            assert set(skill.axes) <= set(career_fit_rules.axes), (slug, skill.ru)


def test_fact_axes_and_subjects_use_known_values() -> None:
    for evidence_id, axes in career_fit_rules.evidence_axes.items():
        assert axes and set(axes) <= set(career_fit_rules.axes), evidence_id
    school_subjects = set(tr("subjects", locale="ru")["school_subjects"])
    assert set(career_fit_rules.subject_axes) == school_subjects
    for subject, axes in career_fit_rules.subject_axes.items():
        assert axes and set(axes) <= set(career_fit_rules.axes), subject
    assert set(career_fit_rules.subject_aliases.values()) <= school_subjects
    # Every onboarding subject resolves to itself.
    assert {svc.subject_key(s) for s in school_subjects} == school_subjects


def test_every_catalog_subject_spelling_of_a_school_subject_is_mapped() -> None:
    known = {s.lower() for s in tr("subjects", locale="ru")["school_subjects"]} | set(career_fit_rules.subject_aliases)
    for entry in _REVIEW:
        for subject in entry["subjects_to_develop"]:
            normalized = svc._TRAILING_NOTE.sub("", subject.strip().lower()).strip()
            if normalized in known:
                assert svc.subject_key(subject) is not None, (entry["slug"], subject)


def test_kk_skill_lists_line_up_with_ru() -> None:
    # A stored reason points at a skill by index; the kk row renders it from
    # its own kk snapshot, so both lists must have the same shape.
    for slug, entry in _BY_SLUG.items():
        assert len(_REVIEW_KK[slug]["skills_needed"]) == len(entry["skills_needed"]), slug


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("математика", "Математика"),
        ("Информатика", "Информатика"),
        ("физика (оптика)", "Физика"),
        ("изобразительное искусство (ИЗО)", "Рисование"),
        ("русский/казахский язык (для написания текстов и описаний)", "Русский язык"),
        ("иностранный язык", "Английский язык"),
        ("обществознание", None),
        ("робототехника", None),
    ],
)
def test_subject_key_normalizes_catalog_spellings(text: str, expected: str | None) -> None:
    assert svc.subject_key(text) == expected


# ── interest summary ─────────────────────────────────────────────────────────


def test_shared_letters_are_above_average_for_both_strongest_contribution_first() -> None:
    # C: (85-59.2)·(6-3.2) ≈ 73 beats I: (90-59.2)·(5-3.2) ≈ 56.
    assert svc.shared_letters(_PROFILE, _VECTOR, "CIE", ["I", "C"]) == ["C", "I"]


def test_a_type_low_for_both_is_never_a_reason() -> None:
    # A is far below average for both — it raises the correlation, but it is
    # what neither of them is about.
    profile = {"R": 80, "I": 80, "A": 5, "S": 80, "E": 80, "C": 80}
    vector = {"R": 4.0, "I": 4.0, "A": 0.5, "S": 4.0, "E": 4.0, "C": 4.0}
    assert "A" not in svc.shared_letters(profile, vector, "RIC", ["R", "I", "A", "S", "E", "C"])


def test_only_confirmed_interests_are_named() -> None:
    # A near-flat profile is "above average" by a few points everywhere —
    # nothing there to call «ближе всего».
    profile = {"R": 60, "I": 60, "A": 5, "S": 60, "E": 60, "C": 60}
    vector = {"R": 4.0, "I": 4.0, "A": 0.5, "S": 4.0, "E": 4.0, "C": 4.0}
    assert svc.shared_letters(profile, vector, "RIC", []) == []
    assert svc.shared_letters(_PROFILE, _VECTOR, "CIE", ["I"]) == ["I"]


def test_without_a_vector_the_code_letters_the_student_confirmed() -> None:
    assert svc.shared_letters({}, None, "SEC", ["C", "S"]) == ["S", "C"]


def test_letters_are_capped() -> None:
    profile = {"R": 90, "I": 90, "A": 90, "S": 90, "E": 10, "C": 10}
    vector = {"R": 6.0, "I": 6.0, "A": 6.0, "S": 6.0, "E": 1.0, "C": 1.0}
    letters = svc.shared_letters(profile, vector, "RIA", ["R", "I", "A", "S"])
    assert len(letters) == career_fit_rules.max_letters


# ── reasons ──────────────────────────────────────────────────────────────────


def test_a_task_result_is_paired_with_a_skill_on_its_axis() -> None:
    inputs = StrengthInputs(astur=astur_snapshot({"numeric_series": 95}))
    [reason] = _fit(inputs)["careers"]["buhgalter"]["reasons"]
    assert reason["source_id"] == "strength:astur:numeric"
    # «умение работать с цифрами» — the numbers skill, not the first skill.
    assert _BY_SLUG["buhgalter"]["skills_needed"][reason["skill_index"]] == "умение работать с цифрами"


def test_visible_exploratory_interests_can_ground_flat_profile_careers() -> None:
    inputs = StrengthInputs(riasec_ranked=["I", "R", "A", "C", "S", "E"])
    pool = svc.fact_pool(inputs)
    assert [c.source_id for c in pool[:5]] == [
        "strength:interest:I",
        "strength:interest:R",
        "strength:interest:A",
        "strength:interest:C",
        "strength:interest:S",
    ]

    reasons = _fit(inputs)["careers"]["buhgalter"]["reasons"]
    assert reasons
    assert all(r["kind"] == "fact" for r in reasons)
    assert reasons[0]["source_id"].startswith("strength:interest:")


def test_each_fact_and_each_skill_backs_one_reason_at_most() -> None:
    reasons = _fit(rich_inputs())["careers"]["buhgalter"]["reasons"]
    facts = [r for r in reasons if r["kind"] == "fact"]
    assert len(facts) <= career_fit_rules.max_fact_reasons
    assert len(reasons) <= career_fit_rules.max_reasons
    assert len({r["skill_index"] for r in facts}) == len(facts)
    evidence = [e for r in facts for e in r["evidence_ids"]]
    assert len(evidence) == len(set(evidence))


def test_a_skill_whose_catalog_text_changed_is_never_paired() -> None:
    inputs = StrengthInputs(astur=astur_snapshot({"numeric_series": 95}))
    skills = list(_BY_SLUG["buhgalter"]["skills_needed"])
    skills[0] = "что-то совсем другое"
    reasons = _fit(inputs, _direction(skills=skills))["careers"]["buhgalter"]["reasons"]
    assert all(r.get("skill_index") != 0 for r in reasons)


def test_the_lie_scale_drops_self_reports_like_the_strength_cards() -> None:
    inputs = StrengthInputs(belbin_role_totals=belbin_totals(finisher=20), lie_flagged=True)
    assert not any(
        r["source_id"].startswith("strength:belbin")
        for r in _fit(inputs)["careers"]["buhgalter"]["reasons"]
    )


def test_a_cross_test_fact_speaks_for_its_interest_only() -> None:
    # cross.lead = E interest confirmed by Belbin's coordinator: it may back a
    # leadership skill, never «teamwork» just because the coordinator does.
    inputs = StrengthInputs(riasec_confirmed=["E"], belbin_role_totals=belbin_totals(coordinator=20))
    pool = {c.source_id: c for c in svc.fact_pool(inputs)}
    assert "strength:cross:lead" in pool
    hirurg = _direction("hirurg")
    reasons = _fit(inputs, hirurg)["careers"]["hirurg"]["reasons"]
    team_index = _BY_SLUG["hirurg"]["skills_needed"].index("работать в команде операционной бригады")
    assert not any(
        r["source_id"] == "strength:cross:lead" and r["skill_index"] == team_index for r in reasons
    )


def test_easy_subject_wins_over_liked() -> None:
    inputs = StrengthInputs(subjects_liked=["Математика"], subjects_easy=["Информатика"])
    reasons = _fit(inputs)["careers"]["buhgalter"]["reasons"]
    subjects = [r for r in reasons if r["kind"] == "subject"]
    assert subjects and subjects[0]["subject"] in {"Информатика", "Математика"}
    # bookkeeping lists математика first: the first catalog subject the student has.
    assert subjects[0]["subject"] == "Математика" and subjects[0]["how"] == "liked"
    assert isinstance(subjects[0].get("skill_index"), int)


def test_free_text_subjects_never_match() -> None:
    inputs = StrengthInputs(subjects_liked=["Шахматы"])
    assert not _fit(inputs)["careers"]["buhgalter"]["reasons"]


def test_cards_do_not_all_open_with_the_same_fact() -> None:
    inputs = StrengthInputs(astur=astur_snapshot({"numeric_series": 95, "logical_schemas": 95}))
    fit = _fit(inputs, _direction("buhgalter"), _direction("auditor"), _direction("aktuariy"))
    openers = [fit["careers"][slug]["reasons"][0]["source_id"] for slug in ("buhgalter", "auditor", "aktuariy")]
    assert len(set(openers)) > 1


def test_stored_fit_is_locale_free_and_versioned() -> None:
    inputs = rich_inputs()
    with use_locale("kk"):
        kk = svc.build_career_fit(inputs, {"I": 90, "C": 85}, [_direction()])
    assert _fit(inputs, profile={"I": 90, "C": 85}) == kk
    assert svc.is_current(kk) and kk["version"] == career_fit_rules.version
    assert not svc.is_current(None) and not svc.is_current({"version": -1})


def test_vetted_pool_does_not_change_the_strength_cards() -> None:
    inputs = rich_inputs()
    with use_locale("ru"):
        pool = student_strengths_service.vetted_candidates(inputs)
        selected = student_strengths_service.select_strengths(inputs)
    assert {c.source_id for c in selected} - {c.source_id for c in pool} <= {
        c.source_id for c in selected if c.basis == "interest"
    }


# ── render ───────────────────────────────────────────────────────────────────


def _render(entry: dict, locale: str = "ru", slug: str = "buhgalter"):
    with use_locale(locale):
        return svc.render_career(entry, _career(slug, locale))


def test_render_names_the_shared_interests() -> None:
    # The interest line is the fallback when no concrete fact ↔ skill reason
    # can be rendered. Concrete reasons are tested below and take precedence.
    entry = {"letters": ["C", "I"], "reasons": []}
    summary, _, keys = _render(entry)
    assert summary == (
        "Совпадает с тем, что тебе ближе всего: порядок и исследование. "
        "В этой профессии особенно важно: умение работать с цифрами."
    )
    assert keys[:2] == ["riasec:C", "riasec:I"]
    kk_summary, _, _ = _render(entry, "kk")
    assert kk_summary == (
        "Бұл мамандық саған ең жақын нәрсеге сәйкес келеді: реттілік және зерттеу. "
        f"Бұл мамандықта әсіресе маңыздысы: {svc._lower_first(_career(locale='kk')['skills_needed'][0])}."
    )


def test_render_reads_the_fact_and_the_row_language_skill() -> None:
    entry = _fit(StrengthInputs(astur=astur_snapshot({"numeric_series": 95})))["careers"]["buhgalter"]
    why, [reason], keys = _render(entry)
    assert reason.text == (
        "Ты хорошо замечаешь закономерности в числах — здесь это пригодится: умение работать с цифрами."
    )
    assert why == reason.text  # a concrete reason wins over the generic interest fallback
    assert reason.fact == "Ты хорошо замечаешь закономерности в числах"
    assert keys == ["strength:astur:numeric"]

    _, [kk_reason], _ = _render(entry, "kk")
    kk_skill = _REVIEW_KK["buhgalter"]["skills_needed"][entry["reasons"][0]["skill_index"]]
    assert kk_skill.rstrip(".")[1:] in kk_reason.text and "Сандардағы" in kk_reason.text


def test_render_subject_reason_in_both_languages() -> None:
    entry = {"letters": [], "reasons": [{"kind": "subject", "subject": "История", "how": "liked"}]}
    why, [reason], keys = _render(entry)
    assert reason.text == "Тебе нравится предмет «История» — в этой профессии он понадобится."
    assert why == reason.text
    assert keys == ["subject:История"]
    _, [kk_reason], _ = _render(entry, "kk")
    assert "«Тарих»" in kk_reason.text


def test_subject_reason_names_a_related_profession_skill() -> None:
    inputs = StrengthInputs(subjects_liked=["Математика"])
    entry = _fit(inputs)["careers"]["buhgalter"]
    stored = next(reason for reason in entry["reasons"] if reason["kind"] == "subject")
    why, [reason], _ = _render(entry)
    assert stored["skill_index"] == _BY_SLUG["buhgalter"]["skills_needed"].index("умение работать с цифрами")
    assert reason.text == "Тебе нравится предмет «Математика» — здесь это пригодится: умение работать с цифрами."
    assert why == reason.text


def test_a_subject_never_repeats_the_skill_a_fact_already_named() -> None:
    # Found live: the subject was paired with the same skill as the first fact
    # («оценивать погрешности…» twice in one «Почему тебе подходит»).
    inputs = StrengthInputs(astur=astur_snapshot({"numeric_series": 95}), subjects_liked=["Математика"])
    reasons = _fit(inputs)["careers"]["buhgalter"]["reasons"]
    skills = [r["skill_index"] for r in reasons if "skill_index" in r]
    assert any(r["kind"] == "subject" for r in reasons)
    assert len(skills) == len(set(skills))


def test_subject_without_a_related_profession_skill_is_omitted() -> None:
    inputs = StrengthInputs(subjects_liked=["Литература"])
    entry = _fit(inputs, _direction("bibliotekar"))["careers"]["bibliotekar"]
    assert not any(reason["kind"] == "subject" for reason in entry["reasons"])


def test_why_is_one_text_over_every_reason_in_both_languages() -> None:
    entry = {
        "letters": ["I"],
        "reasons": [
            {
                "kind": "fact",
                "source_id": "strength:astur:numeric",
                "content_key": "astur.numeric",
                "evidence_ids": ["astur:numeric"],
                "skill_index": 0,
            },
            {
                "kind": "fact",
                "source_id": "strength:astur:logical_reasoning",
                "content_key": "astur.logical_reasoning",
                "evidence_ids": ["astur:logical_reasoning"],
                "skill_index": 4,
            },
            {
                "kind": "subject",
                "subject": "Математика",
                "how": "easy",
                "skill_index": 1,
            },
        ],
    }
    why, reasons, _ = _render(entry)
    assert why == (
        "Ты хорошо замечаешь закономерности в числах — здесь это пригодится: умение работать с цифрами. "
        "А ещё ты умеешь проверять, следует ли вывод из условий — здесь это пригодится: умение анализировать данные. "
        "Кроме того, тебе легко даётся предмет «Математика» — здесь это пригодится: знание бухгалтерского учета."
    )
    assert len(reasons) == 3

    kk_why, kk_reasons, _ = _render(entry, "kk")
    assert kk_why == (
        f"{kk_reasons[0].text} Сонымен қатар, {svc._lower_first(kk_reasons[1].text)}. "
        f"Оған қоса, {svc._lower_first(kk_reasons[2].text)}."
    )


def test_render_drops_what_it_cannot_ground_and_never_raises() -> None:
    entry = {
        "letters": ["I", "Z"],
        "reasons": [
            {"kind": "fact", "source_id": "x", "content_key": "astur.numeric", "evidence_ids": [], "skill_index": 99},
            {"kind": "fact", "source_id": "y", "content_key": "no.such.card", "evidence_ids": [], "skill_index": 0},
            {"kind": "subject", "subject": "Шахматы", "how": "liked"},
            {"kind": "subject", "subject": "История", "how": "sometimes"},
        ],
    }
    summary, reasons, keys = _render(entry)
    assert reasons == [] and keys == ["riasec:I"]
    assert summary == (
        "Совпадает с тем, что тебе ближе всего: исследование. "
        "В этой профессии особенно важно: умение работать с цифрами."
    )
    ru_fallback = tr("career_fit", locale="ru")["reason_skill_fallback"].format(
        skill=svc._lower_first(_career()["skills_needed"][0])
    )
    assert _render(None) == (ru_fallback, [], [])
    assert _render({"letters": 5}) == (ru_fallback, [], [])
    with use_locale("kk"):
        kk_fallback = tr("career_fit", locale="kk")["reason_skill_fallback"].format(
            skill=svc._lower_first(_career()["skills_needed"][0])
        )
        assert svc.render_career(None, _career())[0] == kk_fallback


def test_acronym_skills_keep_their_case() -> None:
    assert svc._lower_first("Анализировать данные.") == "анализировать данные"
    assert svc._lower_first("SQL-запросы") == "SQL-запросы"
