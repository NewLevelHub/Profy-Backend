from typing import Iterable


def lock_fields(row, field_names: Iterable[str]) -> None:
    locked = set(row.admin_locked_fields or [])
    locked.update(field_names)
    row.admin_locked_fields = sorted(locked)


def is_locked(row, field_name: str) -> bool:
    return field_name in (row.admin_locked_fields or [])


# Question-bank content (Question/QuestionPair/MotivationStatement/
# MotivationPair/Direction) uses a value-carrying `overrides` dict instead of
# `admin_locked_fields` above — bank-seeded rows can be deleted by a reseed,
# not just have fields reverted, so the override needs to be recoverable from
# the row itself. See docs/admin-questions-content-overrides-plan.md.
def apply_overrides(row, updates: dict) -> None:
    overrides = dict(row.overrides or {})
    for key, value in updates.items():
        setattr(row, key, value)
        overrides[key] = value
    row.overrides = overrides


def effective_value(row, field_name: str, bank_value):
    overrides = row.overrides or {}
    return overrides[field_name] if field_name in overrides else bank_value


def has_overrides(row) -> bool:
    return bool(row.overrides)
