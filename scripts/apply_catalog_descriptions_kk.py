#!/usr/bin/env python
"""KZ-504/505 — Kazakh overlay for University / Program descriptions.

ONE script, ONE data file: ``scripts/data/catalog_descriptions_kk.json``.

    {
      "universities":     [ {"slugs": ["nu"],             "ru": "...", "kk": "..."} ],
      "programs":         [ {"rows":  [["nu", "Physics"]], "ru": "...", "kk": "..."} ],
      "university_names": [ {"slug":  "nu",                "ru": "...", "kk": "..."} ],
      "program_names":    [ {"ru": "Юриспруденция", "kk": "...", "slugs": ["nu"]} ]
    }

``universities`` / ``programs``: one entry per *distinct* RU description;
``slugs`` / ``rows`` list every catalog row it covers. ``university_names`` /
``program_names``: one entry per Kazakhstan university / distinct KZ program
name whose ``name`` has a Kazakh form (KZ-206 follow-up) — written to
``name_i18n['kk']``; ``slugs`` on a ``program_names`` entry are the
universities that offer a program with that exact ``ru`` name. ``ru`` is the
source string (used to locate the row and for native review); ``kk`` is what
gets written. To fix a translation, edit ``kk`` in place and re-run ``apply``.

Subcommands
-----------
apply   catalog file -> ``description_i18n['kk']`` JSONB in the DB. Idempotent,
        writes only the ``*_i18n`` overlay, never the ``ru`` base column. This
        is the only step wired into a runbook (``start.sh``, right after
        ``build_universities.py``). Needs the DB.

dump    DB rows whose RU description has no ``kk`` entry yet -> a todo file
        ``scripts/data/catalog_descriptions_kk.todo.json`` (same shape, empty
        ``kk``). Use it when universities/programs were added and need
        translating. Needs the DB.

merge   fold a filled-in todo file back into the catalog file (dedup by RU,
        union ``slugs`` / ``rows``), rejecting any ``kk`` value that is not
        actually Kazakh. Pure JSON, no DB.

Row references are portable keys (``University.slug`` / ``University.ror_id``,
``Program`` name) resolved via ``scripts/entity_resolver.py`` — never raw
UUIDs (PRO-244).

Run inside Docker:
    docker compose exec api python scripts/apply_catalog_descriptions_kk.py apply
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import select

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from scripts.entity_resolver import resolve_program, resolve_university

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "data" / "catalog_descriptions_kk.json"
TODO = HERE / "data" / "catalog_descriptions_kk.todo.json"

_KZ_COUNTRIES = ("Казахстан", "Қазақстан")
_KK_CHARS = set("әғқңөұүһі")


_CYRILLIC_RE = re.compile(r"[а-яёұүөқғңһәі]", re.IGNORECASE)
# leading / trailing non-letter, non-Cyrillic characters on a token
# ("IT," -> "IT", "«Нархоз»." -> "Нархоз", "2026)" -> "2026")
_WORD_TRIM = re.compile(r"^[^\wЀ-ӿ]+|[^\wЀ-ӿ]+$")


def is_kazakh(text: str) -> bool:
    """Catch a value the translator left in *Russian*. Deliberately permissive
    (it only gates whether the string is written to `description_i18n['kk']`):

    * a very short string, or one with no Cyrillic words at all
      ("Data Science, MBA"), passes — it is not Russian prose;
    * Latin abbreviations / years are ignored even with attached punctuation
      ("IT,", "MBA.", "2026)") so they don't dilute the Cyrillic ratio.

    Only text whose Cyrillic words are mostly *without* a Kazakh-specific
    letter is rejected. The real quality gate is `tests/guard/`."""
    text = (text or "").strip()
    if len(text) < 4:
        return True
    non_latin = kk = 0
    for raw in text.split():
        word = _WORD_TRIM.sub("", raw)
        if not word or word.isascii():  # Latin token, number, or pure punctuation
            continue
        non_latin += 1
        if any(c.lower() in _KK_CHARS for c in word):
            kk += 1
    if non_latin == 0:
        return True  # nothing Cyrillic to judge
    return kk / non_latin >= 0.25


def is_kazakh_name(kk: str, ru: str) -> bool:
    """Loose sanity check for official names / field-of-study titles. Many are
    valid Kazakh with no Kazakh-specific letter ("Кайнар академиясы") or
    spelled identically in both languages ("Биология", "Информатика"), so the
    `is_kazakh` heuristic is wrong here. Require only: non-empty and made of
    real letters (Cyrillic or Latin), not whitespace/punctuation junk. These
    are curated + native-reviewed anyway."""
    kk = (kk or "").strip()
    return len(kk) >= 2 and any(c.isalpha() for c in kk)


_SECTIONS = ("universities", "programs", "university_names", "program_names")


def _load_catalog() -> dict:
    if not CATALOG.exists():
        return {s: [] for s in _SECTIONS}
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    for s in _SECTIONS:
        data.setdefault(s, [])
    return data


def _sort_catalog(data: dict) -> None:
    # `.get(..., [""])[0]` etc. keep an entry with an empty ref list sortable
    # rather than raising IndexError (such an entry does nothing on `apply`,
    # but must not crash the write).
    data["universities"].sort(key=lambda e: (e.get("slugs") or [""])[0])
    data["programs"].sort(
        key=lambda e: tuple((e.get("rows") or [["", ""]])[0][:2])
    )
    data["university_names"].sort(key=lambda e: e.get("slug", ""))
    data["program_names"].sort(key=lambda e: e.get("ru", ""))


def _write_catalog(data: dict) -> None:
    _sort_catalog(data)
    ordered = {
        "_about": data.get("_about")
        or (
            "KZ-504/505 Kazakh overlay for the university/program catalog. "
            "`universities` / `programs`: one entry per distinct RU description. "
            "`university_names` / `program_names`: name_i18n['kk'] for Kazakhstan "
            "universities and their programs (KZ-206 follow-up). Edit `kk` in "
            "place; `apply` writes it to JSONB."
        ),
        **{s: data[s] for s in _SECTIONS},
    }
    CATALOG.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _uni_kwargs(key: str) -> dict:
    """catalog `university_key` -> entity_resolver.resolve_university kwargs."""
    if key.startswith("jinaq:"):
        return {"jinaq_external_id": key.split(":", 1)[1]}
    if key.startswith("ror:"):
        return {"ror_id": key.split(":", 1)[1]}
    return {"slug": key}


def _portable_key(uni: University) -> str | None:
    if uni.slug:
        return uni.slug
    if uni.ror_id:
        return f"ror:{uni.ror_id}"
    return None


# ── apply ───────────────────────────────────────────────────────────────────

async def _apply(dry_run: bool) -> int:
    data = _load_catalog()
    ok = {"uni": 0, "prog": 0, "name": 0, "pname": 0}
    miss = {"uni": 0, "prog": 0, "name": 0, "pname": 0}
    bad = {"uni": 0, "prog": 0, "name": 0, "pname": 0}
    unresolved: list = []

    async with async_session() as db:
        for entry in data["university_names"]:
            kk = (entry.get("kk") or "").strip()
            if not is_kazakh_name(kk, entry.get("ru", "")):
                bad["name"] += 1
                continue
            uni, _by = await resolve_university(db, **_uni_kwargs(entry["slug"]))
            if uni is None:
                miss["name"] += 1
                unresolved.append(entry["slug"])
                continue
            uni.name_i18n = {**(uni.name_i18n or {}), "kk": kk}
            db.add(uni)
            ok["name"] += 1

        for entry in data["program_names"]:
            kk = (entry.get("kk") or "").strip()
            if not is_kazakh_name(kk, entry.get("ru", "")):
                bad["pname"] += 1
                continue
            for slug in entry["slugs"]:
                uni, _by = await resolve_university(db, **_uni_kwargs(slug))
                prog = (
                    await resolve_program(db, university=uni, name=entry["ru"])
                    if uni is not None
                    else None
                )
                if prog is None:
                    miss["pname"] += 1
                    unresolved.append([slug, entry["ru"]])
                    continue
                prog.name_i18n = {**(prog.name_i18n or {}), "kk": kk}
                db.add(prog)
                ok["pname"] += 1

        for entry in data["universities"]:
            kk = (entry.get("kk") or "").strip()
            if not is_kazakh(kk):
                bad["uni"] += 1
                continue
            for key in entry["slugs"]:
                uni, _by = await resolve_university(db, **_uni_kwargs(key))
                if uni is None:
                    miss["uni"] += 1
                    unresolved.append(key)
                    continue
                uni.description_i18n = {**(uni.description_i18n or {}), "kk": kk}
                db.add(uni)
                ok["uni"] += 1

        for entry in data["programs"]:
            kk = (entry.get("kk") or "").strip()
            if not is_kazakh(kk):
                bad["prog"] += 1
                continue
            for uni_key, name in entry["rows"]:
                uni, _by = await resolve_university(db, **_uni_kwargs(uni_key))
                prog = (
                    await resolve_program(db, university=uni, name=name)
                    if uni is not None
                    else None
                )
                if prog is None:
                    miss["prog"] += 1
                    unresolved.append([uni_key, name])
                    continue
                prog.description_i18n = {**(prog.description_i18n or {}), "kk": kk}
                db.add(prog)
                ok["prog"] += 1

        if dry_run:
            await db.rollback()
        else:
            await db.commit()

    print(
        f"uni names:    {ok['name']} applied, {miss['name']} unresolved, "
        f"{bad['name']} skipped (failed kk check)"
    )
    print(
        f"prog names:   {ok['pname']} applied, {miss['pname']} unresolved, "
        f"{bad['pname']} skipped (failed kk check)"
    )
    print(
        f"uni descr:    {ok['uni']} applied, {miss['uni']} unresolved, "
        f"{bad['uni']} skipped (failed kk check)"
    )
    print(
        f"programs:     {ok['prog']} applied, {miss['prog']} unresolved, "
        f"{bad['prog']} skipped (failed kk check)"
    )
    if dry_run:
        print("(--dry-run: rolled back, nothing written)")
    if any(bad.values()):
        # a few bad values are the CI guard's job (tests/guard); a warning here
        # is enough and must not abort `start.sh`.
        print("WARNING: some kk values look non-Kazakh and were NOT applied — "
              "run `merge`/native review to fix catalog_descriptions_kk.json")

    total_entries = sum(len(data[s]) for s in _SECTIONS)
    total_ok = sum(ok.values())
    total_miss = sum(miss.values())
    if unresolved:
        # a catalog row can legitimately reference a university/program absent
        # from this particular DB snapshot — informational up to a point.
        print(f"note: {total_miss} row ref(s) did not resolve on this DB; "
              f"sample: {unresolved[:5]}")

    # Hard fail: the file has entries but nothing landed in the DB. Almost
    # always a stale catalog file or slug-canonicalization drift in
    # build_universities.py (it has renamed ~220 slugs before). Without a
    # non-zero exit `start.sh` / CD would sail past this and ship an empty
    # Kazakh catalog, unnoticed until kk is turned on.
    if total_entries and total_ok == 0:
        print(f"ERROR: {total_entries} catalog entries but 0 applied — stale "
              f"file or slug drift. Not treating this as success.")
        return 2
    # Soft alarm: most refs missed. Not fatal (a partial snapshot is legal),
    # but it should be loud in the CD log.
    if total_ok and total_miss > total_ok:
        print(f"WARNING: {total_miss} refs unresolved vs {total_ok} applied — "
              f"check the catalog file against this DB's slugs.")
    return 0


# ── dump ────────────────────────────────────────────────────────────────────

async def _dump(only_kz: bool, kinds: set[str]) -> None:
    data = _load_catalog()
    have_uni = {e["ru"].strip() for e in data["universities"]}
    have_prog = {e["ru"].strip() for e in data["programs"]}
    have_name = {e["slug"] for e in data["university_names"]}
    have_pname = {e["ru"].strip() for e in data["program_names"]}
    todo: dict = {s: [] for s in _SECTIONS}

    async with async_session() as db:
        if "name" in kinds:
            q = select(University).where(University.name.op("~")("[А-Яа-яЁё]"))
            if only_kz:
                q = q.where(University.country.in_(_KZ_COUNTRIES))
            names = []
            for uni in (await db.execute(q)).scalars():
                key = _portable_key(uni)
                if key is None or key in have_name:
                    continue
                names.append({"slug": key, "ru": uni.name, "kk": ""})
            todo["university_names"] = sorted(names, key=lambda e: e["slug"])

        if "progname" in kinds:
            q = (
                select(Program, University)
                .join(University, Program.university_id == University.id)
                .where(Program.name.op("~")("[А-Яа-яЁё]"))
            )
            if only_kz:
                q = q.where(University.country.in_(_KZ_COUNTRIES))
            by_ru: dict[str, set[str]] = {}
            for prog, uni in (await db.execute(q)).all():
                ru = (prog.name or "").strip()
                if not ru or ru in have_pname:
                    continue
                key = _portable_key(uni)
                if key is not None:
                    by_ru.setdefault(ru, set()).add(key)
            todo["program_names"] = [
                {"ru": ru, "kk": "", "slugs": sorted(keys)}
                for ru, keys in sorted(by_ru.items())
            ]

        if "university" in kinds:
            q = select(University).where(University.description.isnot(None))
            if only_kz:
                q = q.where(University.country.in_(_KZ_COUNTRIES))
            by_ru: dict[str, set[str]] = {}
            for uni in (await db.execute(q)).scalars():
                ru = (uni.description or "").strip()
                if not ru or ru in have_uni:
                    continue
                key = _portable_key(uni)
                if key is not None:
                    by_ru.setdefault(ru, set()).add(key)
            todo["universities"] = [
                {"slugs": sorted(keys), "ru": ru, "kk": ""}
                for ru, keys in sorted(by_ru.items())
            ]

        if "program" in kinds:
            q = (
                select(Program, University)
                .join(University, Program.university_id == University.id)
                .where(Program.description.isnot(None))
            )
            if only_kz:
                q = q.where(University.country.in_(_KZ_COUNTRIES))
            by_ru: dict[str, list] = {}
            for prog, uni in (await db.execute(q)).all():
                ru = (prog.description or "").strip()
                if not ru or ru in have_prog:
                    continue
                key = _portable_key(uni)
                if key is not None:
                    by_ru.setdefault(ru, []).append([key, prog.name])
            todo["programs"] = [
                {"rows": sorted(rows), "ru": ru, "kk": ""}
                for ru, rows in sorted(by_ru.items())
            ]

    TODO.write_text(
        json.dumps(todo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    counts = {s: len(todo[s]) for s in _SECTIONS}
    if not any(counts.values()):
        print("nothing to translate — catalog is complete for this DB")
        return
    print(f"wrote {TODO.name}: " + ", ".join(
        f"{n} {s}" for s, n in counts.items() if n))
    print("fill in every empty \"kk\", then: "
          "python scripts/apply_catalog_descriptions_kk.py merge")


# ── merge ───────────────────────────────────────────────────────────────────

def _merge() -> int:
    if not TODO.exists():
        raise SystemExit(f"no {TODO.name} — run `dump` first")
    todo = json.loads(TODO.read_text(encoding="utf-8"))
    data = _load_catalog()

    added = updated = rejected = 0
    samples: list = []

    def _reject(section: str, ru: str, kk: str, why: str) -> None:
        nonlocal rejected
        rejected += 1
        if len(samples) < 15:
            samples.append((section, why, ru[:50], kk[:50]))

    # university_names: flat {slug, ru, kk}, keyed by slug (looser kk check).
    names_index = {e["slug"]: e for e in data["university_names"]}
    for entry in todo.get("university_names", []):
        kk = (entry.get("kk") or "").strip()
        if not kk:
            continue
        slug = (entry.get("slug") or "").strip()
        if not slug:
            _reject("university_names", entry.get("ru", ""), kk, "empty slug")
            continue
        if not is_kazakh_name(kk, entry.get("ru", "")):
            _reject("university_names", entry.get("ru", ""), kk, "not kk")
            continue
        cur = names_index.get(slug)
        if cur is None:
            new = {"slug": slug, "ru": entry.get("ru", ""), "kk": kk}
            data["university_names"].append(new)
            names_index[slug] = new
            added += 1
        elif cur.get("kk") != kk:
            cur["kk"] = kk
            updated += 1

    # program_names: {ru, kk, slugs}, keyed by ru name (looser kk check).
    pn_index = {e["ru"].strip(): e for e in data["program_names"]}
    for entry in todo.get("program_names", []):
        kk = (entry.get("kk") or "").strip()
        if not kk:
            continue
        ru = (entry.get("ru") or "").strip()
        slugs = sorted(s for s in (entry.get("slugs") or []) if s)
        if not is_kazakh_name(kk, ru):
            _reject("program_names", ru, kk, "not kk")
            continue
        cur = pn_index.get(ru)
        if cur is None:
            if not slugs:
                _reject("program_names", ru, kk, "empty slugs (new entry)")
                continue
            new = {"ru": ru, "kk": kk, "slugs": slugs}
            data["program_names"].append(new)
            pn_index[ru] = new
            added += 1
        else:
            cur["slugs"] = sorted(set(cur.get("slugs", [])) | set(slugs))
            if cur.get("kk") != kk:
                cur["kk"] = kk
                updated += 1

    for section, ref_key in (("universities", "slugs"), ("programs", "rows")):
        index = {e["ru"].strip(): e for e in data[section]}
        for entry in todo.get(section, []):
            kk = (entry.get("kk") or "").strip()
            if not kk:
                continue
            ru = (entry.get("ru") or "").strip()
            refs = [r for r in (entry.get(ref_key) or []) if r]
            if not is_kazakh(kk):
                _reject(section, ru, kk, "not kk")
                continue
            cur = index.get(ru)
            if cur is None:
                if not refs:
                    _reject(section, ru, kk, "empty refs (new entry)")
                    continue
                new = {ref_key: sorted(refs), "ru": ru, "kk": kk}
                data[section].append(new)
                index[ru] = new
                added += 1
            else:
                merged = cur.get(ref_key, [])
                for ref in refs:
                    if ref not in merged:
                        merged.append(ref)
                cur[ref_key] = sorted(merged)
                if cur.get("kk") != kk:
                    cur["kk"] = kk
                    updated += 1

    _write_catalog(data)
    print(f"merged into {CATALOG.name}: +{added} new, {updated} kk changed, "
          f"{rejected} rejected")
    for section, why, ru, kk in samples:
        print(f"  reject [{section}] {why}: {ru!r} -> {kk!r}")
    return 1 if rejected else 0


# ── cli ─────────────────────────────────────────────────────────────────────

def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("apply", help="catalog file -> description_i18n['kk'] in the DB")
    a.add_argument("--dry-run", action="store_true", help="resolve + report, then roll back")

    d = sub.add_parser("dump", help="DB rows lacking a kk translation -> todo file")
    d.add_argument("--only-kz", action="store_true", help="Kazakhstan universities only")
    d.add_argument(
        "--kind",
        choices=["university", "program", "name", "progname", "all"], default="all",
        help="'name'/'progname' = University.name / Program.name overrides; "
             "'university'/'program' = descriptions",
    )

    sub.add_parser("merge", help="fold a filled-in todo file into the catalog file")

    args = ap.parse_args()
    if args.cmd == "apply":
        raise SystemExit(asyncio.run(_apply(args.dry_run)))
    elif args.cmd == "dump":
        kinds = (
            {"university", "program", "name", "progname"}
            if args.kind == "all" else {args.kind}
        )
        asyncio.run(_dump(args.only_kz, kinds))
    elif args.cmd == "merge":
        raise SystemExit(_merge())


if __name__ == "__main__":
    main()
