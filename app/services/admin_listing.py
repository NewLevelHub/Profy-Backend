"""Shared sort handling for every admin list endpoint.

One contract across all of them — `?sort=<field>&order=asc|desc` — with the
allowed field set declared per endpoint next to its own query, because a
sort field is a promise about a column that endpoint actually has.

Two rules are applied here rather than left to each caller, since getting
either wrong is invisible until an admin notices the list lying to them:

1. **NULLs always last.** Postgres orders NULLs FIRST on DESC. `updated_at`
   is null on every university that was never hand-edited and `ranking` is
   null on plenty more, so "sort by ranking, descending" would otherwise
   open on a page of rows that have no ranking at all — the exact opposite
   of what was asked for.

2. **Always a unique tiebreaker.** OFFSET/LIMIT pagination over a
   non-unique key has no defined order between rows that tie, and Postgres
   is free to return them differently per query. Without a tiebreaker the
   same row can show up on page 1 and page 2 while another never appears.
   Sorting 314 questions by `instrument` — 3 distinct values — is exactly
   that case.
"""

from typing import Any, Literal, Sequence

from sqlalchemy import nulls_last
from sqlalchemy.sql.elements import ColumnElement

# Postgres' default collation orders by byte value, which puts every
# Latin-named row ahead of every Cyrillic one: sorting the 252 universities by
# name started with "Aalto University" and pushed all 111 Kazakh ones — the
# main working slice — to page six of thirteen. ICU's Russian collation orders
# Cyrillic as a reader expects, matching what the admin frontend used to do
# locally with localeCompare('ru') over a fully downloaded catalog.
#
# Shipped with postgres:16-alpine, the image all three environments run.
RU_COLLATION = "ru-RU-x-icu"


def ru_text(column: ColumnElement) -> ColumnElement:
    """Wrap a Russian-language text column so it sorts alphabetically."""
    return column.collate(RU_COLLATION)

SortOrder = Literal["asc", "desc"]


class AdminSortFieldError(Exception):
    """Unknown `sort` value. Deliberately not silently ignored: a list that
    quietly returns its default order after being asked for something else
    is indistinguishable, from the client's side, from a column whose sort
    does nothing."""

    def __init__(self, field: str, allowed: Sequence[str]) -> None:
        self.field = field
        self.allowed = list(allowed)
        super().__init__(
            f"Unknown sort field '{field}'. Sortable fields: {', '.join(self.allowed)}."
        )


def order_by_clause(
    sort: str | None,
    order: SortOrder | None,
    *,
    allowed: dict[str, Any],
    default: Sequence[Any],
    tiebreaker: Any,
) -> list[Any]:
    """`default` is used when no `sort` is given — each endpoint keeps the
    ordering it had before this parameter existed, so an un-sorted request
    returns exactly what it used to."""
    if not sort:
        return [*default, tiebreaker]

    column = allowed.get(sort)
    if column is None:
        raise AdminSortFieldError(sort, sorted(allowed))

    directed = column.desc() if order == "desc" else column.asc()
    return [nulls_last(directed), tiebreaker]
