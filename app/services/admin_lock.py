from collections.abc import Collection, Iterable


def lock_fields(row, field_names: Iterable[str]) -> None:
    locked = set(row.admin_locked_fields or [])
    locked.update(field_names)
    row.admin_locked_fields = sorted(locked)


def is_locked(row, field_name: str) -> bool:
    return field_name in (row.admin_locked_fields or [])


class AdminOverrideValidationError(Exception):
    """Raised by apply_overrides() instead of letting a bad PATCH reach the
    DB as an uncaught IntegrityError. Deliberately not a ValueError subclass
    — admin routers already catch plain ValueError to mean "row not found"
    (404); this needs its own except clause mapped to 422."""


# Question-bank content (Question/QuestionPair/MotivationStatement/
# MotivationPair/Direction) uses a value-carrying `overrides` dict instead of
# `admin_locked_fields` above — bank-seeded rows can be deleted by a reseed,
# not just have fields reverted, so the override needs to be recoverable from
# the row itself. See docs/admin-questions-content-overrides-plan.md.
def apply_overrides(
    row,
    updates: dict,
    *,
    localized_fields: Collection[str] = (),
    locale: str | None = None,
) -> None:
    """`localized_fields` names which of `row`'s columns hold a `{locale:
    value}` JSONB map (post the questions/pairs/motivation/directions
    single-row-per-item redesign — see docs/i18n-contract.md §8) rather than
    a plain scalar. For those fields `updates[key]` is the value for ONE
    locale (the admin edits one language at a time), given via `locale`; it
    is merged into both the live column's map and `overrides[key]`'s map,
    leaving the other locale's value untouched. Non-localized fields behave
    exactly as before (bare value, no `locale` needed)."""
    overrides = dict(row.overrides or {})
    columns = {c.name: c for c in row.__table__.columns}
    for key, value in updates.items():
        column = columns.get(key)
        if key in localized_fields:
            if not locale:
                raise AdminOverrideValidationError(f"locale is required to edit {key}")
            if value is None and column is not None and not column.nullable:
                raise AdminOverrideValidationError(f"{key} cannot be null")
            current_map = dict(getattr(row, key) or {})
            current_map[locale] = value
            setattr(row, key, current_map)
            override_map = dict(overrides.get(key) or {})
            override_map[locale] = value
            overrides[key] = override_map
        else:
            if value is None and column is not None and not column.nullable:
                raise AdminOverrideValidationError(f"{key} cannot be null")
            setattr(row, key, value)
            overrides[key] = value
    row.overrides = overrides


def effective_value(row, field_name: str, bank_value, *, localized: bool = False):
    overrides = row.overrides or {}
    if field_name not in overrides:
        return bank_value
    if not localized:
        return overrides[field_name]
    # `bank_value` is the full `{locale: value}` map from the bank; the
    # admin's override only ever pins specific locale(s) within it, so merge
    # rather than replace — an override on `kk` must not discard a `ru`
    # value the bank still supplies.
    merged = dict(bank_value or {})
    merged.update(overrides[field_name])
    return merged


def has_overrides(row) -> bool:
    return bool(row.overrides)


def sync_fields(row, bank_values: dict, *, localized_fields: Collection[str] = ()) -> bool:
    """One call replacing the `target = effective_value(row, name, value);
    if row.name != target: ...` triple repeated per field across every
    scripts/seed_*.py — for each `field_name -> bank_value` pair, syncs
    `bank_value` in unless the field is admin-overridden, in which case the
    override is kept. Returns whether anything actually changed, so callers
    can still report their own updated/skipped counts."""
    changed = False
    for field_name, bank_value in bank_values.items():
        target = effective_value(row, field_name, bank_value, localized=field_name in localized_fields)
        if getattr(row, field_name) != target:
            setattr(row, field_name, target)
            changed = True
    return changed
