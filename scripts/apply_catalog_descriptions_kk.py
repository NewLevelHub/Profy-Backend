#!/usr/bin/env python
"""KZ-504/505 — Kazakh overlay for University / Program descriptions.

ONE script, ONE data file: ``scripts/data/catalog_descriptions_kk.json``.

    {
      "universities": [ {"slugs": ["nu"],            "ru": "...", "kk": "..."} ],
      "programs":     [ {"rows":  [["nu", "Physics"]], "ru": "...", "kk": "..."} ]
    }

One entry per *distinct* RU string; ``slugs`` / ``rows`` list every catalog row
it covers. ``ru`` is the source string (used both to locate the row and for
native review); ``kk`` is what gets written. To fix a translation, edit ``kk``
in place and re-run ``apply``.

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


def is_kazakh(text: str) -> bool:
    """Fuzzy heuristic shared with the other KZ-50x apply scripts: of the
    non-Latin words in ``text``, at least a quarter must carry a
    Kazakh-specific letter. Short strings are treated as suspicious."""
    text = (text or "").strip()
    if len(text) < 4:
        return False
    non_latin = kk = 0
    for word in text.split():
        if all(c.isalpha() and c.isascii() for c in word):
            continue
        non_latin += 1
        if any(c.lower() in _KK_CHARS for c in word):
            kk += 1
    return non_latin > 0 and kk / non_latin >= 0.25


def _load_catalog() -> dict:
    if not CATALOG.exists():
        return {"universities": [], "programs": []}
    data = json.loads(CATALOG.read_text(encoding="utf-8"))
    data.setdefault("universities", [])
    data.setdefault("programs", [])
    return data


def _sort_catalog(data: dict) -> None:
    data["universities"].sort(key=lambda e: e["slugs"][0])
    data["programs"].sort(key=lambda e: (e["rows"][0][0], e["rows"][0][1]))


def _write_catalog(data: dict) -> None:
    _sort_catalog(data)
    ordered = {
        "_about": data.get("_about")
        or (
            "KZ-504/505 Kazakh overlay for University.description / "
            "Program.description. One entry per distinct RU string. Edit `kk` "
            "in place; `apply` writes it to the description_i18n JSONB."
        ),
        "universities": data["universities"],
        "programs": data["programs"],
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

async def _apply(dry_run: bool) -> None:
    data = _load_catalog()
    ok = {"uni": 0, "prog": 0}
    miss = {"uni": 0, "prog": 0}
    bad = {"uni": 0, "prog": 0}
    unresolved: list = []

    async with async_session() as db:
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
        f"universities: {ok['uni']} applied, {miss['uni']} unresolved, "
        f"{bad['uni']} skipped (failed kk check)"
    )
    print(
        f"programs:     {ok['prog']} applied, {miss['prog']} unresolved, "
        f"{bad['prog']} skipped (failed kk check)"
    )
    if dry_run:
        print("(--dry-run: rolled back, nothing written)")
    if bad["uni"] or bad["prog"]:
        # not fatal here — the CI guard (tests/guard) is the quality gate; this
        # is a dev/CD bootstrap step and must not abort `start.sh`.
        print("WARNING: some kk values look non-Kazakh and were NOT applied — "
              "run `merge`/native review to fix catalog_descriptions_kk.json")
    if unresolved:
        # a catalog row can legitimately reference a university/program that is
        # absent from this particular DB snapshot — informational, not an error.
        print(f"note: {len(unresolved)} row ref(s) did not resolve on this DB; "
              f"sample: {unresolved[:5]}")


# ── dump ────────────────────────────────────────────────────────────────────

async def _dump(only_kz: bool, kinds: set[str]) -> None:
    data = _load_catalog()
    have_uni = {e["ru"].strip() for e in data["universities"]}
    have_prog = {e["ru"].strip() for e in data["programs"]}
    todo: dict = {"universities": [], "programs": []}

    async with async_session() as db:
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
    n_u, n_p = len(todo["universities"]), len(todo["programs"])
    if not n_u and not n_p:
        print("nothing to translate — catalog is complete for this DB")
        return
    print(f"wrote {TODO.name}: {n_u} universities + {n_p} programs still to translate")
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
    for section, ref_key in (("universities", "slugs"), ("programs", "rows")):
        index = {e["ru"].strip(): e for e in data[section]}
        for entry in todo.get(section, []):
            kk = (entry.get("kk") or "").strip()
            if not kk:
                continue
            if not is_kazakh(kk):
                rejected += 1
                if len(samples) < 15:
                    samples.append((section, entry["ru"][:60], kk[:60]))
                continue
            ru = entry["ru"].strip()
            refs = entry.get(ref_key, [])
            cur = index.get(ru)
            if cur is None:
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
          f"{rejected} rejected (not Kazakh)")
    for s in samples:
        print("  reject:", s)
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
    d.add_argument("--kind", choices=["university", "program", "all"], default="all")

    sub.add_parser("merge", help="fold a filled-in todo file into the catalog file")

    args = ap.parse_args()
    if args.cmd == "apply":
        asyncio.run(_apply(args.dry_run))
    elif args.cmd == "dump":
        kinds = {"university", "program"} if args.kind == "all" else {args.kind}
        asyncio.run(_dump(args.only_kz, kinds))
    elif args.cmd == "merge":
        raise SystemExit(_merge())


if __name__ == "__main__":
    main()
