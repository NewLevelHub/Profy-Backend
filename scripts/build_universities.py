"""
THE university/program loader. Reads ONE committed file —
scripts/data/university_snapshot.clean.json — and brings the `universities`,
`programs`, `program_directions` and `university_external_refs` tables into
line with it. Runs on every deploy, in place of the ~30 seed/apply/backfill
scripts it replaces.

Design
------
* Deterministic primary keys. `University.id` / `Program.id` are
  `uuid5(NAMESPACE, <portable key>)`, not a per-DB `uuid4()`. The same row
  gets the SAME id on every database (local / dev / prod), which is what
  makes the snapshot portable and kills the PRO-244 class of "review file
  keyed by a dead uuid" bugs by construction.
      university: uuid5(NS, "jinaq:<jinaq_id>")  — or "slug:", "ror:", "ncc:"
      program:    uuid5(NS, "<university_id>:<degree-normalised name>")

* Two phases: PRUNE then UPSERT.
    1. PRUNE — delete every `universities` / `programs` / `university_external_refs`
       row whose (deterministic id / (source,external_id)) is not in the
       snapshot. On the FIRST run against a DB seeded the old way this is
       every row (they all carry a random `uuid4()`), i.e. a one-time full
       rebuild — pruning happens BEFORE inserts so the old and new rows never
       collide on the `slug` / `ror_id` / `ovpo_code` unique indexes.
    2. UPSERT — insert missing rows, update changed rows field-by-field,
       leave unchanged rows untouched.
  On every later run the prune set is empty and step 2 is a near no-op, so
  `direction_roadmaps.program_id` (the one long-lived FK into `programs`,
  `ON DELETE SET NULL`) is nulled only on that first rebuild and stays intact
  afterwards (the program keeps a stable id).

* Never sets `name_normalized` (DB-computed), `cost_*` or `ranking_label` /
  `uniranks_*` (deliberately not in the snapshot). `world_rank` -> `ranking`.

* UPSERT skips any field an admin has manually edited via /admin/universities
  or /admin/programs (`admin_locked_fields`, see app/services/admin_lock.py
  and docs/admin-edit-lock-plan.md) — this loader replaced the ~30-script
  pipeline where every individual overwrite-if-different script checked
  `is_locked()` itself; the check has to live here now since this is the
  only place left that overwrites-if-different for these two tables.

Requires `directions` to already be seeded (scripts/seed_riasec_directions.py)
— profession tags reference Direction rows by slug; an unknown slug is
reported and skipped, never invented.

Run inside the api container:
  docker compose exec api python scripts/build_universities.py            # apply
  docker compose exec api python scripts/build_universities.py --dry-run  # report only
  docker compose exec api python scripts/build_universities.py --check    # exit 1 if DB != snapshot
"""
import argparse
import asyncio
import json
import os
import re
import sys
import uuid
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import delete, func, select
from sqlalchemy.orm import selectinload

from app.database import async_session
from app.models.direction import Direction
from app.models.direction_roadmap import DirectionRoadmap
from app.models.program import Program
from app.models.university import University
from app.models.university_external_ref import UniversityExternalRef
from app.services.admin_lock import is_locked

SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "university_snapshot.clean.json")

# Universities per commit in phase 2. The whole run used to be one
# transaction from the first SELECT to the final commit (9+ minutes on a
# real deploy, zero progress output) — if the deploy's SSH session got
# killed mid-run (timeout, cancelled workflow) the orphaned process could
# leave that entire transaction's row locks on `universities`/`programs`
# held until something noticed the dead connection, which without a tuned
# `idle_in_transaction_session_timeout` can take a very long time and has
# required a full server reboot to clear in practice. Committing every
# CHUNK_SIZE universities bounds how much a single interruption can leave
# locked to one chunk instead of the whole snapshot, and the progress print
# below means a slow-but-alive run is distinguishable from a stuck one in
# the deploy log.
CHUNK_SIZE = 200

# Fixed namespace for uuid5 — DO NOT CHANGE (every id in every DB derives from it).
NAMESPACE = uuid.UUID("6f4d9d2e-1c3a-5b7e-9f10-2a4c6e8b0d13")

_WS = re.compile(r"\s+")
# Mirrors programs.name_normalized's Computed() expression (app/models/program.py).
_DEGREE_SUFFIX = re.compile(
    r"\s*\((?:бакалавр(?:,\s*[^)]*)?|магистратура|практический психолог)\)\s*", re.IGNORECASE
)

UNIVERSITY_FIELDS = (
    "name", "slug", "ror_id", "ovpo_code", "short_name", "aliases", "location",
    "country", "city", "website", "description", "source_url",
    "contacts", "facilities", "fact_sources",
)
PROGRAM_FIELDS = (
    "name", "language", "source_category", "description", "who_its_for",
    "career_options", "requirements", "deadlines", "grants",
    "source_url", "fact_sources",
)


def _norm_program(name: str) -> str:
    return _WS.sub(" ", _DEGREE_SUFFIX.sub(" ", name or "").strip()).lower()


def university_id(rec: dict) -> uuid.UUID:
    """Deterministic PK, keyed by the most stable identifier available.
    `jinaq_id` first — covers the ~2200 jinaq-sourced rows and is immune to
    the slug canonicalization done in build_catalog.py, so their id (and
    every child program's id, which is derived from it) never moves. The
    `slug` / `ror_id` / `ncc` fallbacks are only for the ~150 rows with no
    jinaq_id at all; for those, a slug change DOES move the id, which re-keys
    their programs and nulls `direction_roadmaps.program_id`
    (ON DELETE SET NULL) for any student who saved a plan against one. That
    is acceptable only because slug canonicalization is a one-time build-time
    step that produces stable slugs — after it has run once, these ids are
    fixed too. Don't add a runtime code path that renames a curated slug."""
    k = rec.get("keys") or {}
    if k.get("jinaq_id"):
        return uuid.uuid5(NAMESPACE, f"jinaq:{k['jinaq_id']}")
    if k.get("slug"):
        return uuid.uuid5(NAMESPACE, f"slug:{k['slug']}")
    if k.get("ror_id"):
        return uuid.uuid5(NAMESPACE, f"ror:{k['ror_id']}")
    anchor = "|".join(_WS.sub(" ", (rec.get(f) or "").strip()).lower()
                      for f in ("name", "country", "city"))
    return uuid.uuid5(NAMESPACE, f"ncc:{anchor}")


def program_id(uni_id: uuid.UUID, name: str) -> uuid.UUID:
    return uuid.uuid5(NAMESPACE, f"{uni_id}:{_norm_program(name)}")


def apply_synced_fields(row, updates: dict) -> tuple[bool, int]:
    """Set `row`'s columns from `updates`, skipping any field an admin has
    manually edited (`admin_lock.is_locked`) so a redeploy doesn't silently
    revert it. Shared by the University and Program upsert branches below.
    Returns (changed, locked_skips)."""
    changed = False
    locked_skips = 0
    for f, v in updates.items():
        if is_locked(row, f):
            if getattr(row, f) != v:
                locked_skips += 1
            continue
        if getattr(row, f) != v:
            setattr(row, f, v)
            changed = True
    return changed, locked_skips


class Stats:
    def __init__(self):
        self.uni_ins = self.uni_upd = self.uni_del = 0
        self.prog_ins = self.prog_upd = self.prog_del = 0
        self.ref_ins = self.ref_upd = self.ref_del = 0
        self.tag_links = 0
        self.untagged_programs = 0
        self.unknown_slugs: set[str] = set()
        self.dupe_program_names: list[str] = []
        self.roadmaps_unlinked = 0
        self.progs_per_slug: Counter = Counter()
        self.professions_empty: list[str] = []
        self.professions_thin: list[tuple[str, int]] = []
        self.uni_locked_skips = 0
        self.prog_locked_skips = 0

    def touched(self) -> int:
        return (self.uni_ins + self.uni_upd + self.uni_del + self.prog_ins
                + self.prog_upd + self.prog_del + self.ref_ins + self.ref_upd + self.ref_del)

    def report(self, dry: bool) -> str:
        head = "DRY RUN — nothing written\n" if dry else ""
        out = (
            f"{head}"
            f"universities   insert={self.uni_ins}  update={self.uni_upd}  prune={self.uni_del}\n"
            f"programs       insert={self.prog_ins}  update={self.prog_upd}  prune={self.prog_del}\n"
            f"external_refs  insert={self.ref_ins}  update={self.ref_upd}  prune={self.ref_del}\n"
            f"profession tag links: {self.tag_links}   programs with no tag: {self.untagged_programs}\n"
        )
        if self.roadmaps_unlinked:
            out += (f"WARNING: {self.roadmaps_unlinked} direction_roadmaps.program_id set NULL "
                    f"by pruning old-id programs (one-time, on the first rebuild)\n")
        if self.unknown_slugs:
            out += f"unknown profession slugs (skipped): {sorted(self.unknown_slugs)}\n"
        if self.dupe_program_names:
            out += (f"duplicate program names within a university (kept first): "
                    f"{len(self.dupe_program_names)}\n")
        if self.professions_empty:
            out += (f"\nSNAP-5: professions with 0 tagged programs "
                    f"(student picks -> empty page): {sorted(self.professions_empty)}\n")
        if self.professions_thin:
            out += ("SNAP-5: professions with 1-2 tagged programs: "
                    + ", ".join(f"{s}={n}" for s, n in sorted(self.professions_thin)) + "\n")
        if self.uni_locked_skips or self.prog_locked_skips:
            out += (f"admin-locked fields skipped (not overwritten): "
                    f"universities={self.uni_locked_skips}  programs={self.prog_locked_skips}\n")
        return out


async def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", default=SNAPSHOT)
    ap.add_argument("--dry-run", action="store_true", help="compute and report, write nothing")
    ap.add_argument("--check", action="store_true",
                    help="exit 1 if any insert/update/prune would happen (no writes)")
    args = ap.parse_args()
    dry = args.dry_run or args.check

    with open(args.snapshot, encoding="utf-8") as f:
        snapshot = json.load(f)["universities"]
    st = Stats()

    # ---- resolve deterministic ids for the whole snapshot up front ----------
    recs: list[tuple[uuid.UUID, dict, list[tuple[uuid.UUID, dict]]]] = []
    all_uni_ids: set[uuid.UUID] = set()
    all_prog_ids: set[uuid.UUID] = set()
    all_ref_keys: set[tuple[str, str]] = set()
    for rec in snapshot:
        uid = university_id(rec)
        all_uni_ids.add(uid)
        for ref in rec.get("external_refs") or []:
            all_ref_keys.add((ref["source"], ref["external_id"]))
        progs, seen_norm = [], set()
        for prec in rec.get("programs") or []:
            nn = _norm_program(prec["name"])
            if nn in seen_norm:
                st.dupe_program_names.append(f'{rec["name"]} / {prec["name"]}')
                continue
            seen_norm.add(nn)
            pid = program_id(uid, prec["name"])
            all_prog_ids.add(pid)
            progs.append((pid, prec))
        recs.append((uid, rec, progs))

    async with async_session() as db:
        directions_by_slug = {
            d.slug: d for d in (await db.execute(select(Direction))).scalars().all()
        }
        existing_uni_ids = set((await db.execute(select(University.id))).scalars().all())
        existing_prog_ids = set((await db.execute(select(Program.id))).scalars().all())
        existing_ref_keys = {
            (s, e) for s, e in (
                await db.execute(select(UniversityExternalRef.source, UniversityExternalRef.external_id))
            ).all()
        }

        stale_prog = [i for i in existing_prog_ids if i not in all_prog_ids]
        stale_uni = [i for i in existing_uni_ids if i not in all_uni_ids]
        stale_ref = [k for k in existing_ref_keys if k not in all_ref_keys]
        st.prog_del, st.uni_del, st.ref_del = len(stale_prog), len(stale_uni), len(stale_ref)

        if stale_prog:
            st.roadmaps_unlinked = (
                await db.execute(
                    select(func.count()).select_from(DirectionRoadmap).where(
                        DirectionRoadmap.program_id.in_(stale_prog)
                    )
                )
            ).scalar_one()

        # ---- PHASE 1: prune (before any insert — avoids unique-index clashes) ----
        if not dry:
            for chunk in (stale_prog[i:i + 5000] for i in range(0, len(stale_prog), 5000)):
                await db.execute(delete(Program).where(Program.id.in_(chunk)))
            for s, e in stale_ref:
                await db.execute(delete(UniversityExternalRef).where(
                    UniversityExternalRef.source == s, UniversityExternalRef.external_id == e))
            for chunk in (stale_uni[i:i + 5000] for i in range(0, len(stale_uni), 5000)):
                await db.execute(delete(University).where(University.id.in_(chunk)))
            await db.commit()
            if st.uni_del or st.prog_del or st.ref_del:
                print(f"Pruned {st.uni_del} universities, {st.prog_del} programs, "
                      f"{st.ref_del} external_refs", flush=True)

        existing_unis = {
            u.id: u for u in (await db.execute(select(University))).scalars().all()
        }
        existing_progs = {
            p.id: p for p in (
                await db.execute(select(Program).options(selectinload(Program.directions)))
            ).scalars().all()
        }
        existing_refs = {
            (r.source, r.external_id): r
            for r in (await db.execute(select(UniversityExternalRef))).scalars().all()
        }

        # ---- PHASE 2: upsert ---------------------------------------------------
        print(f"Upserting {len(recs)} universities...", flush=True)
        for i, (uid, rec, progs) in enumerate(recs, start=1):
            d = {f: rec.get(f) for f in UNIVERSITY_FIELDS}
            d["aliases"] = rec.get("aliases") or []
            d["contacts"] = rec.get("contacts") or {}
            d["facilities"] = rec.get("facilities") or {}
            d["fact_sources"] = rec.get("fact_sources") or {}
            d["ranking"] = rec.get("world_rank")

            uni = existing_unis.get(uid)
            if uni is None:
                uni = University(id=uid, **d)
                db.add(uni)
                existing_unis[uid] = uni
                st.uni_ins += 1
            else:
                changed, skips = apply_synced_fields(uni, d)
                st.uni_locked_skips += skips
                if changed:
                    st.uni_upd += 1

            for ref in rec.get("external_refs") or []:
                key = (ref["source"], ref["external_id"])
                row = existing_refs.get(key)
                if row is None:
                    db.add(UniversityExternalRef(
                        source=ref["source"], external_id=ref["external_id"],
                        external_name=ref.get("external_name"),
                        match_method=ref.get("match_method"), university_id=uid))
                    st.ref_ins += 1
                elif (row.university_id != uid or row.external_name != ref.get("external_name")
                      or row.match_method != ref.get("match_method")):
                    row.university_id = uid
                    row.external_name = ref.get("external_name")
                    row.match_method = ref.get("match_method")
                    st.ref_upd += 1

            for pid, prec in progs:
                new_dirs = []
                for s in prec.get("professions") or []:
                    dr = directions_by_slug.get(s)
                    if dr is None:
                        st.unknown_slugs.add(s)
                    else:
                        new_dirs.append(dr)
                if not new_dirs:
                    st.untagged_programs += 1
                st.tag_links += len(new_dirs)
                for dr in new_dirs:
                    st.progs_per_slug[dr.slug] += 1

                pd = {f: prec.get(f) for f in PROGRAM_FIELDS}
                pd["career_options"] = prec.get("career_options") or []
                pd["requirements"] = prec.get("requirements") or {}
                pd["deadlines"] = prec.get("deadlines") or {}
                pd["grants"] = prec.get("grants") or []

                prog = existing_progs.get(pid)
                if prog is None:
                    prog = Program(id=pid, university_id=uid, **pd)
                    prog.directions = new_dirs
                    db.add(prog)
                    existing_progs[pid] = prog
                    st.prog_ins += 1
                else:
                    changed = prog.university_id != uid
                    prog.university_id = uid
                    field_changed, skips = apply_synced_fields(prog, pd)
                    changed = changed or field_changed
                    st.prog_locked_skips += skips
                    if {x.slug for x in prog.directions} != {x.slug for x in new_dirs}:
                        prog.directions = new_dirs
                        changed = True
                    if changed:
                        st.prog_upd += 1

            if not dry and i % CHUNK_SIZE == 0:
                await db.commit()
                print(f"  ... {i}/{len(recs)} universities committed", flush=True)

        st.professions_empty = [s for s in directions_by_slug if st.progs_per_slug[s] == 0]
        st.professions_thin = [(s, st.progs_per_slug[s]) for s in directions_by_slug
                               if 0 < st.progs_per_slug[s] < 3]

        if dry:
            await db.rollback()
        else:
            await db.commit()

    print(st.report(dry))
    if args.check and st.touched():
        print(f"--check: DB differs from snapshot ({st.touched()} changes needed)")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
