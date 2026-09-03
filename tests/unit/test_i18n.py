"""Request-locale resolution — app/i18n.py. Pure logic, no DB/LLM.

While "kk" is not yet in SUPPORTED_LOCALES (removed by KZ-603), every "kk" input
resolves to the default "ru". The `kk -> kk` cases below are marked and flip to
active in KZ-603.
"""

import pytest

from app.i18n import (
    DEFAULT_LOCALE,
    KNOWN_LOCALES,
    SUPPORTED_LOCALES,
    MissingLocalizedText,
    fallback_counts,
    get_locale,
    guess_locale_from_language_field,
    normalize_locale,
    pick_locale,
    reset_fallback_counts,
    set_locale,
)


@pytest.fixture(autouse=True)
def _clear_fallback_counts():
    reset_fallback_counts()
    yield
    reset_fallback_counts()


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("ru", "ru"),
        ("RU", "ru"),
        ("  ru  ", "ru"),
        ("ru-RU", "ru"),
        ("ru,kk;q=0.9", "ru"),
        ("ru-RU,ru;q=0.9,en;q=0.8", "ru"),
        # kk not supported yet (KZ-603) -> falls back to ru
        ("kk", DEFAULT_LOCALE),
        ("kk-KZ", DEFAULT_LOCALE),
        ("kk;q=0.9,ru;q=0.1", DEFAULT_LOCALE),
        # unknown / junk -> default
        ("en", DEFAULT_LOCALE),
        ("de-DE,en;q=0.8", DEFAULT_LOCALE),
        ("", DEFAULT_LOCALE),
        (None, DEFAULT_LOCALE),
        ("garbage;;;", DEFAULT_LOCALE),
        (";q=0.5", DEFAULT_LOCALE),
        ("*", DEFAULT_LOCALE),
    ],
)
def test_normalize_locale(raw, expected):
    assert normalize_locale(raw) == expected


def test_normalize_locale_respects_q_weight_order():
    # both supported? only "ru" is right now, so this just confirms ru wins
    assert normalize_locale("en;q=0.1, ru;q=0.9") == "ru"
    assert normalize_locale("en;q=0.9, ru;q=0.1") == "ru"


@pytest.mark.parametrize(
    "raw, expected",
    [
        # trailing params after the q weight must not break float() parsing
        ("ru;q=0.1;x=1, kk;q=0.9", "kk"),
        ("kk;q=0.9;charset=utf-8, ru;q=0.1", "kk"),
        # q is matched case-insensitively
        ("ru;Q=0.1, kk;Q=0.9", "kk"),
        # out-of-range / junk q values are clamped or ignored, never win outright
        ("ru;q=5, kk;q=0.9", "ru"),  # q>1 clamps to 1.0, order breaks the tie -> ru first
        ("ru;q=nonsense, kk;q=0.5", "ru"),  # unparseable -> 1.0, ru wins
        ("ru;q=-1, kk;q=0.1", "kk"),  # q<0 clamps to 0.0
    ],
)
def test_normalize_locale_q_weight_parsing(raw, expected):
    assert normalize_locale(raw, allowed=KNOWN_LOCALES) == expected


def test_set_locale_clamps_to_supported():
    assert set_locale("ru") == "ru"
    assert get_locale() == "ru"
    # unsupported values are stored as the default, never raised on
    assert set_locale("kk") == DEFAULT_LOCALE
    assert set_locale("xx") == DEFAULT_LOCALE
    assert set_locale(None) == DEFAULT_LOCALE
    assert get_locale() == DEFAULT_LOCALE


def test_kk_is_gated_until_enable_pr():
    # KZ-603 flips this by adding "kk" to SUPPORTED_LOCALES; this guard test
    # documents the current state so the change is deliberate.
    assert "kk" not in SUPPORTED_LOCALES
    # ...but the persistence layer already knows about it.
    assert set(KNOWN_LOCALES) == {"ru", "kk"}


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("kk", "kk"),
        ("kk-KZ", "kk"),
        ("KK", "kk"),
        ("kk;q=0.9, ru;q=0.1", "kk"),
        ("ru, kk;q=0.9", "ru"),  # ru wins on weight
        ("en, kk;q=0.5", "kk"),  # en unknown -> kk
        ("en", "ru"),
        ("", "ru"),
        (None, "ru"),
    ],
)
def test_normalize_locale_with_known_locales_allows_kk(raw, expected):
    assert normalize_locale(raw, allowed=KNOWN_LOCALES) == expected


@pytest.mark.parametrize(
    "value, expected",
    [
        ("казахский", "kk"),
        ("Казахский язык", "kk"),
        ("қазақ тілі", "kk"),
        ("қазақша", "kk"),
        ("Kazakh", "kk"),
        ("kazakh language", "kk"),
        ("qazaq", "kk"),
        ("обучение на казахском", "kk"),
        ("русский", "ru"),
        ("Русский язык", "ru"),
        ("английский", "ru"),
        ("English", "ru"),
        ("", "ru"),
        (None, "ru"),
        # No false positives on ordinary words containing "каз"/"kaz".
        ("показать варианты", "ru"),
        ("рассказать о себе", "ru"),
        ("указать позже", "ru"),
        ("kazan", "ru"),
    ],
)
def test_guess_locale_from_language_field(value, expected):
    assert guess_locale_from_language_field(value) == expected


# ── pick_locale ────────────────────────────────────────────────────────────────

def test_pick_locale_returns_requested_when_present():
    assert pick_locale({"ru": "Привет", "kk": "Сәлем"}, "kk") == "Сәлем"
    assert pick_locale({"ru": "Привет", "kk": "Сәлем"}, "ru") == "Привет"
    assert fallback_counts() == {}


def test_pick_locale_falls_back_to_ru_and_counts():
    assert pick_locale({"ru": "Привет"}, "kk") == "Привет"
    assert fallback_counts() == {"kk": 1}
    # asking for ru is not a fallback
    assert pick_locale({"ru": "Привет"}, "ru") == "Привет"
    assert fallback_counts() == {"kk": 1}


def test_pick_locale_treats_blank_kk_as_missing():
    assert pick_locale({"ru": "Привет", "kk": ""}, "kk") == "Привет"
    assert fallback_counts() == {"kk": 1}


def test_pick_locale_raises_when_no_ru_fallback():
    # contract §5: never return "" where text is expected — a mapping without a
    # ru value (or empty / None) is a data-integrity bug, so it raises.
    for bad in ({}, None, {"kk": "Сәлем"}, {"en": "Hi"}):
        with pytest.raises(MissingLocalizedText):
            pick_locale(bad, "ru")
    # every attempt still bumped the fallback tally before raising
    assert fallback_counts() == {"ru": 4}


def test_pick_locale_uses_kk_without_needing_ru():
    # a present, non-blank kk value is returned as-is; ru is only the fallback
    assert pick_locale({"kk": "Сәлем"}, "kk") == "Сәлем"
    assert fallback_counts() == {}


def test_pick_locale_defaults_to_current_request_locale():
    set_locale("ru")  # SUPPORTED_LOCALES gate keeps this "ru" for now
    assert pick_locale({"ru": "Привет", "kk": "Сәлем"}) == "Привет"
