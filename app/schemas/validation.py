"""Reusable request-schema validation helpers."""

from collections.abc import Hashable, Iterable
from typing import Annotated
from urllib.parse import urlsplit

from pydantic import Field
from pydantic_core import PydanticCustomError

from app.i18n.catalog import key as i18n_key

# --- Size ceilings for request fields (SEC-14) --------------------------------
# Every string and every list a client sends has an upper bound: without one a
# single request can overflow a varchar column (a 500 instead of a 422), bloat
# a JSONB column, or hand the database an `IN (...)` of any length. A field
# with a real domain limit (a name, a chip, a code) declares its own; these
# are the shared ones for staff-edited text, set far above anything stored
# today — they are ceilings, not style rules. tests/unit/test_request_size_limits.py
# fails when a request field is added without a bound.

# Narrative text: descriptions, report summaries, notes (longest today: ~700).
LONG_TEXT_MAX_LENGTH = 20_000
# One entry of a list — a profession, a skill, a first step, an alias.
LIST_ITEM_MAX_LENGTH = 500
# Entries in such a list (longest today: 10).
LIST_MAX_ITEMS = 100
# A two-letter locale tag, with room.
LOCALE_MAX_LENGTH = 16
# `{item: value}` maps of the tests (Belbin block, АСТУР subtest): the largest
# real one has 20 entries.
ANSWER_MAP_MAX_ITEMS = 200
ANSWER_MAP_KEY_MAX_LENGTH = 64

LongText = Annotated[str, Field(max_length=LONG_TEXT_MAX_LENGTH)]
ListItemText = Annotated[str, Field(max_length=LIST_ITEM_MAX_LENGTH)]
AnswerMapKey = Annotated[str, Field(max_length=ANSWER_MAP_KEY_MAX_LENGTH)]


def http_url(value: str | None) -> str | None:
    """A link that ends up in an `href`: `http(s)://host…`, or empty.

    A browser runs `javascript:` (and renders `data:`) straight from a link,
    so any other scheme stored here is script on the page that shows it."""
    if value is None:
        return None
    value = value.strip()
    if not value:
        return value
    try:
        parts = urlsplit(value)
        is_web_link = parts.scheme in ("http", "https") and bool(parts.hostname)
    except ValueError:
        is_web_link = False
    if not is_web_link:
        raise PydanticCustomError("url_must_be_http", i18n_key("api_errors", "url_must_be_http"))
    return value


def ensure_unique(values: Iterable[Hashable], *, error_code: str) -> None:
    """Raise a stable Pydantic validation error for repeated identifiers."""
    seen: set[Hashable] = set()
    duplicates: list[Hashable] = []
    duplicate_set: set[Hashable] = set()

    for value in values:
        if value in seen and value not in duplicate_set:
            duplicates.append(value)
            duplicate_set.add(value)
        seen.add(value)

    if duplicates:
        raise PydanticCustomError(
            error_code,
            i18n_key("api_errors", error_code).format(
                values=", ".join(str(value) for value in duplicates)
            ),
        )
