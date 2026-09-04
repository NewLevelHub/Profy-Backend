"""Guardrail: no checked-in review/data file may identify a University or
Program row *only* by a bare `uuid4()` primary key.

Those ids are generated independently per row per database, so a hardcoded
`University.id` / `Program.id` snapshotted from one database resolves to
nothing on any other one — the apply script then silently no-ops on every
entry (this is PRO-244; it already bit `apply_uniranks_world_rank.py` and
`apply_foreign_university_dedup.py`). Every such reference must travel with
a cross-DB-portable key — `slug` / `university_slug` / `jinaq_external_id` /
`ror_id` for a University, and a program *name* (resolved under its parent
University) for a Program — so `scripts/entity_resolver.py` can re-resolve
it against whatever database the script is run on.

Files that still violate this are listed in `_ALLOWLIST` with the ticket
that will fix them; that entry must be deleted in the same change that
makes the file compliant (the test fails if an allowlisted file has become
clean).
"""
import json
import re
from pathlib import Path

import pytest

from scripts.entity_resolver import portable_keys

_REPO_ROOT = Path(__file__).resolve().parents[2]

_UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# Record fields whose value (or list of values) is a reference to a row.
_UNIVERSITY_REF_FIELDS = ("university_id", "keep", "remove", "jinaq_university_id")
_PROGRAM_REF_FIELDS = ("program_id", "program_ids")

# A University ref is safe if the record also carries any of these.
_UNIVERSITY_PORTABLE_FIELDS = (
    "slug",
    "university_slug",
    "jinaq_external_id",
    "external_id",
    "ror_id",
    "keep_slug",
    "remove_slug",
    "keep_ror_id",
    "remove_ror_id",
)

# path (posix, relative to repo root) -> ticket that removes it
_ALLOWLIST = {
    "scripts/data/uniranks_world_rank_review.json": "PRO-245",
    "scripts/data/foreign_university_dedup_review.json": "PRO-247",
    "scripts/program_requirements_review_2027.json": "PRO-246 follow-up (regenerate with per-program names)",
}


def _iter_files() -> list[Path]:
    seen: set[Path] = set()
    for pattern in ("scripts/data/**/*.json", "scripts/*review*.json"):
        for path in _REPO_ROOT.glob(pattern):
            if path.is_file():
                seen.add(path)
    return sorted(seen)


def _is_uuid(value: object) -> bool:
    return isinstance(value, str) and bool(_UUID_RE.match(value))


def _iter_records(data: object):
    """Yield (locator, record_dict, key_ref) for every row-like record in a
    parsed review file. `key_ref` is the dict key when it is itself a bare
    uuid row reference (the `db_updates_2026.json` shape), else None.
    """
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                yield f"[{i}]", item, None
    elif isinstance(data, dict):
        nested = [k for k in ("merges", "no_action", "entries", "specialties") if isinstance(data.get(k), list)]
        if nested:
            for k in nested:
                for i, item in enumerate(data[k]):
                    if isinstance(item, dict):
                        yield f"{k}[{i}]", item, None
        elif data and all(isinstance(v, dict) for v in data.values()):
            for key, value in data.items():
                yield f"[{key!r}]", value, key if _is_uuid(key) else None
        else:
            yield "<root>", data, None


def _violations_in(path: Path) -> list[str]:
    data = json.loads(path.read_text(encoding="utf-8"))
    out: list[str] = []
    for locator, record, key_ref in _iter_records(data):
        uni_refs: list[str] = []
        prog_refs: list[str] = []

        for field in _UNIVERSITY_REF_FIELDS:
            if _is_uuid(record.get(field)):
                uni_refs.append(field)
        for field in _PROGRAM_REF_FIELDS:
            value = record.get(field)
            if _is_uuid(value):
                prog_refs.append(field)
            elif isinstance(value, list) and any(_is_uuid(v) for v in value):
                prog_refs.append(field)
        if key_ref is not None:
            prog_refs.append("<dict key>")

        if not uni_refs and not prog_refs:
            continue

        record_portable = portable_keys(record)

        if uni_refs and not any(record.get(f) for f in _UNIVERSITY_PORTABLE_FIELDS):
            out.append(f"{locator}: University ref via {uni_refs} with no portable key")

        # A Program ref needs a program *name* to resolve under its University;
        # a bare university_slug is not enough (can't tell which program).
        if prog_refs:
            has_name = bool(record.get("name") or record.get("program_name") or record.get("programs"))
            has_univ = bool(record.get("university_slug") or record.get("slug") or record_portable)
            if not (has_name and has_univ):
                out.append(f"{locator}: Program ref via {prog_refs} with no (program name + university) pair")

    return out


def test_no_review_file_identifies_rows_only_by_bare_uuid():
    offenders: dict[str, list[str]] = {}
    allowlisted_now_clean: list[str] = []

    for path in _iter_files():
        rel = path.relative_to(_REPO_ROOT).as_posix()
        violations = _violations_in(path)
        if rel in _ALLOWLIST:
            if not violations:
                allowlisted_now_clean.append(rel)
        elif violations:
            offenders[rel] = violations

    assert not allowlisted_now_clean, (
        "These files are compliant now — delete their _ALLOWLIST entry: "
        + ", ".join(allowlisted_now_clean)
    )
    assert not offenders, "Review files reference rows only by bare uuid:\n" + "\n".join(
        f"  {rel}:\n" + "\n".join(f"    {v}" for v in vs) for rel, vs in offenders.items()
    )


def test_foreign_university_photo_review_carries_portable_key():
    """Positive check: the reference-quality review file keeps a slug on
    every record (regression canary for the pattern this test enforces)."""
    path = _REPO_ROOT / "scripts/data/foreign_university_photo_review.json"
    entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
    assert entries and all(e.get("university_slug") for e in entries)
