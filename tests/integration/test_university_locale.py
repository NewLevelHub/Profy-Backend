"""KZ-501 — University/Program free-text fields carry a nullable `*_i18n`
override map ({"kk": "..."}); the base column keeps the `ru` text. The read
side (`university_service`) serves the override for a non-`ru` locale when it
exists and falls back to the `ru` base otherwise, reporting which via the
`description_locale` / `who_its_for_locale` response fields.
"""
import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.i18n import DEFAULT_LOCALE, resolve_column_i18n
from app.models.direction import Direction
from app.models.program import Program
from app.models.university import University
from app.services import university_service

SLUG = "test-direction-kz501"


# ── pure resolver ─────────────────────────────────────────────────────────────

def test_resolve_column_i18n_returns_override_when_present():
    text, loc = resolve_column_i18n({"kk": "Қазақша сипаттама"}, "Русский текст", "kk")
    assert (text, loc) == ("Қазақша сипаттама", "kk")


def test_resolve_column_i18n_falls_back_to_ru_when_locale_missing():
    text, loc = resolve_column_i18n({}, "Русский текст", "kk")
    assert (text, loc) == ("Русский текст", DEFAULT_LOCALE)
    text, loc = resolve_column_i18n(None, "Русский текст", "kk")
    assert (text, loc) == ("Русский текст", DEFAULT_LOCALE)


def test_resolve_column_i18n_ru_request_never_touches_overrides():
    text, loc = resolve_column_i18n({"kk": "Қазақша"}, "Русский текст", "ru")
    assert (text, loc) == ("Русский текст", "ru")


def test_resolve_column_i18n_handles_missing_base():
    assert resolve_column_i18n(None, None, "kk") == (None, DEFAULT_LOCALE)


def test_resolve_column_i18n_blank_override_is_ignored():
    text, loc = resolve_column_i18n({"kk": ""}, "Русский текст", "kk")
    assert (text, loc) == ("Русский текст", DEFAULT_LOCALE)


# ── read side ────────────────────────────────────────────────────────────────

async def _seed_program(db: AsyncSession, **program_overrides) -> Program:
    university = University(
        name="Test University KZ501",
        country="Казахстан",
        city="Алматы",
        description="Русское описание вуза",
        **program_overrides.pop("university_overrides", {}),
    )
    db.add(university)
    direction = Direction(name="Test Direction", slug=SLUG, holland_code="RIA")
    db.add(direction)
    await db.flush()

    # Defaults a caller may override by name — `language` / `grants` matter to
    # the dictionary tests at the bottom of this file.
    fields = {
        "name": "Тестовая программа",
        "language": "ru",
        "description": "Русское описание программы",
        "who_its_for": "Русский текст «для кого»",
        "requirements": {},
        "deadlines": {},
        "grants": [],
    }
    fields.update(program_overrides)
    program = Program(university_id=university.id, **fields)
    program.directions = [direction]
    db.add(program)
    await db.flush()
    return program


async def test_kk_request_without_overrides_gets_ru_and_ru_locale(db_session: AsyncSession):
    program = await _seed_program(db_session)

    detail = await university_service.get_program_detail(db_session, program.id, locale="kk")
    assert detail.description == "Русское описание программы"
    assert detail.description_locale == "ru"
    assert detail.who_its_for_locale == "ru"
    assert detail.university.description == "Русское описание вуза"
    assert detail.university.description_locale == "ru"

    briefs = await university_service.list_program_briefs(db_session, SLUG, locale="kk")
    assert briefs[0].description == "Русское описание программы"
    assert briefs[0].description_locale == "ru"
    assert briefs[0].university.description_locale == "ru"


async def test_kk_request_with_overrides_gets_kk(db_session: AsyncSession):
    program = await _seed_program(
        db_session,
        description_i18n={"kk": "Бағдарламаның қазақша сипаттамасы"},
        who_its_for_i18n={"kk": "Қазақша «кімге арналған»"},
        university_overrides={"description_i18n": {"kk": "Университеттің қазақша сипаттамасы"}},
    )

    detail = await university_service.get_program_detail(db_session, program.id, locale="kk")
    assert detail.description == "Бағдарламаның қазақша сипаттамасы"
    assert detail.description_locale == "kk"
    assert detail.who_its_for == "Қазақша «кімге арналған»"
    assert detail.who_its_for_locale == "kk"
    assert detail.university.description == "Университеттің қазақша сипаттамасы"
    assert detail.university.description_locale == "kk"

    briefs = await university_service.list_program_briefs(db_session, SLUG, locale="kk")
    assert briefs[0].description == "Бағдарламаның қазақша сипаттамасы"
    assert briefs[0].description_locale == "kk"
    assert briefs[0].university.description_locale == "kk"


async def test_ru_request_is_unchanged_by_the_overrides(db_session: AsyncSession):
    program = await _seed_program(
        db_session,
        description_i18n={"kk": "Қазақша"},
        university_overrides={"description_i18n": {"kk": "Қазақша вуз"}},
    )

    detail = await university_service.get_program_detail(db_session, program.id, locale="ru")
    assert detail.description == "Русское описание программы"
    assert detail.description_locale == "ru"
    assert detail.university.description == "Русское описание вуза"
    assert detail.university.description_locale == "ru"


async def test_default_locale_is_ru(db_session: AsyncSession):
    program = await _seed_program(db_session, description_i18n={"kk": "Қазақша"})
    detail = await university_service.get_program_detail(db_session, program.id)
    assert detail.description_locale == "ru"


# ── free text inside the catalog (contract §14) ──────────────────────────────
#
# `language`, `career_options` and `grants` are free text with no column of
# their own, so `resolve_column_i18n` does not reach them — they go through the
# source-string dictionary. The program screen renders these raw fields rather
# than their `requirements_summary` counterparts, so localizing only the
# summary left a Russian scholarship paragraph under a Kazakh heading.


@pytest.fixture
def dictionary(monkeypatch):
    """Two-entry stub, so this pins the wiring and not the shipped catalog."""
    from app.i18n import data_strings

    monkeypatch.setattr(
        data_strings,
        "_dictionary",
        lambda locale: {
            "английский": "ағылшын",
            "Грант на всё обучение": "Оқудың барлығына грант",
            "Отбор по баллам": "Балдар бойынша іріктеу",
            "Режиссёр": "Режиссёр-қоюшы",
        }
        if locale == "kk"
        else {},
    )


async def test_kk_gets_the_dictionary_for_language_grants_and_careers(
    db_session: AsyncSession, dictionary
):
    program = await _seed_program(
        db_session,
        language="английский",
        career_options=["Режиссёр"],
        grants=[{"name": "Грант на всё обучение", "amount": "100%", "conditions": "Отбор по баллам"}],
    )

    detail = await university_service.get_program_detail(db_session, program.id, locale="kk")
    assert detail.language == "ағылшын"
    assert detail.career_options == ["Режиссёр-қоюшы"]
    assert detail.grants[0]["name"] == "Оқудың барлығына грант"
    assert detail.grants[0]["conditions"] == "Балдар бойынша іріктеу"
    # Non-text keys must survive untouched — the UI reads `amount` as-is.
    assert detail.grants[0]["amount"] == "100%"

    briefs = await university_service.list_program_briefs(db_session, SLUG, locale="kk")
    assert briefs[0].language == "ағылшын"


async def test_ru_keeps_the_source_text(db_session: AsyncSession, dictionary):
    program = await _seed_program(
        db_session,
        language="английский",
        grants=[{"name": "Грант на всё обучение"}],
    )

    detail = await university_service.get_program_detail(db_session, program.id, locale="ru")
    assert detail.language == "английский"
    assert detail.grants[0]["name"] == "Грант на всё обучение"


async def test_a_phrase_the_dictionary_lacks_is_served_as_is(
    db_session: AsyncSession, dictionary
):
    """Contract §5: a miss keeps the Russian source rather than blanking the
    card — a new import must degrade, not break."""
    program = await _seed_program(
        db_session,
        language="суахили",
        grants=[{"name": "Неизвестная стипендия"}],
    )

    detail = await university_service.get_program_detail(db_session, program.id, locale="kk")
    assert detail.language == "суахили"
    assert detail.grants[0]["name"] == "Неизвестная стипендия"
