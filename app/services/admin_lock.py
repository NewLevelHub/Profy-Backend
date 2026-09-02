from typing import Iterable


def lock_fields(row, field_names: Iterable[str]) -> None:
    locked = set(row.admin_locked_fields or [])
    locked.update(field_names)
    row.admin_locked_fields = sorted(locked)


def is_locked(row, field_name: str) -> bool:
    return field_name in (row.admin_locked_fields or [])
