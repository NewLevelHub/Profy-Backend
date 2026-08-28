"""Generates scripts/data/foreign_university_photo_review.json — a review of
candidate Wikidata matches (and their photo, via the P18 image property) for
every non-KZ University row that jinaq doesn't cover (so it never got a
photo at all — see scripts/import_jinaq_university_photos.py).

Read-only against Wikidata's public API; writes nothing to our DB or
storage. Confidence is "high" only when the top wbsearchentities hit's
label matches the university name closely (normalized exact, or one is a
substring of the other) AND its description mentions a university/college
keyword (guards against matching a same-named school/press/building
instead of the institution itself, e.g. "Carnegie Mellon University Press").
Anything else is "low" or "no_match"/"no_image" — for human review, same
discipline as every other identity-matching pass in this project. Nothing
gets downloaded or applied here; that's
scripts/apply_foreign_university_photos_from_wikidata.py, and only for
entries a human sets `confirmed: true` on.

Run inside the api container:
  docker-compose exec api python scripts/generate_foreign_university_photo_review.py
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
from app.models.university_external_ref import UniversityExternalRef

OUTPUT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "data", "foreign_university_photo_review.json"
)
_UNIVERSITY_KEYWORDS = ("university", "college", "institute", "academy", "school of", "polytechnic", "conservatory")
_REQUEST_DELAY_SECONDS = 0.3


def _normalize(s: str) -> str:
    return " ".join(s.strip().lower().replace("(", " ").replace(")", " ").split())


def _name_search_variants(name: str) -> list[str]:
    """Our curated names often carry a trailing abbreviation ("Carnegie
    Mellon University (CMU)") or name a school/department within a larger
    institution ("Rotman School of Management, University of Toronto" /
    "National University of Singapore — NUS Business School") — Wikidata's
    label search wants the plain institution name, so try, in order: the
    name as-is, with any trailing "(...)" stripped, then each "X, Y" / "X
    — Y" segment (the parent institution — usually the one with its own
    Wikidata page and campus photo — is tried first since it's more likely
    to be what a photo should show; department pages rarely have one)."""
    variants = [name]
    stripped = re.sub(r"\s*\([^)]*\)\s*$", "", name).strip()
    if stripped and stripped != name:
        variants.append(stripped)
    for sep in (" — ", ", "):
        if sep in stripped:
            parts = [p.strip() for p in stripped.split(sep) if p.strip()]
            # Parent institution is conventionally the longer/more formal
            # segment (contains "university"/"institut"/etc.) — try it before
            # the other segment, but try both.
            parts.sort(key=lambda p: ("university" not in p.lower() and "institut" not in p.lower(), len(p)))
            for p in parts:
                if p not in variants:
                    variants.append(p)
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
    if name_matches or looks_like_university:
        return "low"
    return "low"


async def main() -> None:
    async with async_session() as db:
        result = await db.execute(
            select(University)
            .outerjoin(
                UniversityExternalRef,
                (UniversityExternalRef.university_id == University.id) & (UniversityExternalRef.source == "jinaq"),
            )
            .where(University.country != "Казахстан", UniversityExternalRef.id.is_(None))
            .order_by(University.name)
        )
        universities = result.scalars().all()

    print(f"{len(universities)} foreign universities without a jinaq photo to check against Wikidata")

    entries = []
    # Wikimedia's own robot policy (https://w.wiki/4wJS) 403s any request
    # without a compliant User-Agent naming the app, a contact point, and
    # purpose — a generic UA gets blocked at the edge before ever reaching
    # the API logic.
    headers = {"User-Agent": "ProfyUniversityPhotoResearch/1.0 (contact: aarhat144@gmail.com; university photo research)"}
    async with httpx.AsyncClient(timeout=15, headers=headers) as client:
        for i, uni in enumerate(universities, start=1):
            entry = {
                "university_slug": uni.slug,
                "university_name": uni.name,
                "university_id": str(uni.id),
                "wikidata_id": None,
                "wikidata_label": None,
                "wikidata_description": None,
                "image_filename": None,
                "confidence": "no_match",
                "confirmed": False,
            }
            try:
                best_no_image: dict | None = None
                for variant in _name_search_variants(uni.name):
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
            if i % 20 == 0:
                print(f"  ...{i}/{len(universities)}")

    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(
            {
                "_readme": (
                    "Each entry proposes a Wikidata match + its P18 image for a foreign university jinaq "
                    "doesn't cover. Check `wikidata_label`/`wikidata_description` against `university_name` — "
                    "if it's really the same institution and the image looks right, set `confirmed: true`. "
                    "confidence='low' or 'no_match'/'no_image' entries need a closer look or a manual "
                    "wikidata_id/image_filename fix before confirming. Nothing is downloaded until "
                    "scripts/apply_foreign_university_photos_from_wikidata.py runs against confirmed entries."
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
