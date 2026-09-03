from typing import Iterable


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
def apply_overrides(row, updates: dict) -> None:
    overrides = dict(row.overrides or {})
    columns = {c.name: c for c in row.__table__.columns}
    for key, value in updates.items():
        column = columns.get(key)
        if value is None and column is not None and not column.nullable:
            raise AdminOverrideValidationError(f"{key} cannot be null")
        setattr(row, key, value)
        overrides[key] = value
    row.overrides = overrides


def effective_value(row, field_name: str, bank_value):
    overrides = row.overrides or {}
    return overrides[field_name] if field_name in overrides else bank_value


def has_overrides(row) -> bool:
    return bool(row.overrides)


def sync_fields(row, bank_values: dict) -> bool:
    """One call replacing the `target = effective_value(row, name, value);
    if row.name != target: ...` triple repeated per field across every
    scripts/seed_*.py — for each `field_name -> bank_value` pair, syncs
    `bank_value` in unless the field is admin-overridden, in which case the
    override is kept. Returns whether anything actually changed, so callers
    can still report their own updated/skipped counts."""
    changed = False
    for field_name, bank_value in bank_values.items():
        target = effective_value(row, field_name, bank_value)
        if getattr(row, field_name) != target:
            setattr(row, field_name, target)
            changed = True
    return changed
