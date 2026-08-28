"""Generates scripts/data/uniranks_world_rank_review.json — a review of
candidate UNIRANKS 2027 world-rank matches for every University row that
doesn't have one yet (all 2462, not just the ~61 Kazakhstani ones already
covered by scripts/apply_uniranks_kz_2027.py / apply_uniranks_not_ranked.py,
which came from manually transcribing uniranks.com's Kazakhstan-only ranking
page).

Unlike that earlier pass, this one does NOT scrape uniranks' per-country
ranking tables (those only exist for a handful of countries and require
paging through each one by hand). Instead it uses the fact that every
university on uniranks.com has its own profile page at a predictable URL —
https://www.uniranks.com/universities/ru/<slug-of-its-name> — whose page
embeds a JSON-LD block with a clean, unambiguous
`"UNIRANKS Global Rank 2027": <int>` property. So the approach is a direct
per-university lookup (try a few slug variants derived from our own name/
short_name/aliases), not a scrape-and-match against a listing.

We only ever want the WORLD rank here (uniranks_world_rank), never a
national/regional one — see the multi-scale note in
Profy-Frontend's getUniversityRankingLabels; deliberately not touching
uniranks_kz_rank in this pass (per user instruction: no more per-country
tables).

uniranks stores every institution under a *Russian-translated* display name
regardless of what script the source name used (e.g. our "Carnegie Mellon
University" is their "Университет Карнеги Меллон") — so comparing our name
string against the page's declared name is useless for confidence-scoring
non-Russian-named universities; nearly everything would come back "low"
even on a correct match. Confirmed instead by testing that a wrong/near-miss
slug reliably 500s rather than silently resolving to some unrelated existing
university's page (checked by hand against several deliberately-wrong
guesses) — so the identity check that actually matters is *which variant*
produced the 200: a hit on the university's full, unmodified name is strong
evidence on its own ("high"); a hit on a shortened/derived variant
(parenthetical stripped, short_name, an alias) is weaker — short strings
like an acronym are more likely to collide with an unrelated institution —
so those are "low" for a quick human glance. Untouched entries (no 200 for
any variant) are simply not rated by uniranks at all, a normal, expected
outcome for most small regional colleges, not an error.

Read-only against uniranks.com; writes nothing to our DB. Confirmed entries
get applied by scripts/apply_uniranks_world_rank.py.

Run inside the api container:
  docker-compose exec api python scripts/generate_uniranks_world_rank_review.py [--limit N]
"""
import asyncio
import json
import os
import re
import sys

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import httpx
from sqlalchemy import select

from app.database import async_session
from app.models.university import University

OUTPUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "uniranks_world_rank_review.json")
_USER_AGENT = "ProfyUniversityRankingResearch/1.0 (contact: aarhat144@gmail.com; university world-ranking research)"
_REQUEST_DELAY_SECONDS = 0.25
_CONCURRENCY = 6

_NAME_ENTITY_RE = re.compile(r'"@type":"CollegeOrUniversity"[^}]*?"name":"((?:[^"\\]|\\.)*)"')
_GLOBAL_RANK_RE = re.compile(r'"UNIRANKS Global Rank \d{4}"\s*,\s*"value":(\d+)')


def _slugify(name: str) -> str:
    s = name.lower()
    s = re.sub(r"[^\w]+", "-", s, flags=re.UNICODE)
    return s.strip("-")


def _name_variants(uni: University) -> list[str]:
    """Try, in order: full name, name with a trailing "(...)" stripped, each
    segment of a "X — Y" / "X, Y" name, short_name, then aliases — same
    rationale as generate_foreign_university_photo_review.py's
    _name_search_variants (curated names often carry an abbreviation or
    name a sub-unit uniranks won't have its own page for)."""
    variants = [uni.name]
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", uni.name).strip()
    if stripped and stripped != uni.name:
        variants.append(stripped)
    for sep in (" — ", ", "):
        if sep in uni.name:
            variants.append(uni.name.split(sep)[0].strip())
    if uni.short_name:
        variants.append(uni.short_name)
    for alias in uni.aliases or []:
        if alias:
            variants.append(alias)

    seen: set[str] = set()
    ordered: list[str] = []
    for v in variants:
        slug = _slugify(v)
        if slug and slug not in seen:
            seen.add(slug)
            ordered.append(v)
    return ordered


async def _lookup(client: httpx.AsyncClient, slug: str) -> tuple[str, int] | None:
    url = f"https://www.uniranks.com/universities/ru/{slug}"
    try:
        resp = await client.get(url, follow_redirects=True)
    except httpx.HTTPError:
        return None
    if resp.status_code != 200:
        return None
    if resp.url.path.rstrip("/") == "/universities":
        return None  # bounced to the generic listing == not found
    html = resp.text
    name_match = _NAME_ENTITY_RE.search(html)
    rank_match = _GLOBAL_RANK_RE.search(html)
    if not name_match or not rank_match:
        return None
    entity_name = name_match.group(1)
    return entity_name, int(rank_match.group(1))


async def _process_one(sem: asyncio.Semaphore, client: httpx.AsyncClient, uni: University) -> dict | None:
    for variant_index, variant in enumerate(_name_variants(uni)):
        slug = _slugify(variant)
        async with sem:
            result = await _lookup(client, slug)
            await asyncio.sleep(_REQUEST_DELAY_SECONDS)
        if result is None:
            continue
        entity_name, world_rank = result
        # Full, unmodified name matched -> strong signal on its own (see
        # module docstring re: uniranks' Russian-translated display names
        # making string comparison useless here). Anything matched via a
        # shortened/derived variant is weaker and gets a human glance.
        confidence = "high" if variant_index == 0 else "low"
        return {
            "university_id": str(uni.id),
            "our_name": uni.name,
            "country": uni.country,
            "city": uni.city,
            "matched_variant": variant,
            "matched_slug": slug,
            "uniranks_name": entity_name,
            "world_rank": world_rank,
            "confidence": confidence,
            "confirmed": confidence == "high",
        }
    return None


async def main() -> None:
    limit = None
    if "--limit" in sys.argv:
        limit = int(sys.argv[sys.argv.index("--limit") + 1])

    async with async_session() as db:
        result = await db.execute(
            select(University).where(University.uniranks_world_rank.is_(None)).order_by(University.name)
        )
        universities = result.scalars().all()

    if limit:
        universities = universities[:limit]

    print(f"Checking {len(universities)} universities against uniranks.com...")

    sem = asyncio.Semaphore(_CONCURRENCY)
    entries: list[dict] = []
    checked = 0

    async with httpx.AsyncClient(headers={"User-Agent": _USER_AGENT}, timeout=20.0) as client:
        tasks = [_process_one(sem, client, uni) for uni in universities]
        for coro in asyncio.as_completed(tasks):
            res = await coro
            checked += 1
            if res is not None:
                entries.append(res)
                tag = "HIGH" if res["confidence"] == "high" else "low "
                print(f"[{tag}] {res['our_name']!r} -> #{res['world_rank']} ({res['uniranks_name']!r})")
            if checked % 100 == 0:
                print(f"... {checked}/{len(universities)} checked, {len(entries)} matches so far")

    entries.sort(key=lambda e: e["world_rank"])

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)

    high = sum(1 for e in entries if e["confidence"] == "high")
    low = len(entries) - high
    print(f"\nChecked: {len(universities)}, matched: {len(entries)} (high={high}, low={low}), not found: {len(universities) - len(entries)}")
    print(f"Written to {OUTPUT_PATH}")


if __name__ == "__main__":
    asyncio.run(main())
