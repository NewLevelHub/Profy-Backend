"""Reusable request-schema validation helpers."""

from collections.abc import Hashable, Iterable
from urllib.parse import urlsplit

from pydantic_core import PydanticCustomError

from app.i18n.catalog import key as i18n_key


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
