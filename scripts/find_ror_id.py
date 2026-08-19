"""
Look up a candidate foreign university against the ROR registry (ror.org)
before adding it to a seed data file (e.g. scripts/data/universities_92_professions.py).

Part of docs/university-module-fix-plan.md B1: `University.ror_id` is the
canonical dedup key for foreign universities, replacing name/slug matching
which drifts across spelling variants of the same institution. This script
is the manual research step — it does NOT write to the DB or to any data
file; it just prints candidates so a researcher can pick the right ror_id
and website, then paste them into the new university's dict.

Usage:
    python scripts/find_ror_id.py "Technical University of Munich"
    python scripts/find_ror_id.py "Nanyang Technological University" --country Singapore
"""
import argparse
import asyncio
import sys

import httpx

ROR_API = "https://api.ror.org/v2/organizations"


async def search(query: str, country: str | None) -> list[dict]:
    params = {"query": query}
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(ROR_API, params=params)
        resp.raise_for_status()
        data = resp.json()

    items = data.get("items", [])
    if country:
        country_lower = country.lower()
        filtered = [
            item
            for item in items
            if country_lower in (item.get("locations", [{}])[0].get("geonames_details", {}).get("country_name", "") or "").lower()
        ]
        items = filtered or items  # fall back to unfiltered if the country filter drops everything
    return items


def primary_name(item: dict) -> str:
    for name in item.get("names", []):
        if "ror_display" in name.get("types", []):
            return name["value"]
    names = item.get("names", [])
    return names[0]["value"] if names else "(no name)"


def website(item: dict) -> str | None:
    links = item.get("links", [])
    for link in links:
        if link.get("type") == "website":
            return link.get("value")
    return None


def print_candidates(items: list[dict]) -> None:
    if not items:
        print("No matches found.")
        return
    for item in items[:8]:
        ror_id = item.get("id", "").rsplit("/", 1)[-1]
        country_name = (item.get("locations", [{}])[0].get("geonames_details", {}) or {}).get("country_name", "?")
        print(f"  ror_id={ror_id}")
        print(f"    name:    {primary_name(item)}")
        print(f"    country: {country_name}")
        print(f"    website: {website(item) or '(none)'}")
        print()


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="University name to search for")
    parser.add_argument("--country", default=None, help="Filter/prioritize results by country name")
    args = parser.parse_args()

    try:
        items = await search(args.query, args.country)
    except httpx.HTTPError as exc:
        print(f"ROR API request failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(f"Query: {args.query!r}" + (f" (country={args.country})" if args.country else ""))
    print_candidates(items)


if __name__ == "__main__":
    asyncio.run(main())
