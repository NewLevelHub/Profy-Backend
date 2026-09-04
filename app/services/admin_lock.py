from enum import Enum
from typing import Any, Iterable


def lock_fields(row, field_names: Iterable[str]) -> None:
    locked = set(row.admin_locked_fields or [])
    locked.update(field_names)
    row.admin_locked_fields = sorted(locked)


def is_locked(row, field_name: str) -> bool:
    return field_name in (row.admin_locked_fields or [])


def unlock_fields(row, field_names: Iterable[str] | None = None) -> list[str]:
    """Drop `field_names` (or every lock, when None) from admin_locked_fields,
    putting those fields back under seed control. Returns what was actually
    removed.

    Unlike a question-bank override, a lock records only the field's *name* —
    no previous value was ever kept — so unlocking cannot restore anything by
    itself. It makes the field eligible for the next seed run to overwrite,
    which is the only recovery path a lock ever had.
    """
    locked = set(row.admin_locked_fields or [])
    removed = sorted(locked if field_names is None else locked & set(field_names))
    row.admin_locked_fields = sorted(locked.difference(removed))
    return removed


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
# Each entry is {"value": <admin edit>, "bank_value": <what the bank had>}.
# The bank value is captured at override time so a revert can put the row back
# immediately instead of leaving the admin's text on screen until the next
# deploy re-runs the seed script.
#
# "The original is unknown" is expressed by the KEY BEING ABSENT, never by a
# null: plenty of overridable columns are nullable (icon, short_text, frame),
# so a null bank_value is a real value to restore, not a missing one. Only
# rows overridden before this shape existed lack the key.
_VALUE = "value"
_BANK_VALUE = "bank_value"


def _jsonable(value: Any) -> Any:
    """Enum columns (category, age_tier, instrument, ...) must reach JSONB as
    their plain value, not as the enum member."""
    return value.value if isinstance(value, Enum) else value


def _entry(value: Any, bank_value: Any) -> dict:
    return {_VALUE: _jsonable(value), _BANK_VALUE: _jsonable(bank_value)}


def _override_value(entry: Any) -> Any:
    """Reads either shape. Rows written before the nested shape existed hold
    the value directly, and a seed run can still meet one on a database that
    has not been migrated."""
    return entry[_VALUE] if isinstance(entry, dict) and _VALUE in entry else entry


def apply_overrides(row, updates: dict) -> None:
    overrides = dict(row.overrides or {})
    columns = {c.name: c for c in row.__table__.columns}
    for key, value in updates.items():
        column = columns.get(key)
        if value is None and column is not None and not column.nullable:
            raise AdminOverrideValidationError(f"{key} cannot be null")
        # The column still holds the bank's own value the first time a field
        # is edited; on a re-edit the bank value already recorded is the one
        # to keep, since the column now holds the previous admin edit.
        existing = overrides.get(key)
        bank_value = (
            existing.get(_BANK_VALUE)
            if isinstance(existing, dict) and _BANK_VALUE in existing
            else getattr(row, key)
        )
        setattr(row, key, value)
        overrides[key] = _entry(value, bank_value)
    row.overrides = overrides


def clear_overrides(row, field_names: Iterable[str] | None = None) -> list[str]:
    """Undo `field_names` (or every override, when None), restoring each
    field to the bank value recorded when it was first edited. Returns the
    fields actually cleared.

    Without this, one mistyped character permanently pinned a field: a
    resync composes overrides back over the bank on every deploy, so the
    edit survived forever and the only way out was editing the row in the
    database by hand.

    A field whose bank value was never recorded (overridden before this was
    kept) still has its override dropped — the column keeps the admin's value
    until the next seed run, which then restores the bank's."""
    overrides = dict(row.overrides or {})
    targets = sorted(overrides if field_names is None else set(overrides) & set(field_names))

    for field_name in targets:
        entry = overrides.pop(field_name)
        if isinstance(entry, dict) and _BANK_VALUE in entry:
            setattr(row, field_name, entry[_BANK_VALUE])

    row.overrides = overrides
    return targets


def effective_value(row, field_name: str, bank_value):
    overrides = row.overrides or {}
    return _override_value(overrides[field_name]) if field_name in overrides else bank_value


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
    overrides = dict(row.overrides or {})
    overrides_changed = False

    for field_name, bank_value in bank_values.items():
        target = effective_value(row, field_name, bank_value)
        if getattr(row, field_name) != target:
            setattr(row, field_name, target)
            changed = True

        # Keep the recorded bank value pointing at what the bank says *now*.
        # The bank can be re-worded while an admin override sits on top of it;
        # without this the "revert to original" the admin is offered would put
        # back a wording the bank itself no longer uses.
        entry = overrides.get(field_name)
        if isinstance(entry, dict) and (
            _BANK_VALUE not in entry or entry[_BANK_VALUE] != _jsonable(bank_value)
        ):
            overrides[field_name] = _entry(entry.get(_VALUE), bank_value)
            overrides_changed = True

    if overrides_changed:
        row.overrides = overrides
    return changed
