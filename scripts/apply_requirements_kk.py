#!/usr/bin/env python
"""Kazakh dictionary for the free-text strings inside `Program.requirements`.

The admission-requirement cards on the program screen are built from raw text
in `Program.requirements` (`notes`, `exams`, `source_required_documents`,
`extracurriculars`), from `Program.language`, and from `Program.grants[]`.
None of it had a Kazakh form, so a `kk` visitor read Kazakh headings above
Russian requirement cards.

Unlike the description overlay (`apply_catalog_descriptions_kk.py`), this is
keyed by the **source string**, not by a catalog row: ~12.4k programs share
only ~4.6k distinct phrases, so one entry serves every program that uses it.
The store is therefore a plain committed dictionary, read at request time by
`app/i18n/data_strings.py` — there is no DB write step and no `apply`
subcommand; `merge` finishing is the whole deployment.

Subcommands
-----------
dump    distinct source strings still missing a `kk` entry -> a todo file
        `scripts/data/requirements_kk.todo.json`, shaped
        `{"<source>": ""}` and grouped by field in `_meta` for the translator.
        Needs the DB.

merge   fold a filled-in todo file into
        `app/i18n/data/program_requirements_kk.json`, rejecting entries whose
        value is not plausibly Kazakh or is byte-identical to the source.
        Pure JSON, no DB.

stats   coverage per field: how many distinct strings, how many translated.
        Needs the DB.

Run inside Docker:
    docker compose exec api python scripts/apply_requirements_kk.py dump
    docker compose exec api python scripts/apply_requirements_kk.py stats
    python scripts/apply_requirements_kk.py merge        # no DB needed
"""
import argparse
import asyncio
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# `dump` / `stats` need the app + DB; `merge` is pure JSON and must run on a
# bare checkout (that is the whole point of splitting it out), so the app
# imports are deferred into `_collect` rather than taken at module level.

HERE = Path(__file__).resolve().parent
STORE = HERE.parent / "app" / "i18n" / "data" / "program_requirements_kk.json"
TODO = HERE / "data" / "requirements_kk.todo.json"

_KK_CHARS = set("әғқңөұүһі")
_WORD_TRIM = re.compile(r"^[^\wЀ-ӿ]+|[^\wЀ-ӿ]+$")

# Function words that exist in Russian and not in Kazakh — their presence is
# positive evidence the value was never translated. Whole words only: "и" as a
# substring matches half the Cyrillic alphabet's worth of Kazakh words.
# Kazakh connectives and postpositions with no Russian homograph — one of
# these is strong evidence the value really was translated.
_KAZAKH_MARKERS = re.compile(
    r"(?<![\wЀ-ӿ])(және|немесе|үшін|бойынша|туралы|арқылы|болса|қажет|керек|"
    r"кейін|дейін|бірге|сондай-ақ|барлық|әрбір|бар|жоқ|мен|бен|пен)"
    r"(?![\wЀ-ӿ])",
    re.IGNORECASE,
)

_RUSSIAN_MARKERS = re.compile(
    r"(?<![\wЀ-ӿ])(и|или|для|при|по|на|с|со|из|от|до|не|что|как|если|это|"
    r"его|её|их|также|обязательн\w*|необходим\w*|требу\w+|наличие|уровн\w+)"
    r"(?![\wЀ-ӿ])",
    re.IGNORECASE,
)


def is_kazakh(text: str) -> bool:
    """Catch a value left in Russian. Same heuristic as the description
    overlay: only text whose Cyrillic words are mostly *without* a
    Kazakh-specific letter is rejected. Deliberately permissive — many real
    entries are Latin ("IELTS 6.5", "A-Levels") or Cyrillic words spelled the
    same in both languages ("Биология", "Информатика")."""
    text = (text or "").strip()
    if len(text) < 4:
        return True
    non_latin = kk = 0
    for raw in text.split():
        word = _WORD_TRIM.sub("", raw)
        if not word or not _is_cyrillic_word(word):
            continue
        non_latin += 1
        if any(c.lower() in _KK_CHARS for c in word):
            kk += 1
    if non_latin == 0:
        return True
    if kk / non_latin >= 0.25:
        return True
    # The ratio alone under-counts a sentence that is Kazakh but built from
    # words that carry no Kazakh-specific letter — "Орта мектеп дипломы немесе
    # баламасы" scores 0/5 and is perfectly good Kazakh. So take a second
    # reading from the function words, which are decisive in both directions:
    # a Kazakh connective present, and no Russian-only one.
    if _KAZAKH_MARKERS.search(text):
        return True
    return bool(kk) and not _RUSSIAN_MARKERS.search(text)


# Any Cyrillic letter, Kazakh-specific ones included.
_CYRILLIC_CHAR = re.compile(r"[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]")


def _has_cyrillic(text: str) -> bool:
    return bool(re.search(r"[А-Яа-яЁё]", text or ""))


def _is_cyrillic_word(word: str) -> bool:
    """Whether a token is Cyrillic text rather than a Latin one.

    Checked by looking for an actual Cyrillic letter, NOT by `not isascii()`:
    this catalog is full of Turkish, German and Spanish proper nouns
    ("Yabancı Uyruklu Öğrenci Sınavı", "Politécnica"), and counting those as
    Cyrillic both inflated the prose-length count and diluted the
    Kazakh-letter ratio, so a correct translation of a mostly-Turkish string
    was rejected."""
    return bool(_CYRILLIC_CHAR.search(word))


# `is_kazakh` judges by the ratio of words carrying a Kazakh-specific letter,
# which only means anything over a run of prose. Short entries — subject names,
# document names, exam titles — are the majority here and many are spelled
# identically in both languages ("Биология", "Математика", "Информатика") or
# carry no Kazakh letter at all ("Орыс тілі" does, "Диплом" does not). Judging
# those by letter ratio rejects correct translations, so anything under this
# many words gets the loose check instead (KZ-504 hit the same wall and split
# `is_kazakh` / `is_kazakh_name` for exactly this reason).
_PROSE_MIN_WORDS = 5


def _all_cyrillic_words_capitalized(text: str) -> bool:
    """Whether every Cyrillic-bearing token starts with an uppercase letter."""
    seen = False
    for raw in (text or "").split():
        word = _WORD_TRIM.sub("", raw)
        if not word or not _is_cyrillic_word(word):
            continue
        seen = True
        if not word[0].isupper():
            return False
    return seen


def _cyrillic_word_count(text: str) -> int:
    """Cyrillic words only — the Latin half of a mixed entry ("Орта мектеп
    дипломы / Zeugnis", "YÖS емтиханы (Yabancı Uyruklu Öğrenci Sınavı)") says
    nothing about whether the Cyrillic half was translated, and counting it
    pushes short labels over the prose threshold."""
    count = 0
    for raw in (text or "").split():
        word = _WORD_TRIM.sub("", raw)
        if word and _is_cyrillic_word(word):
            count += 1
    return count


def is_plausible_translation(translation: str, source: str) -> bool:
    """Whether `translation` may be written to the store.

    Prose (five or more Cyrillic words) is held to the Kazakh-letter ratio and
    must differ from its source. Shorter entries only have to be real text — an identical value is a legitimate
    outcome there ("Физика" is "Физика"), and the quality gate for them is the
    native review, not a heuristic."""
    translation = (translation or "").strip()
    if len(translation) < 2 or not any(c.isalpha() for c in translation):
        return False
    if translation == source and _has_cyrillic(source):
        # Identical is a real outcome when every Cyrillic word is a proper noun
        # or subject name — those are spelled the same in both languages, so
        # "Экономика: Математика + География." has nothing to translate. A
        # phrase carrying lowercase Russian word forms ("Портфолио творческих
        # работ") is instead one the translator left untouched.
        return _all_cyrillic_words_capitalized(translation)
    if _cyrillic_word_count(translation) < _PROSE_MIN_WORDS:
        return True
    return is_kazakh(translation)


# Where in `requirements` the free text lives. Grouping is for the translator's
# benefit only — the store itself is one flat source->translation map, because
# the same phrase can legitimately appear under two different fields.
def _strings_of(program) -> dict[str, list[str]]:
    req: dict = program.requirements or {}
    grants: list = program.grants or []
    out: dict[str, list[str]] = {
        "language": [program.language] if program.language else [],
        "exams": [str(x) for x in (req.get("exams") or [])],
        "notes": [str(x) for x in (req.get("notes") or [])],
        "source_required_documents": [
            str(x) for x in (req.get("source_required_documents") or [])
        ],
        "extracurriculars": [str(x) for x in (req.get("extracurriculars") or [])],
        "grants": [],
    }
    for g in grants:
        if not isinstance(g, dict):
            continue
        for key in ("name", "conditions"):
            value = g.get(key)
            if value:
                out["grants"].append(str(value))
    return out


def _load_store() -> dict[str, str]:
    if not STORE.exists():
        return {}
    return json.loads(STORE.read_text(encoding="utf-8"))


def _write_store(data: dict[str, str]) -> None:
    STORE.parent.mkdir(parents=True, exist_ok=True)
    # Sorted so a re-merge produces a reviewable diff, not a reshuffle.
    ordered = {k: data[k] for k in sorted(data)}
    STORE.write_text(
        json.dumps(ordered, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


async def _collect() -> dict[str, set[str]]:
    """Every distinct source string in the catalog, grouped by field."""
    from sqlalchemy import select

    from app.database import async_session
    from app.models.program import Program

    grouped: dict[str, set[str]] = {}
    async with async_session() as db:
        result = await db.execute(select(Program))
        for program in result.scalars():
            for field, values in _strings_of(program).items():
                bucket = grouped.setdefault(field, set())
                for value in values:
                    value = value.strip()
                    if value:
                        bucket.add(value)
    return grouped


async def cmd_dump(args) -> None:
    grouped = await _collect()
    store = _load_store()

    missing: dict[str, list[str]] = {}
    for field, values in sorted(grouped.items()):
        pending = sorted(v for v in values if v not in store)
        if args.cyrillic_only:
            pending = [v for v in pending if _has_cyrillic(v)]
        if pending:
            missing[field] = pending

    flat = {v: "" for values in missing.values() for v in values}
    payload = {
        "_about": (
            "Fill every value with the Kazakh translation, then run "
            "`python scripts/apply_requirements_kk.py merge`. Keys are the "
            "source strings and must not be edited. Leave a value empty to "
            "skip it (it stays Russian and is reported as a fallback)."
        ),
        "_fields": {field: len(values) for field, values in missing.items()},
        "_by_field": missing,
        "translations": flat,
    }
    TODO.parent.mkdir(parents=True, exist_ok=True)
    TODO.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    total = len(flat)
    print(f"{total} distinct string(s) still untranslated -> {TODO}")
    for field, values in missing.items():
        print(f"  {field:28} {len(values)}")


def cmd_merge(args) -> None:
    if not TODO.exists():
        sys.exit(f"no todo file at {TODO} — run `dump` first")
    payload = json.loads(TODO.read_text(encoding="utf-8"))
    incoming: dict = payload.get("translations", payload)

    store = _load_store()
    added = skipped_empty = skipped_same = skipped_not_kk = 0
    rejected: list[tuple[str, str]] = []

    for source, translation in incoming.items():
        if source.startswith("_"):
            continue
        source = source.strip()
        translation = (translation or "").strip()
        if not translation:
            skipped_empty += 1
            continue
        if not is_plausible_translation(translation, source):
            if translation == source:
                skipped_same += 1
            else:
                skipped_not_kk += 1
            rejected.append((source, translation))
            continue
        if store.get(source) != translation:
            added += 1
        store[source] = translation

    _write_store(store)
    print(f"store: {len(store)} entries -> {STORE}")
    print(f"  written/updated:      {added}")
    print(f"  skipped (empty):      {skipped_empty}")
    print(f"  skipped (unchanged):  {skipped_same}")
    print(f"  skipped (not kk):     {skipped_not_kk}")
    if rejected and args.verbose:
        print("\nrejected:")
        for source, translation in rejected[:40]:
            print(f"  {source!r} -> {translation!r}")


async def cmd_stats(args) -> None:
    grouped = await _collect()
    store = _load_store()
    print(f"{'field':28} {'distinct':>9} {'translated':>11} {'coverage':>9}")
    total = done = 0
    for field, values in sorted(grouped.items()):
        n = len(values)
        k = sum(1 for v in values if store.get(v))
        total += n
        done += k
        pct = f"{(k / n * 100):.0f}%" if n else "—"
        print(f"{field:28} {n:>9} {k:>11} {pct:>9}")
    pct = f"{(done / total * 100):.0f}%" if total else "—"
    print(f"{'TOTAL':28} {total:>9} {done:>11} {pct:>9}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_dump = sub.add_parser("dump", help="write untranslated source strings to a todo file")
    p_dump.add_argument(
        "--cyrillic-only",
        action="store_true",
        help="only strings containing Cyrillic (skips the English-language entries)",
    )

    p_merge = sub.add_parser("merge", help="fold a filled todo file into the store")
    p_merge.add_argument("--verbose", action="store_true", help="list rejected entries")

    sub.add_parser("stats", help="coverage per field")

    args = parser.parse_args()
    if args.command == "merge":
        cmd_merge(args)
    elif args.command == "dump":
        asyncio.run(cmd_dump(args))
    else:
        asyncio.run(cmd_stats(args))


if __name__ == "__main__":
    main()
