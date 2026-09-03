"""The `locale` column shared by every bank-seeded content table (KZ-301)."""

from sqlalchemy import Enum
from sqlalchemy.orm import Mapped, mapped_column

from app.i18n import DEFAULT_LOCALE, KNOWN_LOCALES


def locale_column() -> Mapped[str]:
    """Build the `locale` column for a bank-seeded content table.

    One logical content unit = one row per locale, keyed
    ``(<natural_key>, locale)`` — each model declares that composite unique in
    its own ``__table_args__``. Structural columns (order, age_tier, scoring
    codes, holland_code, category, …) are identical across a logical row's
    locales; ``scripts/seed_*.py`` keeps it that way and only touches the
    locales its bank carries.

    Call this once per model — a ``mapped_column`` instance can't be shared
    between mapped classes. Plain-string ``Enum`` (values, not a Python enum
    class), so ``row.locale`` is a ``str``. Values come from ``KNOWN_LOCALES``
    so model and persistence contract can't drift; the ``locale_enum`` Postgres
    type is owned by Alembic (migration ``d80fbf5d1f43``).
    """
    return mapped_column(
        Enum(*KNOWN_LOCALES, name="locale_enum", create_type=False),
        nullable=False,
        server_default=DEFAULT_LOCALE,
        index=True,
    )
