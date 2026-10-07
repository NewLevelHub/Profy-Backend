"""PRO-430: the kk RIASEC explanations are a real translation. They used to
be generated from RU by word substitution, which left most of each sentence
in Russian and broke words mid-way («поработать» → «пожұмысть»)."""

import re
import string

from app.i18n.catalog import riasec_explanations as catalog

# Frequent Russian-only function words; none of them is a Kazakh word.
_RUSSIAN_WORDS = re.compile(
    r"(?<!\w)(и|в|на|с|по|что|это|для|или|как|где|тебе|тебя|ты|можно|нужно|когда|который|очень|только)(?!\w)",
    re.IGNORECASE,
)


def _placeholders(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def test_kk_covers_every_ru_key() -> None:
    assert set(catalog.KK) == set(catalog.RU)


def test_kk_keeps_the_ru_placeholders() -> None:
    for key, ru in catalog.RU.items():
        assert _placeholders(catalog.KK[key]) == _placeholders(ru), key


def test_kk_is_not_russian() -> None:
    for key, kk in catalog.KK.items():
        assert kk != catalog.RU[key], key
        assert not _RUSSIAN_WORDS.findall(kk), (key, _RUSSIAN_WORDS.findall(kk))
