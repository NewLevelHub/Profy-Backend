"""Generates scripts/data/missing_university_photo_review.json — a review of
candidate Wikidata matches (and their photo, via the P18 image property) for
every University row that STILL has zero photos after both earlier passes
(scripts/import_jinaq_university_photos.py and
scripts/generate_foreign_university_photo_review.py's Wikidata sweep).

Broader than that earlier sweep in one way: this one does NOT exclude
Kazakhstani universities. The earlier pass only ever targeted non-KZ
universities because at the time every KZ university either came from jinaq
(photo already handled) or the hand-curated set — but 27 KZ universities
turned out to have neither a jinaq photo nor ever been checked against
Wikidata at all, discovered by directly auditing "which university has zero
UniversityImage rows" rather than assuming jinaq coverage implies photo
coverage.

Same matching/confidence logic as generate_foreign_university_photo_review.py
(see that file for the full rationale) — duplicated rather than imported
since the two scripts target a different, one-time query each and are each
meant to be read standalone as a record of what was actually done and why.

Read-only against Wikidata's public API; writes nothing to our DB or
storage. Nothing gets downloaded until
scripts/apply_missing_university_photos_from_wikidata.py runs against
confirmed entries.

Run inside the api container:
  docker-compose exec api python scripts/generate_missing_university_photo_review.py
"""
import asyncio
import json
import os
import re
import sys
import time

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)

import httpx
from sqlalchemy import select

from app.database import async_session
from app.models.university import University
from app.models.university_image import UniversityImage

OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "missing_university_photo_review.json"
)
_UNIVERSITY_KEYWORDS = ("university", "college", "institute", "academy", "school of", "polytechnic", "conservatory")
_REQUEST_DELAY_SECONDS = 0.3


def _normalize(s: str) -> str:
    return " ".join(s.strip().lower().replace("(", " ").replace(")", " ").split())


def _name_search_variants(name: str, short_name: str | None) -> list[str]:
    """Same rationale as generate_foreign_university_photo_review.py, plus
    short_name — several of the 27 KZ entries here are only known to
    Wikidata by their short/English name (e.g. "Narxoz University" rather
    than the full curated name), which the KZ data source doesn't always
    put first in `name` the way the foreign-cluster source does."""
    variants = [name]
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if stripped and stripped != name:
        variants.append(stripped)
    for sep in (" — ", ", "):
        if sep in stripped:
            parts = [p.strip() for p in stripped.split(sep) if p.strip()]
            parts.sort(key=lambda p: ("university" not in p.lower() and "институт" not in p.lower(), len(p)))
            for p in parts:
                if p not in variants:
                    variants.append(p)
    if short_name and short_name not in variants:
        variants.append(short_name)
    return variants


async def _search_wikidata(client: httpx.AsyncClient, name: str) -> dict | None:
    resp = await client.get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbsearchentities", "search": name, "language": "en", "format": "json", "limit": 3},
    )
    resp.raise_for_status()
    results = resp.json().get("search") or []
    return results[0] if results else None


async def _get_image_filename(client: httpx.AsyncClient, entity_id: str) -> str | None:
    resp = await client.get(
        "https://www.wikidata.org/w/api.php",
        params={"action": "wbgetclaims", "entity": entity_id, "property": "P18", "format": "json"},
    )
    resp.raise_for_status()
    claims = resp.json().get("claims", {}).get("P18")
    if not claims:
        return None
    return claims[0]["mainsnak"]["datavalue"]["value"]


def _confidence(university_name: str, candidate_label: str, candidate_description: str) -> str:
    a, b = _normalize(university_name), _normalize(candidate_label)
    name_matches = a == b or a in b or b in a
    desc = (candidate_description or "").lower()
    looks_like_university = any(k in desc for k in _UNIVERSITY_KEYWORDS)
    if name_matches and looks_like_university:
        return "high"
    return "low"


async def main() -> None:
    async with async_session() as db:
        result = await db.execute(
            select(University)
            .where(University.id.not_in(select(UniversityImage.university_id).distinct()))
            .order_by(University.country, University.name)
        )
        universities = result.scalars().all()

    print(f"{len(universities)} universities with zero photos to check against Wikidata")

    entries = []
    headers = {"User-Agent": "ProfyUniversityPhotoResearch/1.0 (contact: aarhat144@gmail.com; university photo research)"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        for i, uni in enumerate(universities, start=1):
            entry = {
                "university_slug": uni.slug,
                "university_name": uni.name,
                "university_id": str(uni.id),
                "country": uni.country,
                "wikidata_id": None,
                "wikidata_label": None,
                "wikidata_description": None,
                "image_filename": None,
                "confidence": "no_match",
                "confirmed": False,
            }
            try:
                best_no_image: dict | None = None
                for variant in _name_search_variants(uni.name, uni.short_name):
                    hit = await _search_wikidata(client, variant)
                    time.sleep(_REQUEST_DELAY_SECONDS)
                    if not hit:
                        continue
                    image_filename = await _get_image_filename(client, hit["id"])
                    time.sleep(_REQUEST_DELAY_SECONDS)
                    if image_filename:
                        entry["wikidata_id"] = hit["id"]
                        entry["wikidata_label"] = hit.get("label")
                        entry["wikidata_description"] = hit.get("description")
                        entry["image_filename"] = image_filename
                        entry["confidence"] = _confidence(uni.name, hit.get("label", ""), hit.get("description", ""))
                        break
                    if best_no_image is None:
                        best_no_image = hit
                else:
                    if best_no_image is not None:
                        entry["wikidata_id"] = best_no_image["id"]
                        entry["wikidata_label"] = best_no_image.get("label")
                        entry["wikidata_description"] = best_no_image.get("description")
                        entry["confidence"] = "no_image"
            except httpx.HTTPError as exc:
                entry["confidence"] = "error"
                entry["wikidata_description"] = f"request failed: {exc!r}"
            entries.append(entry)
            time.sleep(_REQUEST_DELAY_SECONDS)
            if i % 10 == 0:
                print(f"  ...{i}/{len(universities)}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "_readme": (
                    "Each entry proposes a Wikidata match + its P18 image for a university with zero photos "
                    "(KZ and foreign both — see module docstring). Check wikidata_label/wikidata_description "
                    "against university_name — if it's really the same institution and the image looks right, "
                    "set confirmed: true. confidence='low' or 'no_match'/'no_image' entries need a closer look "
                    "or a manual wikidata_id/image_filename fix before confirming. Nothing is downloaded until "
                    "scripts/apply_missing_university_photos_from_wikidata.py runs against confirmed entries."
                ),
                "entries": entries,
            },
            f,
            ensure_ascii=False,
            indent=2,
        )

    by_conf: dict[str, int] = {}
    for e in entries:
        by_conf[e["confidence"]] = by_conf.get(e["confidence"], 0) + 1
    print(f"\nWrote {len(entries)} entries to {OUTPUT_PATH}")
    print(by_conf)


if __name__ == "__main__":
    asyncio.run(main())
