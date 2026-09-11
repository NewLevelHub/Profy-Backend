"""`app/i18n/data_strings.py` — the source-string-keyed dictionary for free text
inside `Program.requirements`.

Unlike `app/i18n/catalog/` (fixed keys, hand-written trees) this store is
keyed by the Russian/English source string itself, so the things worth pinning
are: `ru` is a pass-through, a hit returns the translation, a miss returns the
source rather than a blank or a key, and the miss is tallied as a fallback.
"""

import pytest

from app import i18n
from app.i18n import data_strings
from app.i18n.data_strings import translate_data_list, translate_data_string


@pytest.fixture(autouse=True)
def _reset():
    i18n.reset_fallback_counts()
    i18n._current_locale.set(i18n.DEFAULT_LOCALE)
    yield
    i18n.reset_fallback_counts()
    i18n._current_locale.set(i18n.DEFAULT_LOCALE)


@pytest.fixture
def dictionary(monkeypatch):
    """Replace the shipped file with a two-entry stub, so these tests pin the
    resolver's behaviour and not the current state of the catalog."""
    monkeypatch.setattr(
        data_strings,
        "_dictionary",
        lambda locale: {"Медицинская справка": "Медициналық анықтама"} if locale == "kk" else {},
    )


def test_ru_returns_the_source_untouched(dictionary) -> None:
    assert translate_data_string("Медицинская справка", locale="ru") == "Медицинская справка"


def test_kk_hit_returns_the_translation(dictionary) -> None:
    assert translate_data_string("Медицинская справка", locale="kk") == "Медициналық анықтама"


def test_surrounding_whitespace_still_resolves(dictionary) -> None:
    """Keys are normalized on write; normalize on read too so a hand-edited
    file with stray whitespace does not silently miss."""
    assert translate_data_string("  Медицинская справка \n", locale="kk") == "Медициналық анықтама"


def test_miss_returns_the_source_not_a_blank(dictionary) -> None:
    """Contract §5: an untranslated string is served as-is. A blank card or a
    raw key on the screen is worse than Russian text."""
    assert translate_data_string("Незнакомая строка", locale="kk") == "Незнакомая строка"


def test_miss_is_tallied_as_a_fallback(dictionary) -> None:
    """The coverage gap has to show up in metrics rather than quietly render
    Russian under a Kazakh heading."""
    translate_data_string("Незнакомая строка", locale="kk")
    assert i18n.fallback_counts().get("kk")


def test_hit_is_not_tallied(dictionary) -> None:
    translate_data_string("Медицинская справка", locale="kk")
    assert not i18n.fallback_counts().get("kk")


@pytest.mark.parametrize("value", [None, "", "   "])
def test_blank_passes_through(dictionary, value) -> None:
    """`None` means "no data" and must stay distinguishable from "translated
    to nothing" — the frontend renders the two differently."""
    assert translate_data_string(value, locale="kk") == value


def test_list_preserves_order_and_length(dictionary) -> None:
    """These lists are rendered as-is and some are paired positionally with
    other fields at the call site, so a dropped or reordered entry is a bug."""
    out = translate_data_list(
        ["Медицинская справка", "Незнакомая строка", "Медицинская справка"], locale="kk"
    )
    assert out == ["Медициналық анықтама", "Незнакомая строка", "Медициналық анықтама"]


def test_empty_list_and_none_give_an_empty_list(dictionary) -> None:
    assert translate_data_list(None, locale="kk") == []
    assert translate_data_list([], locale="kk") == []


def test_absent_locale_file_is_not_an_error(monkeypatch) -> None:
    """A locale nobody has translated yet is a legitimate state: every lookup
    misses and every source string is served unchanged."""
    monkeypatch.setattr(data_strings, "_DATA_DIR", data_strings._DATA_DIR / "does-not-exist")
    data_strings._dictionary.cache_clear()
    try:
        assert translate_data_string("Медицинская справка", locale="kk") == "Медицинская справка"
    finally:
        data_strings._dictionary.cache_clear()


def test_shipped_kk_dictionary_is_loadable_and_non_empty() -> None:
    """Guards the committed file itself: valid JSON, all-string values, and
    no empty translation (an empty value would render as a blank card)."""
    shipped = data_strings._dictionary("kk")
    assert shipped, "kk dictionary is missing or empty"
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in shipped.items())
    assert all(v.strip() for v in shipped.values())
