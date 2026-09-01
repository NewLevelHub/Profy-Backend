"""Generates scripts/data/foreign_university_dedup_review.json — candidate
duplicate pairs among non-KZ University rows, with everything a human needs
to re-confirm each pair's identity and pick which side to keep.

Replaces a hand-built file whose only row references were bare
`University.id` uuid4() snapshots (dead on any DB but the one they were
taken from — PRO-247, see docs/content-pipeline-id-resolution-audit.md).
Every side of every pair here carries a portable `slug` (and `ror_id` when
set), so apply_foreign_university_dedup.py can resolve it anywhere.

Candidate signals (union-find into groups of >= 2), mirroring the original
file's _notes:
  exact_name                 - same normalized name
  shared_ror_id              - same non-null ror_id (the canonical dedup key)
  name_without_parenthetical - same name after stripping a trailing "(...)"
                               ("Delft University of Technology" vs "(TU Delft)")

Nothing is confirmed automatically — identity still needs a human check
(city, photo, program count, ror_id), same discipline as apply_ovpo_codes.py's
discarded fuzzy pass. For each group the reviewer sets `confirmed: true` and
fills `keep_slug` / `remove_slug` (optionally `keep_ror_id` / `remove_ror_id`).
`suggested_*` is only a hint. Existing `no_action` groups and `_notes` from
the current file are carried over verbatim so known non-duplicates and
translation coincidences aren't re-litigated.

Read-only against the DB. Writes scripts/data/foreign_university_dedup_review.regenerated.json
by default; pass --overwrite to replace the real review file.

Run inside the api container:
  docker-compose exec api python scripts/generate_foreign_university_dedup_review.py [--overwrite]
"""
import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

from sqlalchemy import func, select

from app.database import async_session
from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from app.models.university_image import UniversityImage
from scripts.import_jinaq_universities import _normalize

DATA_DIR = os.path.join(_ROOT, "scripts", "data")
REVIEW_PATH = os.path.join(DATA_DIR, "foreign_university_dedup_review.json")
REGEN_PATH = os.path.join(DATA_DIR, "foreign_university_dedup_review.regenerated.json")

_PARENTHETICAL_RE = re.compile(r"\s*\([^)]*\)\s*$")


def _strip_parenthetical(name: str) -> str:
    return _PARENTHETICAL_RE.sub("", name).strip()


class _UnionFind:
    def __init__(self) -> None:
        self.parent: dict = {}

    def find(self, x):
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a, b) -> None:
        self.parent[self.find(a)] = self.find(b)

    def groups(self) -> list[list]:
        out: dict = defaultdict(list)
        for x in self.parent:
            out[self.find(x)].append(x)
        return [g for g in out.values() if len(g) >= 2]


def _keep_rank(side: dict) -> tuple:
    """Higher is better as the row to KEEP: has ror_id, has photo, more
    programs, shorter slug (the preference from merge_duplicate_universities.py)."""
    return (
        bool(side["ror_id"]),
        side["has_photo"],
        side["program_count"],
        -len(side["slug"] or ""),
    )


def _prior_reasons(old_review: dict) -> list[tuple[set[str], str]]:
    out: list[tuple[set[str], str]] = []
    for entry in old_review.get("merges", []):
        anchors = {
            _normalize(part)
            for part in re.split(r"\s*/\s*", entry.get("name", ""))
            if part.strip()
        }
        if entry.get("reason"):
            out.append((anchors, entry["reason"]))
    return out


def _match_prior(group_names: list[str], priors: list[tuple[set[str], str]]) -> str | None:
    keys = {_normalize(n) for n in group_names} | {_normalize(_strip_parenthetical(n)) for n in group_names}
    for anchors, reason in priors:
        if anchors & keys:
            return reason
    return None


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true", help=f"write {REVIEW_PATH} instead of the .regenerated.json")
    args = parser.parse_args()

    old_review = {}
    if os.path.exists(REVIEW_PATH):
        with open(REVIEW_PATH, encoding="utf-8") as f:
            old_review = json.load(f)

    async with async_session() as db:
        universities = (
            await db.execute(select(University).where(University.country != "Казахстан"))
        ).scalars().all()

        prog_counts = dict(
            (
                await db.execute(
                    select(Program.university_id, func.count()).group_by(Program.university_id)
                )
            ).all()
        )
        photo_uni_ids = {
            uid
            for (uid,) in (
                await db.execute(select(UniversityImage.university_id).distinct())
            ).all()
        }
        jinaq_ext = dict(
            (
                await db.execute(
                    select(UniversityExternalRef.university_id, UniversityExternalRef.external_id).where(
                        UniversityExternalRef.source == "jinaq"
                    )
                )
            ).all()
        )

    by_id = {u.id: u for u in universities}

    uf = _UnionFind()
    for u in universities:
        uf.find(u.id)
    # signal 1: exact normalized name
    name_buckets: dict[str, list] = defaultdict(list)
    for u in universities:
        name_buckets[_normalize(u.name)].append(u.id)
    # signal 3: name without a trailing parenthetical
    paren_buckets: dict[str, list] = defaultdict(list)
    for u in universities:
        paren_buckets[_normalize(_strip_parenthetical(u.name))].append(u.id)
    # signal 2: shared non-null ror_id
    ror_buckets: dict[str, list] = defaultdict(list)
    for u in universities:
        if u.ror_id:
            ror_buckets[u.ror_id].append(u.id)

    signal_by_pairkey: dict = {}
    for buckets, signal in (
        (name_buckets, "exact_name"),
        (paren_buckets, "name_without_parenthetical"),
        (ror_buckets, "shared_ror_id"),
    ):
        for ids in buckets.values():
            if len(ids) < 2:
                continue
            for other in ids[1:]:
                uf.union(ids[0], other)
            for i in ids:
                signal_by_pairkey.setdefault(uf.find(i), set()).add(signal)

    priors = _prior_reasons(old_review)

    def _side(uid) -> dict:
        u = by_id[uid]
        return {
            "slug": u.slug,
            "name": u.name,
            "ror_id": u.ror_id,
            "city": u.city,
            "country": u.country,
            "short_name": u.short_name,
            "program_count": int(prog_counts.get(u.id, 0)),
            "has_photo": u.id in photo_uni_ids,
            "jinaq_external_id": jinaq_ext.get(u.id),
            "_snapshot_id": str(u.id),
        }

    merges = []
    for group in uf.groups():
        sides = sorted((_side(uid) for uid in group), key=_keep_rank, reverse=True)
        keep, *rest = sides
        group_names = [s["name"] for s in sides]
        merges.append(
            {
                "confirmed": False,
                "match_signal": sorted(signal_by_pairkey.get(uf.find(group[0]), [])),
                "reason_prior": _match_prior(group_names, priors),
                "suggested_keep_slug": keep["slug"],
                "suggested_remove_slugs": [s["slug"] for s in rest],
                "keep_slug": None,
                "remove_slug": None,
                "sides": sides,
            }
        )

    merges.sort(key=lambda m: (m["reason_prior"] is None, m["sides"][0]["name"]))

    out = {
        "_notes": old_review.get(
            "_notes",
            [
                "Regenerated by scripts/generate_foreign_university_dedup_review.py.",
                "Set confirmed:true and fill keep_slug/remove_slug per confirmed pair.",
            ],
        ),
        "_regenerated": True,
        "merges": merges,
        "no_action": old_review.get("no_action", []),
    }

    target = REVIEW_PATH if args.overwrite else REGEN_PATH
    with open(target, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)

    with_prior = sum(1 for m in merges if m["reason_prior"])
    print(
        f"{len(universities)} foreign universities -> {len(merges)} candidate groups "
        f"({with_prior} matched a prior reason), {len(out['no_action'])} no_action carried over"
    )
    print(f"written to {target}")
    if not args.overwrite:
        print("review it, then re-run with --overwrite (or copy it over) once keep_slug/remove_slug are filled")


if __name__ == "__main__":
    asyncio.run(main())
