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
    direction = Direction(name={"ru": "Test Direction"}, slug=SLUG, holland_code="RIA")
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


# ── catalogue and university page (PRO-450) ─────────────────────────────────
#
# Both used to build their response straight from the row, so the kk UI showed
# the Russian name/description even though the kk overlay was filled in.

_KK_UNIVERSITY = {
    "name_i18n": {"kk": "Тест университеті KZ501"},
    "description_i18n": {"kk": "Университеттің қазақша сипаттамасы"},
}


async def test_catalogue_serves_kk_name_and_description(db_session: AsyncSession):
    await _seed_program(db_session, university_overrides=_KK_UNIVERSITY)

    page = await university_service.list_universities(db_session, search="KZ501", locale="kk")
    [item] = page.items
    assert (item.name, item.name_locale) == ("Тест университеті KZ501", "kk")
    assert (item.description, item.description_locale) == ("Университеттің қазақша сипаттамасы", "kk")
    assert item.programs_count == 1

    page = await university_service.list_universities(db_session, search="KZ501", locale="ru")
    [item] = page.items
    assert (item.name, item.name_locale) == ("Test University KZ501", "ru")
    assert (item.description, item.description_locale) == ("Русское описание вуза", "ru")


@pytest.mark.parametrize("locale", ["kk", "ru"])
async def test_catalogue_search_matches_the_kk_name(db_session: AsyncSession, locale: str):
    await _seed_program(db_session, university_overrides=_KK_UNIVERSITY)

    page = await university_service.list_universities(db_session, search="тест университеті", locale=locale)
    assert [item.name_locale for item in page.items] == [locale]
    assert page.total == 1


@pytest.mark.parametrize("search", ["Өскемен", "өске"])
async def test_catalogue_search_matches_the_kk_city_name(db_session: AsyncSession, search: str):
    db_session.add(University(name="Тестовый вуз ВКО KZ501", country="Казахстан", city="Усть-Каменогорск"))
    db_session.add(University(name="Тестовый вуз Алматы KZ501", country="Казахстан", city="Алматы"))
    await db_session.flush()

    page = await university_service.list_universities(db_session, search=search, locale="kk")
    cities = {item.city for item in page.items}
    assert "Усть-Каменогорск" in cities
    assert "Алматы" not in cities


async def test_catalogue_search_tolerates_rows_without_translated_name(db_session: AsyncSession):
    await _seed_program(db_session)

    page = await university_service.list_universities(db_session, search="KZ501", locale="kk")
    assert page.total == 1
    assert page.items[0].name_locale == "ru"


async def test_university_page_serves_kk_for_itself_and_its_programs(db_session: AsyncSession):
    program = await _seed_program(
        db_session,
        description_i18n={"kk": "Бағдарламаның қазақша сипаттамасы"},
        university_overrides=_KK_UNIVERSITY,
    )

    detail = await university_service.get_university_for_user(
        db_session, program.university_id, locale="kk"
    )
    assert (detail.name, detail.name_locale) == ("Тест университеті KZ501", "kk")
    assert detail.description == "Университеттің қазақша сипаттамасы"
    [brief] = detail.programs
    assert (brief.description, brief.description_locale) == ("Бағдарламаның қазақша сипаттамасы", "kk")
    assert brief.university.name == "Тест университеті KZ501"

    detail = await university_service.get_university_for_user(db_session, program.university_id)
    assert (detail.name, detail.description_locale) == ("Test University KZ501", "ru")
    assert detail.programs[0].description_locale == "ru"


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
