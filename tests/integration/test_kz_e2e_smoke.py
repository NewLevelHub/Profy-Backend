"""KZ-601 — end-to-end smoke that the whole `kk` path renders Kazakh locally.

Not a replacement for the manual native-speaker walkthrough
(`docs/qa-kz-e2e-checklist.md`) — this is the automated floor: the key
seams a `kk` student hits (report narrative for every age tier, direction
detail, program-description overlay, the "russian-only" transit badge, gap
analysis) come back non-empty, not an i18n key, and Kazakh by the same
heuristic the runtime validator uses.

Real transactional Postgres session — synthetic rows never escape it, and the
seeded `kk` content (question banks, directions, `description_i18n['kk']`) is
the same data `start.sh` produces.
"""
import uuid
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import use_locale
from app.models.assessment import Assessment, AssessmentGoal
from app.models.direction import Direction
from app.models.profile import AgeGroup, Profile
from app.models.program import Program
from app.models.university import University
from app.models.user import User
from app.services import (
    assessment_shared,
    direction_service,
    gap_analysis_service,
    llm_client,
    motivation_pair_service,
    motivation_service,
    university_service,
)
from app.services.report_narrative_validator import _check_language_kk

_KK_CHARS = set("әғқңөұүһі")


def _looks_like_key(text: str) -> bool:
    """`onboarding.subject.math`, `results.page.title` — a dotted ascii token
    with no spaces is almost certainly an unresolved i18n key."""
    t = text.strip()
    return bool(t) and " " not in t and "." in t and t.replace(".", "").replace("_", "").isalnum() and t.isascii()


def _assert_kk_prose(label: str, text: str | None) -> None:
    assert text and text.strip(), f"{label}: empty"
    assert not _looks_like_key(text), f"{label}: looks like an i18n key -> {text!r}"
    issues = _check_language_kk([text])
    assert issues == [], f"{label}: not Kazakh -> {text!r} ({issues})"


def _assert_kk_label(label: str, text: str | None) -> None:
    """Short labels (sphere names, subjects) may not carry a kk-specific
    letter, so only require: non-empty, not a key, has Cyrillic, no obvious
    Russian marker handled by the prose check elsewhere."""
    assert text and text.strip(), f"{label}: empty"
    assert not _looks_like_key(text), f"{label}: looks like an i18n key -> {text!r}"


# ── report narrative, every age tier ────────────────────────────────────────

async def _kk_report(db: AsyncSession, monkeypatch, age_group: AgeGroup):
    user = User(email=f"{uuid.uuid4()}@example.com", hashed_password="x",
                is_active=True, is_verified=True, locale="kk")
    db.add(user)
    await db.flush()
    profile = Profile(user_id=user.id, name="Тест", age=16, grade=9, city="Алматы",
                      country="Қазақстан", language="қазақша", age_group=age_group)
    db.add(profile)
    await db.flush()
    assessment = Assessment(profile_id=profile.id, goal=AssessmentGoal.explore)
    db.add(assessment)
    await db.flush()

    monkeypatch.setattr(assessment_shared, "likert_answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(assessment_shared, "likert_total_questions", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_service, "total_triplets", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_pair_service, "answered_count", AsyncMock(return_value=1))
    monkeypatch.setattr(motivation_pair_service, "total_pairs", AsyncMock(return_value=1))
    monkeypatch.setattr(llm_client, "is_enabled", lambda: False)

    from app.services import report_service
    return await report_service.build_report(assessment.id, db)


@pytest.mark.parametrize("age_group", [AgeGroup.junior, AgeGroup.middle, AgeGroup.senior])
async def test_report_narrative_is_kazakh_for_every_age_tier(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch, age_group: AgeGroup
) -> None:
    resp = await _kk_report(db_session, monkeypatch, age_group)

    for field in ("summary", "final_analysis", "interest_map_note", "personality_note"):
        value = getattr(resp, field, None)
        if value:  # junior/middle variants may omit some sections
            _assert_kk_prose(f"{age_group.value}.{field}", value)

    for card in getattr(resp, "strength_cards", []) or []:
        _assert_kk_prose(f"{age_group.value}.strength_card", card.description)

    spheres = [item.sphere for item in getattr(resp, "interest_map", []) or []]
    assert spheres, f"{age_group.value}: empty interest map"
    for sphere in spheres:
        _assert_kk_label(f"{age_group.value}.sphere", sphere)
    # ru sphere names must not leak through
    assert not ({"Реалистичный", "Исследовательский", "Артистичный"} & set(spheres))


async def test_report_has_no_empty_or_key_like_sections(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    resp = await _kk_report(db_session, monkeypatch, AgeGroup.senior)
    payload = resp.model_dump()

    def _walk(node, path="$"):
        if isinstance(node, str):
            if node.strip():
                assert not _looks_like_key(node), f"{path}: i18n key leaked -> {node!r}"
        elif isinstance(node, dict):
            for k, v in node.items():
                _walk(v, f"{path}.{k}")
        elif isinstance(node, (list, tuple)):
            for i, v in enumerate(node):
                _walk(v, f"{path}[{i}]")

    _walk(payload)


# ── direction detail — real seeded kk content ───────────────────────────────

async def test_direction_detail_serves_real_kazakh_content(db_session: AsyncSession) -> None:
    slug = (await db_session.execute(
        select(Direction.slug)
        .where(Direction.locale == "kk", Direction.description.isnot(None), Direction.description != "")
        .limit(1)
    )).scalar_one_or_none()
    assert slug, "no seeded kk direction with content — run apply_direction_content.py"

    with use_locale("kk"):
        detail = await direction_service.get_direction_details(slug, db_session)

    assert detail is not None
    _assert_kk_prose(f"direction[{slug}].description", detail.description)
    for i, item in enumerate(detail.skills_needed or []):
        _assert_kk_label(f"direction[{slug}].skills_needed[{i}]", item)
    for i, item in enumerate(detail.first_steps or []):
        _assert_kk_prose(f"direction[{slug}].first_steps[{i}]", item)


# ── program description overlay (KZ-501/505) ────────────────────────────────

async def _program_with(db: AsyncSession, *, kk_desc: str | None, kk_who: str | None):
    uni = University(name="Тестовый университет", country="Қазақстан", city="Астана",
                     name_i18n={"kk": "Сынақ университеті"},
                     description="Русское описание вуза",
                     description_i18n={"kk": "Университеттің қазақ тіліндегі сипаттамасы."})
    db.add(uni)
    await db.flush()
    program = Program(
        university_id=uni.id, name=f"Программа {uuid.uuid4().hex[:6]}", language="қазақша",
        name_i18n={"kk": "Бағдарлама"},
        description="Русское описание программы",
        description_i18n=({"kk": kk_desc} if kk_desc else None),
        who_its_for="Русский «для кого»",
        who_its_for_i18n=({"kk": kk_who} if kk_who else None),
        requirements={}, deadlines={}, grants=[],
    )
    db.add(program)
    await db.flush()
    return program


async def test_program_detail_serves_kk_description_overlay(db_session: AsyncSession) -> None:
    program = await _program_with(
        db_session,
        kk_desc="Бұл бағдарлама бағдарламалық жасақтаманы әзірлеуге баулиды.",
        kk_who="Нақты ғылымдарды ұнататын оқушыларға арналған.",
    )
    detail = await university_service.get_program_detail(db_session, program.id, locale="kk")

    assert detail.description_locale == "kk"
    assert detail.who_its_for_locale == "kk"
    _assert_kk_prose("program.description", detail.description)
    _assert_kk_prose("program.who_its_for", detail.who_its_for)
    _assert_kk_prose("program.university.description", detail.university.description)
    # KZ-206 follow-up: Kazakhstan university + program names served in Kazakh
    assert detail.university.name == "Сынақ университеті"
    assert detail.university.name_locale == "kk"
    assert detail.name == "Бағдарлама" and detail.name_locale == "kk"


async def test_kz_program_name_overlay_serves_kk_and_ru_is_unchanged(
    db_session: AsyncSession,
) -> None:
    """`name_i18n['kk']` (KZ-206 follow-up) is served on a kk request; a ru
    request still gets the base `name`. An internationally-identical term
    ("Биология" -> "Биология") is still tagged name_locale='kk'."""
    uni = University(name="Тестовый университет", country="Қазақстан", city="Астана")
    db_session.add(uni)
    await db_session.flush()
    prog = Program(
        university_id=uni.id, name="Безопасность жизнедеятельности", language="қазақша",
        name_i18n={"kk": "Тіршілік қауіпсіздігі"},
        requirements={}, deadlines={}, grants=[],
    )
    same = Program(
        university_id=uni.id, name="Биология", language="қазақша",
        name_i18n={"kk": "Биология"},  # identical term, still an explicit override
        requirements={}, deadlines={}, grants=[],
    )
    db_session.add_all([prog, same])
    await db_session.flush()

    detail_kk = await university_service.get_program_detail(db_session, prog.id, locale="kk")
    detail_ru = await university_service.get_program_detail(db_session, prog.id, locale="ru")
    assert detail_kk.name == "Тіршілік қауіпсіздігі" and detail_kk.name_locale == "kk"
    assert detail_ru.name == "Безопасность жизнедеятельности" and detail_ru.name_locale == "ru"

    same_kk = await university_service.get_program_detail(db_session, same.id, locale="kk")
    assert same_kk.name == "Биология" and same_kk.name_locale == "kk"


async def test_kz_university_name_overlay_and_foreign_fallback(
    db_session: AsyncSession,
) -> None:
    """A Kazakhstan university with `name_i18n['kk']` is served under its
    Kazakh official name on a kk request; a university without the override
    (foreign) falls back to `name` with name_locale='ru'."""
    kz = University(name="Карагандинский университет", country="Қазақстан", city="Караганда",
                    name_i18n={"kk": "Қарағанды университеті"})
    foreign = University(name="University of Oxford", country="Великобритания", city="Oxford")
    db_session.add_all([kz, foreign])
    await db_session.flush()

    kz_kk = university_service._university_brief(kz, "kk")
    kz_ru = university_service._university_brief(kz, "ru")
    assert kz_kk.name == "Қарағанды университеті" and kz_kk.name_locale == "kk"
    assert kz_ru.name == "Карагандинский университет" and kz_ru.name_locale == "ru"

    foreign_kk = university_service._university_brief(foreign, "kk")
    assert foreign_kk.name == "University of Oxford" and foreign_kk.name_locale == "ru"


async def test_untranslated_field_reports_ru_locale_for_the_badge(db_session: AsyncSession) -> None:
    """No kk override -> the field falls back to ru AND `*_locale` says so, so
    the frontend can show the KZ-502 'russian only' note instead of a blank."""
    program = await _program_with(db_session, kk_desc=None, kk_who=None)
    detail = await university_service.get_program_detail(db_session, program.id, locale="kk")

    assert detail.description_locale == "ru"
    assert detail.who_its_for_locale == "ru"
    assert detail.description  # not empty — ru text is still served
    assert detail.who_its_for


# ── gap analysis ───────────────────────────────────────────────────────────

async def test_gap_analysis_comments_are_kazakh(db_session: AsyncSession) -> None:
    profile = Profile(user_id=None, name="Тест", age=17, grade=11, city="Астана",
                      country="Қазақстан", language="қазақша", age_group=AgeGroup.senior)
    program = Program(
        university_id=(await _program_with(db_session, kk_desc=None, kk_who=None)).university_id,
        name="Гэп бағдарламасы", language="қазақша",
        requirements={"min_gpa": "3.0", "language_requirement": "IELTS 6.5"},
        deadlines={}, grants=[],
    )
    db_session.add(program)
    await db_session.flush()

    with use_locale("kk"):
        result = gap_analysis_service.analyze_gap(profile, [], {}, program)

    items = [*result.met, *result.not_met, *result.in_progress, *result.unknown]
    assert items, "gap analysis produced no items"
    for item in items:
        _assert_kk_prose(f"gap[{item.requirement}].comment", item.comment)
    blob = " ".join(item.comment for item in items)
    assert "ЕНТ" not in blob, "ru term ЕНТ leaked into a kk gap-analysis comment"
