"""Reusable request-schema validation helpers."""

from collections.abc import Hashable, Iterable

from pydantic_core import PydanticCustomError

from app.i18n.catalog import key as i18n_key


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
